from __future__ import annotations

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from app.campaigns.repository import PostgresCampaignRepository
from app.config import Settings, get_settings
from app.identity.dependencies import resolve_room_actor
from app.identity.models import Participant
from app.main import create_app
from app.scenes.dependencies import get_scene_service
from app.scenes.models import Command
from app.scenes.repository import SceneRepository
from app.scenes.service import SceneService
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def table():
    database = os.getenv("VTT_TEST_DATABASE_URL")
    if not database:
        pytest.skip("local PostgreSQL not configured")
    destination = urlparse(database)
    assert destination.hostname in {"localhost", "127.0.0.1"}
    assert destination.path == "/vtt_ticket01"
    connection = await asyncpg.connect(database)
    user, campaign, room, guest, session = [uuid4() for _ in range(5)]
    campaigns = None
    service = None
    try:
        await connection.execute(
            "insert into auth.users(id,email) values($1,$2)", user, f"cards-{user}@example.invalid"
        )
        await connection.execute(
            "insert into app.campaigns(id,owner_user_id,name) values($1,$2,'Cards')", campaign, user
        )
        await connection.execute(
            "insert into app.rooms(id,campaign_id,owner_user_id,name) values($1,$2,$3,'Cards')",
            room,
            campaign,
            user,
        )
        await connection.execute(
            "insert into app.participants(campaign_id,room_id,user_id,role,display_name) "
            "values($1,$2,$3,'gm','GM')",
            campaign,
            room,
            user,
        )
        await connection.execute(
            "insert into app.participants(id,campaign_id,room_id,identity_kind,display_name) "
            "values($1,$2,$3,'guest','Guest')",
            guest,
            campaign,
            room,
        )
        await connection.execute(
            "insert into app.guest_sessions(id,participant_id,token_hash,expires_at) "
            "values($1,$2,$3,now()+interval '1 hour')",
            session,
            guest,
            str(uuid4()),
        )
        campaigns = PostgresCampaignRepository(database)
        gm = await campaigns.resolve_registered(user, room)
        player = Participant(
            id=guest,
            campaign_id=campaign,
            room_id=room,
            role="player",
            display_name="Guest",
            guest_session_id=session,
            joined_at=datetime.now(UTC),
        )
        service = SceneService(SceneRepository(database))
        settings = Settings(environment="test", database_url=database, _env_file=None)
        app = create_app(settings)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_scene_service] = lambda: service
        state = SimpleNamespace(
            app=app,
            gm=gm,
            player=player,
            actor=gm,
            room=room,
            campaign=campaign,
            connection=connection,
            service=service,
            version=0,
        )
        app.dependency_overrides[resolve_room_actor] = lambda: state.actor
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            state.client = client
            state.url = f"/api/v1/rooms/{room}"

            async def execute(kind, payload, actor=None, expected=None):
                actor = actor or state.actor
                command = Command(
                    command_id=uuid4(),
                    room_id=room,
                    actor_session_id=actor.guest_session_id or actor.id,
                    expected_aggregate_version=state.version if expected is None else expected,
                    type=kind,
                    payload=payload,
                    client_sent_at=datetime.now(UTC),
                )
                result = await service.execute_scene_command(actor, command)
                if result.status == "accepted":
                    state.version = result.aggregate_version
                return command, result

            state.execute = execute
            yield state
    finally:
        if service is not None:
            await service.repository.engine.dispose()
        if campaigns is not None:
            await campaigns._engine.dispose()
        try:
            await connection.execute("delete from app.campaigns where id=$1", campaign)
            await connection.execute("delete from auth.users where id=$1", user)
        finally:
            await connection.close()
