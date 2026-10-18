from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import jwt
import pytest
from app.access.policy import Action, authorize
from app.auth import dependencies as auth_dependencies
from app.auth.dependencies import get_current_identity
from app.auth.jwt import AuthIdentity, SupabaseJWTVerifier
from app.campaigns.dependencies import get_campaign_service
from app.campaigns.repository import PostgresCampaignRepository, _async_database_url
from app.campaigns.service import CampaignService
from app.config import Settings, get_settings
from app.identity.dependencies import GUEST_COOKIE, resolve_room_actor
from app.identity.models import Participant
from app.main import create_app
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv("VTT_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    DATABASE_URL is None, reason="VTT_TEST_DATABASE_URL is not configured"
)


def identity(user_id: UUID, email: str) -> AuthIdentity:
    return AuthIdentity(
        user_id=user_id,
        email=email,
        audience="authenticated",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


@pytest.mark.asyncio
async def test_http_and_repository_enforce_invitation_security_and_room_scope() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(_async_database_url(DATABASE_URL))
    repository = PostgresCampaignRepository(DATABASE_URL)
    service = CampaignService(repository)
    owner_id = uuid4()
    player_id = uuid4()
    co_gm_id = uuid4()
    owner_identity = identity(owner_id, f"repo-{owner_id}@example.invalid")
    player_identity = identity(player_id, f"player-{player_id}@example.invalid")
    co_gm_identity = identity(co_gm_id, f"co-gm-{co_gm_id}@example.invalid")

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                insert into auth.users (id, email, raw_user_meta_data)
                values
                  (:owner, :owner_email, '{"display_name":"Repository GM"}'::jsonb),
                  (:player, :player_email, '{"display_name":"Room player"}'::jsonb),
                  (:co_gm, :co_gm_email, '{"display_name":"Second GM"}'::jsonb)
                """
            ),
            {
                "owner": owner_id,
                "owner_email": owner_identity.email,
                "player": player_id,
                "player_email": player_identity.email,
                "co_gm": co_gm_id,
                "co_gm_email": co_gm_identity.email,
            },
        )

    current_identity = {"value": owner_identity}
    current_actor: dict[str, object] = {}
    current_service = {"value": service}
    settings = Settings(environment="test", database_url=DATABASE_URL, _env_file=None)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_current_identity] = lambda: current_identity["value"]
    application.dependency_overrides[get_campaign_service] = lambda: current_service["value"]
    application.dependency_overrides[resolve_room_actor] = lambda: current_actor["value"]

    try:
        campaign = await service.create_campaign(owner_identity, "Repository test", "neutral")
        room = campaign.rooms[0]
        gm = await repository.resolve_registered(owner_id, room.id)
        current_actor["value"] = gm
        second_room_id = uuid4()
        async with engine.begin() as connection:
            stored_gm_name = await connection.scalar(
                text(
                    """
                    select display_name from app.participants
                    where room_id = :room and user_id = :owner
                    """
                ),
                {"room": room.id, "owner": owner_id},
            )
            assert stored_gm_name == "Repository GM"
            await connection.execute(
                text(
                    """
                    insert into app.rooms
                      (id, campaign_id, owner_user_id, name, game_system)
                    values (:id, :campaign, :owner, 'Закрытая комната', 'neutral')
                    """
                ),
                {"id": second_room_id, "campaign": campaign.id, "owner": owner_id},
            )
            await connection.execute(
                text(
                    """
                    insert into app.participants
                      (campaign_id, room_id, user_id, identity_kind, role, display_name)
                    values
                      (:campaign, :second_room, :owner, 'registered', 'gm', 'Repository GM'),
                      (:campaign, :first_room, :player, 'registered', 'player', 'Room player'),
                      (:campaign, :first_room, :co_gm, 'registered', 'gm', 'Second GM')
                    """
                ),
                {
                    "campaign": campaign.id,
                    "second_room": second_room_id,
                    "first_room": room.id,
                    "owner": owner_id,
                    "player": player_id,
                    "co_gm": co_gm_id,
                },
            )

        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            current_identity["value"] = player_identity
            response = await client.get("/api/v1/campaigns")
            assert response.status_code == 200
            assert [item["id"] for item in response.json()[0]["rooms"]] == [str(room.id)]
            assert response.json()[0]["rooms"][0]["can_manage"] is False
            assert "can_manage" not in response.json()[0]

            current_identity["value"] = co_gm_identity
            response = await client.get("/api/v1/campaigns")
            assert response.status_code == 200
            assert [item["id"] for item in response.json()[0]["rooms"]] == [str(room.id)]
            assert response.json()[0]["rooms"][0]["can_manage"] is True

            current_identity["value"] = owner_identity
            response = await client.get("/api/v1/campaigns")
            assert response.status_code == 200
            room_capabilities = {
                item["id"]: item["can_manage"] for item in response.json()[0]["rooms"]
            }
            assert room_capabilities == {
                str(room.id): True,
                str(second_room_id): True,
            }

            response = await client.patch(
                f"/api/v1/rooms/{room.id}/access", json={"pin": "4821"}
            )
            assert response.status_code == 200
            assert response.json()["pin_enabled"] is True
            assert response.json()["can_manage"] is True
            response = await client.post(
                f"/api/v1/rooms/{room.id}/invites", json={"expires_in_minutes": 60}
            )
            assert response.status_code == 200
            invitation = response.json()
            async with engine.connect() as connection:
                stored_token_hash = await connection.scalar(
                    text(
                        """
                        select token_hash from app.room_join_tokens
                        where room_id = :room and revoked_at is null
                        """
                    ),
                    {"room": room.id},
                )
            assert invitation["token"] != stored_token_hash
            assert stored_token_hash == hashlib.sha256(
                invitation["token"].encode("utf-8")
            ).hexdigest()

            for _attempt in range(4):
                response = await client.post(
                    f"/api/v1/join/{invitation['token']}",
                    json={"display_name": "Guest", "pin": "0000"},
                )
                assert response.status_code == 403
                assert response.json()["detail"]["code"] == "invalid_pin"
            response = await client.post(
                f"/api/v1/join/{invitation['token']}",
                json={"display_name": "Guest", "pin": "0000"},
            )
            assert response.status_code == 429
            async with engine.connect() as connection:
                pin_state = (
                    await connection.execute(
                        text(
                            """
                            select failed_pin_attempts, locked_until
                            from app.room_join_tokens where token_hash = :token_hash
                            """
                        ),
                        {"token_hash": stored_token_hash},
                    )
                ).one()
            assert pin_state.failed_pin_attempts == 5
            assert pin_state.locked_until > datetime.now(UTC)

            current_service["value"] = CampaignService(PostgresCampaignRepository(DATABASE_URL))
            response = await client.post(
                f"/api/v1/join/{invitation['token']}",
                json={"display_name": "Guest", "pin": "4821"},
            )
            assert response.status_code == 429
            current_service["value"] = service

            response = await client.post(
                f"/api/v1/rooms/{room.id}/invites/rotate",
                json={"expires_in_minutes": 60},
            )
            assert response.status_code == 200
            rotated = response.json()
            response = await client.post(
                f"/api/v1/join/{invitation['token']}",
                json={"display_name": "Guest", "pin": "4821"},
            )
            assert response.status_code == 404
            assert "campaign" not in response.text.lower()

            with pytest.raises(IntegrityError):
                await repository.rotate_invite(
                    room.id,
                    owner_id,
                    hashlib.sha256(rotated["token"].encode("utf-8")).hexdigest(),
                    datetime.now(UTC) + timedelta(hours=1),
                )
            async with engine.connect() as connection:
                rotated_revoked_at = await connection.scalar(
                    text(
                        """
                        select revoked_at from app.room_join_tokens
                        where token_hash = :token_hash
                        """
                    ),
                    {
                        "token_hash": hashlib.sha256(
                            rotated["token"].encode("utf-8")
                        ).hexdigest()
                    },
                )
            assert rotated_revoked_at is None
            response = await client.post(
                f"/api/v1/join/{rotated['token']}",
                json={"display_name": "Guest", "pin": "4821", "role": "gm"},
            )
            assert response.status_code == 200
            guest_id = response.json()["participant"]["id"]
            assert response.json()["participant"]["role"] == "player"
            assert response.json()["room"]["can_manage"] is False
            assert client.cookies.get(GUEST_COOKIE)

            response = await client.get(f"/api/v1/join/{rotated['token']}/session")
            assert response.status_code == 200
            assert response.json()["participant"]["id"] == guest_id

            response = await client.patch(
                f"/api/v1/rooms/{room.id}/access", json={"is_locked": True}
            )
            assert response.status_code == 200
            response = await client.post(
                f"/api/v1/rooms/{room.id}/invites", json={"expires_in_minutes": 60}
            )
            locked_invite = response.json()
            response = await client.post(
                f"/api/v1/join/{locked_invite['token']}",
                json={"display_name": "Late guest", "pin": "4821"},
            )
            assert response.status_code == 423
            assert response.json()["detail"]["code"] == "room_locked"

            response = await client.patch(
                f"/api/v1/rooms/{room.id}/access", json={"is_locked": False}
            )
            assert response.status_code == 200
            response = await client.delete(f"/api/v1/rooms/{room.id}/invites")
            assert response.status_code == 204
            response = await client.post(
                f"/api/v1/join/{locked_invite['token']}",
                json={"display_name": "Late guest", "pin": "4821"},
            )
            assert response.status_code == 404
            assert response.json()["detail"]["code"] == "invalid_invite"

            expired_secret = f"expired-{owner_id}"
            await repository.issue_invite(
                room.id,
                owner_id,
                hashlib.sha256(expired_secret.encode()).hexdigest(),
                datetime.now(UTC) - timedelta(minutes=1),
            )
            response = await client.post(
                f"/api/v1/join/{expired_secret}",
                json={"display_name": "Late guest", "pin": "4821"},
            )
            assert response.status_code == 404
            assert response.json()["detail"]["code"] == "invalid_invite"

            second = await service.create_campaign(owner_identity, "Second campaign", "neutral")
            second_gm = await repository.resolve_registered(owner_id, second.rooms[0].id)
            second_invite = await service.issue_invite(second_gm, second.rooms[0].id, 60)
            second_guest, _second_room, _second_secret = await service.join_guest(
                second_invite.token, "Other room guest", None
            )
            response = await client.get(f"/api/v1/join/{second_invite.token}/session")
            assert response.status_code == 401
            assert response.json()["detail"]["code"] == "invalid_guest_session"

            response = await client.get(f"/api/v1/rooms/{room.id}/participants")
            assert response.status_code == 200
            participant_ids = {item["id"] for item in response.json()["participants"]}
            assert str(second_guest.id) not in participant_ids

            response = await client.delete(
                f"/api/v1/rooms/{room.id}/participants/{gm.id}"
            )
            assert response.status_code == 403
            response = await client.delete(
                f"/api/v1/rooms/{room.id}/participants/{second_guest.id}"
            )
            assert response.status_code == 403
            async with engine.connect() as connection:
                protected_participants = (
                    await connection.execute(
                        text(
                            """
                            select id, removed_at from app.participants
                            where id in (:gm, :other_room_guest)
                            """
                        ),
                        {"gm": gm.id, "other_room_guest": second_guest.id},
                    )
                ).mappings().all()
            assert {item["id"] for item in protected_participants} == {
                gm.id,
                second_guest.id,
            }
            assert all(item["removed_at"] is None for item in protected_participants)
            response = await client.delete(
                f"/api/v1/rooms/{room.id}/participants/{guest_id}"
            )
            assert response.status_code == 204
            response = await client.get(f"/api/v1/rooms/{room.id}/participants")
            assert response.status_code == 200
            remaining_ids = {item["id"] for item in response.json()["participants"]}
            assert str(gm.id) in remaining_ids
            assert guest_id not in remaining_ids
            response = await client.get(f"/api/v1/join/{rotated['token']}/session")
            assert response.status_code == 401
            async with engine.connect() as connection:
                removed_state = (
                    await connection.execute(
                        text(
                            """
                            select p.removed_at, s.revoked_at
                            from app.participants p
                            join app.guest_sessions s on s.participant_id = p.id
                            where p.id = :participant
                            """
                        ),
                        {"participant": guest_id},
                    )
                ).one()
            assert removed_state.removed_at is not None
            assert removed_state.revoked_at is not None
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("delete from app.campaigns where owner_user_id = :owner"),
                {"owner": owner_id},
            )
            await connection.execute(
                text("delete from auth.users where id in (:owner, :player, :co_gm)"),
                {"owner": owner_id, "player": player_id, "co_gm": co_gm_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_signed_registered_join_refresh_and_management_use_persisted_room_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(_async_database_url(DATABASE_URL))
    service = CampaignService(PostgresCampaignRepository(DATABASE_URL))
    owner_id, player_id, outsider_id = uuid4(), uuid4(), uuid4()
    settings = Settings(
        environment="test",
        database_url=DATABASE_URL,
        supabase_url="https://vtt-auth.example.invalid",
        _env_file=None,
    )
    private_key = ec.generate_private_key(ec.SECP256R1())
    verifier = SupabaseJWTVerifier(
        issuer=str(settings.supabase_issuer),
        audience="authenticated",
        signing_key_resolver=lambda _token: private_key.public_key(),
    )
    monkeypatch.setattr(auth_dependencies, "build_verifier", lambda *_args: verifier)

    def headers(user_id: UUID) -> dict[str, str]:
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "iss": settings.supabase_issuer,
                "aud": "authenticated",
                "sub": str(user_id),
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
                "user_metadata": {"role": "gm"},
            },
            private_key,
            algorithm="ES256",
        )
        return {"Authorization": f"Bearer {token}"}

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                insert into auth.users (id, email, raw_user_meta_data)
                values (:owner, 'gm@example.invalid', '{"display_name":"GM"}'::jsonb),
                       (:player, 'player@example.invalid', '{"display_name":"Player"}'::jsonb),
                       (:outsider, 'outsider@example.invalid', '{"display_name":"Outsider"}'::jsonb)
                """
            ),
            {"owner": owner_id, "player": player_id, "outsider": outsider_id},
        )
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_campaign_service] = lambda: service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            first = await client.post(
                "/api/v1/campaigns", headers=headers(owner_id),
                json={"name": "First room", "system_id": "neutral"},
            )
            second = await client.post(
                "/api/v1/campaigns", headers=headers(owner_id),
                json={"name": "Second room", "system_id": "neutral"},
            )
            assert first.status_code == second.status_code == 201
            first_room = first.json()["rooms"][0]["id"]
            second_room = second.json()["rooms"][0]["id"]
            invitations = []
            for room_id in (first_room, second_room):
                invitation = await client.post(
                    f"/api/v1/rooms/{room_id}/invites", headers=headers(owner_id),
                    json={"expires_in_minutes": 60},
                )
                assert invitation.status_code == 200
                invitations.append(invitation.json()["token"])

            joined = await client.post(
                f"/api/v1/join/{invitations[0]}/registered", headers=headers(player_id),
                json={"display_name": "Ирина", "role": "gm"},
            )
            assert joined.status_code == 200
            participant_id = joined.json()["participant"]["id"]
            assert joined.json()["participant"]["role"] == "player"
            assert joined.json()["room"]["can_manage"] is False
            restored = await client.get(
                f"/api/v1/join/{invitations[0]}/session", headers=headers(player_id),
            )
            assert restored.status_code == 200
            assert restored.json()["participant"]["id"] == participant_id
            assert restored.json()["participant"]["role"] == "player"
            other_room = await client.get(
                f"/api/v1/join/{invitations[1]}/session", headers=headers(player_id),
            )
            assert other_room.status_code == 403
            for user_id, room_id in (
                (player_id, first_room), (player_id, second_room), (outsider_id, first_room)
            ):
                denied = await client.patch(
                    f"/api/v1/rooms/{room_id}/access", headers=headers(user_id),
                    json={"is_locked": True},
                )
                assert denied.status_code == 403
            guest = await client.post(
                f"/api/v1/join/{invitations[0]}", json={"display_name": "Гость"},
            )
            assert guest.status_code == 200
            denied_guest = await client.patch(
                f"/api/v1/rooms/{first_room}/access", json={"is_locked": True},
            )
            assert denied_guest.status_code == 403
            permitted = await client.patch(
                f"/api/v1/rooms/{first_room}/access", headers=headers(owner_id),
                json={"is_locked": True},
            )
            assert permitted.status_code == 200
            assert permitted.json()["is_locked"] is True
            assert permitted.json()["can_manage"] is True
            rejoined_gm = await client.post(
                f"/api/v1/join/{invitations[1]}/registered", headers=headers(owner_id),
                json={"display_name": "GM"},
            )
            assert rejoined_gm.status_code == 200
            assert rejoined_gm.json()["participant"]["role"] == "gm"
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("delete from app.campaigns where owner_user_id = :owner"),
                {"owner": owner_id},
            )
            await connection.execute(
                text("delete from auth.users where id in (:owner, :player, :outsider)"),
                {"owner": owner_id, "player": player_id, "outsider": outsider_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_migration_preserves_historical_actor_without_restoring_membership() -> None:
    assert DATABASE_URL is not None
    connection = await asyncpg.connect(DATABASE_URL)
    transaction = connection.transaction()
    await transaction.start()
    suffix = uuid4().hex
    namespaces = {name: f"migration_{name}_{suffix}" for name in ("app", "auth", "storage")}

    def isolated(source: str) -> str:
        for original, replacement in namespaces.items():
            source = re.sub(rf"\b{original}\b", replacement, source)
        return source

    owner_id, player_id, former_id, room_id = uuid4(), uuid4(), uuid4(), uuid4()
    try:
        await connection.execute(isolated("""
            create schema auth;
            create schema storage;
            create table auth.users (
              id uuid primary key, email text,
              raw_user_meta_data jsonb not null default '{}'::jsonb
            );
            create table storage.buckets (
              id text primary key, name text, public boolean,
              file_size_limit bigint, allowed_mime_types text[]
            );
        """))
        await connection.execute(isolated(
            (ROOT / "supabase/migrations/20260804123229_initial_app_schema.sql").read_text()
        ))
        await connection.executemany(
            isolated("insert into auth.users (id, email) values ($1, $2)"),
            [(owner_id, "owner@example.invalid"), (player_id, "player@example.invalid"),
             (former_id, "former@example.invalid")],
        )
        await connection.execute(
            isolated("insert into app.rooms (id, owner_user_id, name) values ($1, $2, $3)"),
            room_id, owner_id, "Migration regression",
        )
        await connection.executemany(
            isolated("insert into app.room_members (room_id, user_id) values ($1, $2)"),
            [(room_id, player_id), (room_id, former_id)],
        )
        await connection.executemany(
            isolated("""
                insert into app.room_events (room_id, actor_user_id, event_type)
                values ($1, $2, 'token.moved')
            """),
            [(room_id, player_id), (room_id, former_id)],
        )
        await connection.execute(
            isolated("delete from app.room_members where room_id = $1 and user_id = $2"),
            room_id, former_id,
        )
        await connection.execute(isolated(
            (ROOT / "supabase/migrations/20260903174327_campaigns_guests.sql").read_text()
        ))
        participants = await connection.fetch(isolated("""
            select id, campaign_id, room_id, user_id, role::text as role,
                   display_name, joined_at, removed_at
            from app.participants
        """))
        actors = {row["user_id"]: Participant.model_validate(dict(row)) for row in participants}
        assert actors[owner_id].removed_at is None
        assert actors[owner_id].role.value == "gm"
        assert actors[player_id].removed_at is None
        assert actors[former_id].removed_at is not None
        assert authorize(actors[former_id], Action.VIEW_ROOM, room_id).allowed is False
        mapped_events = await connection.fetchval(isolated("""
            select count(*) from app.room_events e
            join app.participants p
              on p.id = e.actor_participant_id and p.room_id = e.room_id
            where p.user_id = e.actor_user_id
        """))
        assert mapped_events == 2
    finally:
        await transaction.rollback()
        await connection.close()
