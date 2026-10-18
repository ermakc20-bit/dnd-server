from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import jwt
import pytest
from app.auth.jwt import SupabaseJWTVerifier
from app.campaigns.dependencies import get_campaign_service
from app.campaigns.repository import PostgresCampaignRepository
from app.campaigns.service import CampaignService
from app.config import Settings, get_settings
from app.identity import dependencies as identity_dependencies
from app.main import create_app
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient

DATABASE_URL = os.getenv("VTT_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="local PostgreSQL not configured")


@pytest.mark.asyncio
async def test_guest_http_projection_and_commands_are_server_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert DATABASE_URL is not None
    connection = await asyncpg.connect(DATABASE_URL)
    user_id, campaign_id, room_id, actor_id = (uuid4() for _ in range(4))
    guest_id, session_id = uuid4(), uuid4()
    await connection.execute(
        "insert into auth.users(id, email) values($1, $2)",
        user_id,
        f"scene-{user_id}@example.invalid",
    )
    await connection.execute(
        "insert into app.campaigns(id,owner_user_id,name) values($1,$2,'Scene test')",
        campaign_id,
        user_id,
    )
    await connection.execute(
        "insert into app.rooms(id,campaign_id,owner_user_id,name) values($1,$2,$3,'Room')",
        room_id,
        campaign_id,
        user_id,
    )
    await connection.execute(
        """insert into app.participants(id,campaign_id,room_id,user_id,role,display_name)
        values($1,$2,$3,$4,'gm','Master')""",
        actor_id,
        campaign_id,
        room_id,
        user_id,
    )
    await connection.execute(
        """insert into app.participants(id,campaign_id,room_id,identity_kind,display_name)
        values($1,$2,$3,'guest','Guest')""",
        guest_id,
        campaign_id,
        room_id,
    )
    await connection.execute(
        """insert into app.guest_sessions(id,participant_id,token_hash,expires_at)
        values($1,$2,$3,now()+interval '1 hour')""",
        session_id,
        guest_id,
        hashlib.sha256(b"local-scene-guest").hexdigest(),
    )
    settings = Settings(environment="test", database_url=DATABASE_URL, _env_file=None)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    service = CampaignService(PostgresCampaignRepository(DATABASE_URL))
    application.dependency_overrides[get_campaign_service] = lambda: service
    from app.scenes.dependencies import get_scene_service
    from app.scenes.repository import SceneRepository
    from app.scenes.service import SceneService

    scenes = SceneService(SceneRepository(DATABASE_URL))
    application.dependency_overrides[get_scene_service] = lambda: scenes
    key = ec.generate_private_key(ec.SECP256R1())
    verifier = SupabaseJWTVerifier(
        issuer="https://local.invalid/auth/v1",
        audience="authenticated",
        signing_key_resolver=lambda _token: key.public_key(),
    )
    monkeypatch.setattr(identity_dependencies, "get_verifier", lambda _settings: verifier)
    now = datetime.now(UTC)
    bearer = jwt.encode(
        {
            "iss": "https://local.invalid/auth/v1",
            "aud": "authenticated",
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        key,
        algorithm="ES256",
    )

    # The guest uses the actual cookie -> resolver -> Participant chain, not an auth user.
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            client.cookies.set("vtt_guest_session", "local-scene-guest")
            response = await client.get(f"/api/v1/rooms/{room_id}/scene")
            assert response.status_code == 200
            assert response.json()["scene"] is None
            assert response.json()["can_manage"] is False
            assert response.json()["actor_session_id"] == str(session_id)

            # A supplied actor/session cannot grant GM permissions.
            command = {
                "command_id": str(uuid4()),
                "room_id": str(room_id),
                "actor_session_id": str(session_id),
                "expected_aggregate_version": 0,
                "type": "scene.create",
                "payload": {"name": "Secret scene"},
                "client_sent_at": datetime.now(UTC).isoformat(),
            }
            response = await client.post(f"/api/v1/rooms/{room_id}/scene/commands", json=command)
            assert response.status_code == 200
            assert response.json()["error_code"] == "forbidden"
            assert (
                await connection.fetchval(
                    "select count(*) from app.scenes where campaign_id=$1",
                    campaign_id,
                )
                == 0
            )
            gm_command = {
                **command,
                "command_id": str(uuid4()),
                "actor_session_id": str(actor_id),
                "payload": {"name": "Shared scene"},
            }
            headers = {"Authorization": f"Bearer {bearer}"}
            response = await client.post(
                f"/api/v1/rooms/{room_id}/scene/commands", json=gm_command, headers=headers
            )
            assert response.json()["status"] == "accepted"
            gm_command = {
                **gm_command,
                "command_id": str(uuid4()),
                "expected_aggregate_version": 1,
                "type": "item.create",
                "payload": {"name": "Secret", "visibility": "gm_only"},
            }
            assert (
                await client.post(
                    f"/api/v1/rooms/{room_id}/scene/commands", json=gm_command, headers=headers
                )
            ).json()["status"] == "accepted"
            gm_command = {
                **gm_command,
                "command_id": str(uuid4()),
                "expected_aggregate_version": 2,
                "payload": {"name": "Assigned", "owner_participant_id": str(guest_id)},
            }
            assert (
                await client.post(
                    f"/api/v1/rooms/{room_id}/scene/commands", json=gm_command, headers=headers
                )
            ).json()["status"] == "accepted"
            projection = (await client.get(f"/api/v1/rooms/{room_id}/scene")).json()
            assert [item["name"] for item in projection["items"]] == ["Assigned"]
            assigned_id = projection["items"][0]["id"]
            gm_command = {
                **gm_command,
                "command_id": str(uuid4()),
                "expected_aggregate_version": 3,
                "payload": {"name": "Other"},
            }
            assert (
                await client.post(
                    f"/api/v1/rooms/{room_id}/scene/commands", json=gm_command, headers=headers
                )
            ).json()["status"] == "accepted"
            gm_projection = (
                await client.get(f"/api/v1/rooms/{room_id}/scene", headers=headers)
            ).json()
            for item in gm_projection["items"]:
                if item["id"] == assigned_id:
                    continue
                denied_command = {
                    **command,
                    "command_id": str(uuid4()),
                    "expected_aggregate_version": 4,
                    "type": "item.update",
                    "payload": {"item_id": item["id"], "x": 999},
                }
                denied = await client.post(
                    f"/api/v1/rooms/{room_id}/scene/commands", json=denied_command
                )
                assert denied.status_code == 200 and denied.json()["error_code"] == "forbidden"
            gm_command = {
                **gm_command,
                "command_id": str(uuid4()),
                "expected_aggregate_version": 4,
                "type": "item.update",
                "payload": {"item_id": assigned_id, "is_locked": True},
            }
            assert (
                await client.post(
                    f"/api/v1/rooms/{room_id}/scene/commands", json=gm_command, headers=headers
                )
            ).json()["status"] == "accepted"
            locked_move = {
                **command,
                "command_id": str(uuid4()),
                "expected_aggregate_version": 5,
                "type": "item.update",
                "payload": {"item_id": assigned_id, "x": 128},
            }
            assert (
                await client.post(f"/api/v1/rooms/{room_id}/scene/commands", json=locked_move)
            ).json()["error_code"] == "forbidden"
            gm_command = {
                **gm_command,
                "command_id": str(uuid4()),
                "expected_aggregate_version": 5,
                "payload": {"item_id": assigned_id, "is_locked": False},
            }
            assert (
                await client.post(
                    f"/api/v1/rooms/{room_id}/scene/commands", json=gm_command, headers=headers
                )
            ).json()["status"] == "accepted"
            move = {
                **command,
                "command_id": str(uuid4()),
                "expected_aggregate_version": 6,
                "type": "item.update",
                "payload": {"item_id": assigned_id, "x": 64},
            }
            assert (await client.post(f"/api/v1/rooms/{room_id}/scene/commands", json=move)).json()[
                "status"
            ] == "accepted"
            row = await connection.fetchrow(
                """select actor_participant_id,actor_user_id from app.room_events
                where room_id=$1 order by id desc limit 1""",
                room_id,
            )
            assert row["actor_participant_id"] == guest_id and row["actor_user_id"] is None
            durable = await connection.fetchrow(
                "select x from app.scene_items where id=$1", UUID(assigned_id)
            )
            assert durable["x"] == 64
            assert (
                await client.get(
                    f"/api/v1/rooms/{room_id}/scene", headers={"Authorization": "Bearer invalid"}
                )
            ).status_code == 401
            client.cookies.clear()
            assert (await client.get(f"/api/v1/rooms/{room_id}/scene")).status_code == 401
    finally:
        await scenes.repository.engine.dispose()
        await connection.execute("delete from app.campaigns where id=$1", campaign_id)
        await connection.execute("delete from auth.users where id=$1", user_id)
        await connection.close()
