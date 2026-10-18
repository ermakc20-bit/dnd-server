from __future__ import annotations

import hashlib
import os
from io import BytesIO
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from app.campaigns.dependencies import get_campaign_service
from app.campaigns.repository import PostgresCampaignRepository
from app.campaigns.service import CampaignService
from app.config import Settings, get_settings
from app.identity import dependencies as identity_dependencies
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from PIL import Image

DATABASE_URL = os.getenv("VTT_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="local PostgreSQL not configured")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image_format,mime",
    [
        ("PNG", "image/png"),
        ("JPEG", "image/jpeg"),
        ("WEBP", "image/webp"),
        ("AVIF", "image/avif"),
    ],
)
async def test_private_image_upload_and_role_scoped_download(
    image_format: str,
    mime: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert DATABASE_URL is not None
    connection = await asyncpg.connect(DATABASE_URL)
    owner, campaign, room, guest, session = (uuid4() for _ in range(5))
    await connection.execute(
        "insert into auth.users(id,email) values($1,$2)", owner, f"asset-{owner}@example.invalid"
    )
    await connection.execute(
        "insert into app.campaigns(id,owner_user_id,name) values($1,$2,'Assets')", campaign, owner
    )
    await connection.execute(
        """insert into app.rooms(id,campaign_id,owner_user_id,name)
        values($1,$2,$3,'Assets')""",
        room,
        campaign,
        owner,
    )
    await connection.execute(
        """insert into app.participants
        (campaign_id,room_id,user_id,role,display_name) values($1,$2,$3,'gm','GM')""",
        campaign,
        room,
        owner,
    )
    await connection.execute(
        """insert into app.participants
        (id,campaign_id,room_id,identity_kind,display_name) values($1,$2,$3,'guest','Guest')""",
        guest,
        campaign,
        room,
    )
    await connection.execute(
        """insert into app.guest_sessions(id,participant_id,token_hash,expires_at)
        values($1,$2,$3,now()+interval '1 hour')""",
        session,
        guest,
        hashlib.sha256(b"local-asset-guest").hexdigest(),
    )
    settings = Settings(environment="test", database_url=DATABASE_URL, _env_file=None)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_campaign_service] = lambda: CampaignService(
        PostgresCampaignRepository(DATABASE_URL),
    )
    from app.assets.dependencies import get_asset_service
    from app.assets.service import AssetService
    from app.assets.storage import MemoryStorage

    storage = MemoryStorage()
    asset_service = AssetService(DATABASE_URL, storage)
    application.dependency_overrides[get_asset_service] = lambda: asset_service
    # Locally verified JWT-like fixture maps only the exact credential to identity;
    # the scene HTTP suite independently checks cryptographic JWT verification.
    from app.auth.jwt import AuthenticationError

    class Verifier:
        def verify(self, token: str):
            if token != "local-gm":  # noqa: S105 - non-secret isolated test credential
                raise AuthenticationError("invalid test credential")
            from datetime import UTC, datetime, timedelta

            from app.auth.jwt import AuthIdentity

            return AuthIdentity(
                user_id=owner,
                email="local@example.invalid",
                audience="authenticated",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )

    monkeypatch.setattr(identity_dependencies, "get_verifier", lambda _settings: Verifier())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            content = BytesIO()
            Image.new("RGB", (3, 2), (40, 80, 120)).save(content, format=image_format)
            body = content.getvalue()
            headers = {"Authorization": "Bearer local-gm"}
            response = await client.post(
                f"/api/v1/rooms/{room}/assets/prepare",
                headers=headers,
                json={"name": "Map", "content_type": mime, "byte_size": len(body), "kind": "map"},
            )
            assert response.status_code == 201
            asset = response.json()
            assert "object_key" not in asset and "owner_user_id" not in asset

            response = await client.put(
                asset["upload_url"], content=body, headers={**headers, "Content-Type": mime}
            )
            assert response.status_code == 200 and response.json()["status"] == "ready"
            assert response.json()["width"] == 3 and response.json()["height"] == 2
            download = await client.get(
                f"/api/v1/rooms/{room}/assets/{asset['id']}/download", headers=headers
            )
            assert download.status_code == 200 and download.json()["expires_in"] == 60
            assert "/object/public/" not in download.json()["url"]
            assert storage.put_count == 1

            # Real decoding, MIME disagreement, corruption and bomb protection all run
            # through server-authorized HTTP uploads, not a permissive test provider.
            for invalid_body, invalid_mime in (
                (b"not an image", mime),
                (body[:-10], mime),
                (body, "image/jpeg" if mime != "image/jpeg" else "image/png"),
            ):
                prepared = await client.post(
                    f"/api/v1/rooms/{room}/assets/prepare",
                    headers=headers,
                    json={
                        "name": "Invalid",
                        "content_type": invalid_mime,
                        "byte_size": len(invalid_body),
                        "kind": "map",
                    },
                )
                assert prepared.status_code == 201
                invalid_asset = prepared.json()
                rejected = await client.put(
                    invalid_asset["upload_url"],
                    content=invalid_body,
                    headers={**headers, "Content-Type": invalid_mime},
                )
                assert (
                    rejected.status_code == 400
                    and rejected.json()["detail"]["code"] == "invalid_asset"
                )
                assert (
                    await connection.fetchval(
                        "select status from app.assets where id=$1", UUID(invalid_asset["id"])
                    )
                    == "pending"
                )
            bomb = BytesIO()
            Image.new("RGB", (16, 16)).save(bomb, format=image_format)
            bomb_data = bomb.getvalue()
            prepared = await client.post(
                f"/api/v1/rooms/{room}/assets/prepare",
                headers=headers,
                json={
                    "name": "Bomb",
                    "content_type": mime,
                    "byte_size": len(bomb_data),
                    "kind": "map",
                },
            )
            with monkeypatch.context() as patch:
                patch.setattr(Image, "MAX_IMAGE_PIXELS", 1)
                rejected = await client.put(
                    prepared.json()["upload_url"],
                    content=bomb_data,
                    headers={**headers, "Content-Type": mime},
                )
                assert rejected.status_code == 400
            await client.put(
                asset["upload_url"], content=body, headers={**headers, "Content-Type": mime}
            )
            assert storage.put_count == 1

            for bad_mime, bad_size in (("image/svg+xml", 1), (mime, 52428801), (mime, 0)):
                denied = await client.post(
                    f"/api/v1/rooms/{room}/assets/prepare",
                    headers=headers,
                    json={
                        "name": "Bad",
                        "content_type": bad_mime,
                        "byte_size": bad_size,
                        "kind": "map",
                    },
                )
                assert denied.status_code in (400, 422)
            client.cookies.set("vtt_guest_session", "local-asset-guest")
            assert (
                await client.get(f"/api/v1/rooms/{room}/assets/{asset['id']}/download")
            ).status_code == 403
            assert (
                await client.post(
                    f"/api/v1/rooms/{room}/assets/prepare",
                    json={"name": "Denied", "content_type": mime, "byte_size": 1, "kind": "map"},
                )
            ).status_code == 403
            # Exposing an asset only through a hidden item cannot grant a player access.
            from datetime import UTC, datetime

            from app.scenes.models import Command
            from app.scenes.repository import SceneRepository
            from app.scenes.service import SceneService

            gm = await PostgresCampaignRepository(DATABASE_URL).resolve_registered(owner, room)
            scenes = SceneService(SceneRepository(DATABASE_URL))
            for version, kind, payload in (
                (0, "scene.create", {"name": "Map scene"}),
                (
                    1,
                    "item.create",
                    {
                        "kind": "map",
                        "name": "Hidden map",
                        "asset_id": asset["id"],
                        "visibility": "gm_only",
                    },
                ),
            ):
                result = await scenes.execute_scene_command(
                    gm,
                    Command(
                        command_id=uuid4(),
                        room_id=room,
                        actor_session_id=gm.id,
                        expected_aggregate_version=version,
                        type=kind,
                        payload=payload,
                        client_sent_at=datetime.now(UTC),
                    ),
                )
                assert result.status == "accepted"
            assert (
                await client.get(f"/api/v1/rooms/{room}/assets/{asset['id']}/download")
            ).status_code == 403
            state = await scenes.repository.get_projection(gm, room)
            result = await scenes.execute_scene_command(
                gm,
                Command(
                    command_id=uuid4(),
                    room_id=room,
                    actor_session_id=gm.id,
                    expected_aggregate_version=2,
                    type="item.update",
                    payload={"item_id": str(state.items[0].id), "visibility": "everyone"},
                    client_sent_at=datetime.now(UTC),
                ),
            )
            assert result.status == "accepted"
            assert (
                await client.get(f"/api/v1/rooms/{room}/assets/{asset['id']}/download")
            ).status_code == 200
            result = await scenes.execute_scene_command(
                gm,
                Command(
                    command_id=uuid4(),
                    room_id=room,
                    actor_session_id=gm.id,
                    expected_aggregate_version=3,
                    type="scene.create",
                    payload={"name": "Another scene"},
                    client_sent_at=datetime.now(UTC),
                ),
            )
            assert result.status == "accepted"
            assert (
                await client.get(f"/api/v1/rooms/{room}/assets/{asset['id']}/download")
            ).status_code == 403
            assert (
                await connection.fetchval(
                    "select status from app.assets where id=$1", UUID(asset["id"])
                )
                == "ready"
            )

            from app.assets import storage as storage_module
            from app.assets.storage import SupabasePrivateStorage

            original_client = httpx.AsyncClient
            provider_requests = []
            malformed = False

            def provider(request: httpx.Request) -> httpx.Response:
                provider_requests.append(request)
                if "/object/sign/" in request.url.path:
                    return httpx.Response(
                        200,
                        json=[]
                        if malformed
                        else {
                            "signedURL": "/object/sign/vtt-assets/test-object?token=local-fixture",
                        },
                    )
                return httpx.Response(200, json={})

            with monkeypatch.context() as patch:
                patch.setattr(
                    storage_module.httpx,
                    "AsyncClient",
                    lambda **_kwargs: original_client(transport=httpx.MockTransport(provider)),
                )
                asset_service.storage = SupabasePrivateStorage(
                    "https://storage-fixture.invalid", "fixture-only"
                )
                prepared = await client.post(
                    f"/api/v1/rooms/{room}/assets/prepare",
                    headers=headers,
                    json={
                        "name": "Provider contract",
                        "content_type": mime,
                        "byte_size": len(body),
                        "kind": "map",
                    },
                )
                uploaded = await client.put(
                    prepared.json()["upload_url"],
                    content=body,
                    headers={**headers, "Content-Type": mime},
                )
                assert uploaded.status_code == 200
                grant = await client.get(
                    f"/api/v1/rooms/{room}/assets/{asset['id']}/download", headers=headers
                )
                assert grant.status_code == 200 and "/object/sign/" in grant.json()["url"]
                assert provider_requests[0].url.path.startswith("/storage/v1/object/vtt-assets/")
                assert provider_requests[0].content == body
                assert provider_requests[-1].content == b'{"expiresIn":60}'
                malformed = True
                unavailable = await client.get(
                    f"/api/v1/rooms/{room}/assets/{asset['id']}/download", headers=headers
                )
                assert unavailable.status_code == 503
                assert unavailable.json()["detail"]["code"] == "asset_unavailable"
            asset_service.storage = storage
            storage.unavailable = True
            retry_metadata = await client.post(
                f"/api/v1/rooms/{room}/assets/prepare",
                headers=headers,
                json={"name": "Retry", "content_type": mime, "byte_size": len(body), "kind": "map"},
            )
            retry_url = retry_metadata.json()["upload_url"]
            failed_upload = await client.put(
                retry_url, content=body, headers={**headers, "Content-Type": mime}
            )
            assert failed_upload.status_code == 503
            assert (
                await connection.fetchval(
                    "select status from app.assets where id=$1", UUID(retry_metadata.json()["id"])
                )
                == "pending"
            )
            assert (
                await client.get(
                    f"/api/v1/rooms/{room}/assets/{asset['id']}/download", headers=headers
                )
            ).status_code == 503
            assert (
                await connection.fetchval(
                    "select name from app.assets where id=$1", UUID(asset["id"])
                )
                == "Map"
            )
            storage.unavailable = False
            retried = await client.put(
                retry_url, content=body, headers={**headers, "Content-Type": mime}
            )
            assert (
                retried.status_code == 200 and retried.json()["id"] == retry_metadata.json()["id"]
            )
            await scenes.repository.engine.dispose()
    finally:
        await asset_service.engine.dispose()
        await connection.execute("delete from app.campaigns where id=$1", campaign)
        await connection.execute("delete from auth.users where id=$1", owner)
        await connection.close()
