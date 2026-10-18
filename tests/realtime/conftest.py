import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg
import pytest
from app.campaigns.dependencies import get_campaign_service
from app.campaigns.repository import PostgresCampaignRepository
from app.campaigns.service import CampaignService
from app.config import Settings, get_settings
from app.identity.dependencies import resolve_room_actor
from app.identity.models import Participant
from app.main import create_app
from app.scenes.dependencies import get_scene_service
from app.scenes.repository import SceneRepository
from app.scenes.service import SceneService
from fastapi import Request
from fastapi.testclient import TestClient


@pytest.fixture
def live_table():
    database = os.getenv("VTT_TEST_DATABASE_URL")
    redis = os.getenv("VTT_TEST_REDIS_URL")
    if not database or not redis:
        pytest.skip("local PostgreSQL and Redis required")
    assert urlparse(database).hostname == "127.0.0.1"
    assert urlparse(database).path == "/vtt_ticket01"
    assert urlparse(redis).hostname == "127.0.0.1"
    user, campaign, room, gm_id, player_id, session = [uuid4() for _ in range(6)]
    state = SimpleNamespace(room=room, campaign=campaign, version=0)
    state.gm = Participant(
        id=gm_id,
        campaign_id=campaign,
        room_id=room,
        user_id=user,
        role="gm",
        display_name="GM",
        joined_at=datetime.now(UTC),
        authorization_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    state.player = Participant(
        id=player_id,
        campaign_id=campaign,
        room_id=room,
        guest_session_id=session,
        role="player",
        display_name="Guest",
        joined_at=datetime.now(UTC),
    )
    settings = Settings(environment="test", database_url=database, redis_url=redis, _env_file=None)
    # Domain services below are fixture-owned. Do not start global maintenance
    # engines that could retain connections from another TestClient event loop.
    application = create_app(settings.model_copy(update={"database_url": None}))
    application.dependency_overrides[get_settings] = lambda: settings

    def actor(request: Request):
        return state.player if request.headers.get("x-test-actor") == "player" else state.gm

    application.dependency_overrides[resolve_room_actor] = actor

    async def setup():
        state.db = await asyncpg.connect(database)
        await state.db.execute(
            "insert into auth.users(id,email) values($1,$2)",
            user,
            f"realtime-{user}@example.invalid",
        )
        await state.db.execute(
            "insert into app.campaigns(id,owner_user_id,name) values($1,$2,'Realtime')",
            campaign,
            user,
        )
        await state.db.execute(
            "insert into app.rooms(id,campaign_id,owner_user_id,name) values($1,$2,$3,'Realtime')",
            room,
            campaign,
            user,
        )
        await state.db.execute(
            "insert into app.participants(id,campaign_id,room_id,user_id,role,display_name) "
            "values($1,$2,$3,$4,'gm','GM')",
            gm_id,
            campaign,
            room,
            user,
        )
        await state.db.execute(
            "insert into app.participants(id,campaign_id,room_id,identity_kind,display_name) "
            "values($1,$2,$3,'guest','Guest')",
            player_id,
            campaign,
            room,
        )
        await state.db.execute(
            "insert into app.guest_sessions(id,participant_id,token_hash,expires_at) "
            "values($1,$2,$3,now()+interval '1 hour')",
            session,
            player_id,
            str(uuid4()),
        )
        state.service = SceneService(SceneRepository(database))
        state.campaign_repository = PostgresCampaignRepository(database)
        state.campaign_service = CampaignService(state.campaign_repository)
        application.dependency_overrides[get_campaign_service] = lambda: state.campaign_service
        application.dependency_overrides[get_scene_service] = lambda: state.service

    async def cleanup():
        await state.service.repository.engine.dispose()
        await state.campaign_repository._engine.dispose()
        await state.db.execute("delete from app.campaigns where id=$1", campaign)
        await state.db.execute("delete from auth.users where id=$1", user)
        await state.db.close()

    with TestClient(application) as client:
        state.client = client
        state.portal = client.portal
        client.portal.call(setup)
        state.url = f"/api/v1/rooms/{room}"

        def command(kind, payload, player=False, version=None):
            body = {
                "command_id": str(uuid4()),
                "room_id": str(room),
                "actor_session_id": str(session if player else gm_id),
                "expected_aggregate_version": state.version if version is None else version,
                "type": kind,
                "payload": payload,
                "client_sent_at": datetime.now(UTC).isoformat(),
            }
            response = client.post(
                state.url + "/scene/commands",
                json=body,
                headers={"x-test-actor": "player" if player else "gm"},
            )
            result = response.json()
            if result["status"] == "accepted":
                state.version = result["aggregate_version"]
            return body, result

        def ticket(player=False):
            response = client.post(
                state.url + "/realtime/ticket",
                headers={"x-test-actor": "player" if player else "gm"},
            )
            assert response.status_code == 200
            return response.json()["ticket"]

        state.command, state.ticket = command, ticket
        try:
            yield state
        finally:
            client.portal.call(cleanup)
