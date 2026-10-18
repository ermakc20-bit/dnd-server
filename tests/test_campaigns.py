from __future__ import annotations

import asyncio
import logging
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import uvicorn
from app.access.policy import Action, authorize
from app.auth.dependencies import get_current_identity
from app.auth.jwt import AuthIdentity
from app.campaigns.dependencies import get_campaign_service
from app.campaigns.models import Campaign, Room
from app.config import Settings, get_settings
from app.identity.models import Participant, ParticipantRole
from app.main import create_app
from fastapi.testclient import TestClient
from httpx import AsyncClient
from uvicorn.logging import AccessFormatter


class CampaignServiceStub:
    def __init__(self, owner_id: UUID) -> None:
        self.owner_id = owner_id

    async def create_campaign(self, actor: AuthIdentity, name: str, system_id: str) -> Campaign:
        assert actor.user_id == self.owner_id
        assert (name, system_id) == ("Туманы Баровии", "neutral")
        now = datetime(2026, 9, 3, tzinfo=UTC)
        room = Room(
            id=UUID("20000000-0000-4000-8000-000000000002"),
            campaign_id=UUID("20000000-0000-4000-8000-000000000001"),
            name="Основной стол",
            is_locked=False,
            pin_enabled=False,
            created_at=now,
            can_manage=True,
        )
        return Campaign(
            id=room.campaign_id,
            owner_user_id=self.owner_id,
            name=name,
            system_id=system_id,
            status="draft",
            created_at=now,
            rooms=[room],
        )


def test_registered_user_creates_campaign_and_first_room() -> None:
    owner_id = uuid4()
    identity = AuthIdentity(
        user_id=owner_id,
        email="gm@example.com",
        audience="authenticated",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    application = create_app()
    application.dependency_overrides[get_current_identity] = lambda: identity
    application.dependency_overrides[get_campaign_service] = lambda: CampaignServiceStub(owner_id)

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/campaigns",
            json={"name": "Туманы Баровии", "system_id": "neutral"},
        )

    assert response.status_code == 201
    assert response.json() == {
        "id": "20000000-0000-4000-8000-000000000001",
        "owner_user_id": str(owner_id),
        "name": "Туманы Баровии",
        "system_id": "neutral",
        "status": "draft",
        "created_at": "2026-09-03T00:00:00Z",
        "rooms": [
            {
                "id": "20000000-0000-4000-8000-000000000002",
                "campaign_id": "20000000-0000-4000-8000-000000000001",
                "name": "Основной стол",
                "is_locked": False,
                "pin_enabled": False,
                "created_at": "2026-09-03T00:00:00Z",
                "can_manage": True,
            }
        ],
    }


def test_guest_credential_cannot_manage_even_with_a_forged_gm_role() -> None:
    room_id = uuid4()
    forged_guest = Participant(
        id=uuid4(),
        campaign_id=uuid4(),
        room_id=room_id,
        role=ParticipantRole.GM,
        display_name="Forged",
        joined_at=datetime.now(UTC),
    )

    decision = authorize(forged_guest, Action.MANAGE_ROOM, room_id)

    assert decision.allowed is False
    assert decision.reason == "registered_gm_required"


def test_remove_participant_requires_a_real_non_gm_target() -> None:
    room_id = uuid4()
    actor = Participant(
        id=uuid4(),
        campaign_id=uuid4(),
        room_id=room_id,
        user_id=uuid4(),
        role=ParticipantRole.GM,
        display_name="Мария",
        joined_at=datetime.now(UTC),
    )
    target_gm = actor.model_copy(update={"id": uuid4()})
    target_player = actor.model_copy(
        update={"id": uuid4(), "user_id": None, "role": ParticipantRole.PLAYER}
    )

    missing_target = authorize(actor, Action.REMOVE_PARTICIPANT, room_id)
    real_gm_target = authorize(actor, Action.REMOVE_PARTICIPANT, room_id, target_gm)
    player_target = authorize(actor, Action.REMOVE_PARTICIPANT, room_id, target_player)

    assert missing_target.allowed is False
    assert missing_target.reason == "participant_target_required"
    assert real_gm_target.allowed is False
    assert real_gm_target.reason == "cannot_remove_gm"
    assert player_target.allowed is True


@pytest.mark.asyncio
async def test_uvicorn_access_log_redacts_join_tokens(
    settings: Settings, caplog: pytest.LogCaptureFixture,
) -> None:
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    marker = "fixture-invite-marker"
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    ready = asyncio.Event()

    class ReadyServer(uvicorn.Server):
        async def startup(self, sockets: list[socket.socket] | None = None) -> None:
            await super().startup(sockets=sockets)
            ready.set()

    server = ReadyServer(uvicorn.Config(
        application, lifespan="off", http="h11", log_config=None,
    ))
    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            await asyncio.wait_for(ready.wait(), timeout=5)
            async with AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
                health = await client.get("/health/live")
                assert health.status_code == 200
                joined = await client.post(
                    f"/api/v1/join/{marker}?token={marker}", json={"display_name": "Guest"},
                )
                assert joined.status_code == 503
                registered = await client.post(
                    f"/api/v1/join/{marker}/registered", json={"display_name": "Player"},
                )
                assert registered.status_code == 401
                restored = await client.get(f"/api/v1/join/{marker}/session")
                assert restored.status_code == 503
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, timeout=5)
            listener.close()
    records = [record for record in caplog.records if record.name == "uvicorn.access"]
    assert len(records) == 4
    formatter = AccessFormatter(
        '%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False,
    )
    output = "\n".join(formatter.format(record) for record in records)
    assert "GET /health/live HTTP/1.1" in output
    assert marker not in output
    assert "POST /api/v1/join/[REDACTED] HTTP/1.1" in output
    assert "POST /api/v1/join/[REDACTED]/registered HTTP/1.1" in output
    assert "GET /api/v1/join/[REDACTED]/session HTTP/1.1" in output
