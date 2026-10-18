"""Public HTTP/WS regressions, real synthetic JWT and exact owned fixture cleanup."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import asyncpg
import jwt
import pytest
from app.auth import dependencies as auth_dependencies
from app.auth.jwt import SupabaseJWTVerifier
from app.campaigns.dependencies import get_campaign_service
from app.campaigns.repository import PostgresCampaignRepository
from app.campaigns.service import CampaignService
from app.config import Settings, get_settings
from app.identity import dependencies as identity_dependencies
from app.main import create_app
from app.scenes.dependencies import get_scene_service
from app.scenes.repository import SceneRepository
from app.scenes.service import SceneService
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient


@pytest.fixture
def security_table(monkeypatch):
    database = os.environ["VTT_TEST_DATABASE_URL"]
    redis_url = os.environ["VTT_TEST_REDIS_URL"]
    assert database == "postgresql://postgres@127.0.0.1:55439/vtt_ticket01"
    assert redis_url == "redis://127.0.0.1:56439/15"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = SupabaseJWTVerifier(
        issuer="http://fixture.invalid/auth/v1",
        audience="authenticated",
        signing_key_resolver=lambda _: key.public_key(),
    )
    monkeypatch.setattr(auth_dependencies, "get_verifier", lambda _: verifier)
    monkeypatch.setattr(identity_dependencies, "get_verifier", lambda _: verifier)
    state = SimpleNamespace(users=[uuid4(), uuid4()], campaigns=[], actors=set(), tickets=[])

    def headers(user):
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(user),
                "iss": "http://fixture.invalid/auth/v1",
                "aud": "authenticated",
                "iat": now,
                "exp": now + timedelta(hours=1),
            },
            key,
            algorithm="RS256",
        )
        return {"Authorization": "Bearer " + token}

    state.headers = headers
    state.gm_headers = headers(state.users[0])
    settings = Settings(
        environment="test", database_url=database, redis_url=redis_url, _env_file=None
    )
    application = create_app(settings.model_copy(update={"database_url": None}))
    application.dependency_overrides[get_settings] = lambda: settings
    with TestClient(application) as client:
        state.client, state.portal = client, client.portal

        async def setup():
            state.db = await asyncpg.connect(database)
            state.repository = PostgresCampaignRepository(database)
            state.service = SceneService(SceneRepository(database))
            application.dependency_overrides[get_campaign_service] = lambda: CampaignService(
                state.repository
            )
            application.dependency_overrides[get_scene_service] = lambda: state.service
            for user in state.users:
                await state.db.execute(
                    "insert into auth.users(id,email) values($1,$2)",
                    user,
                    f"f3-{user}@example.invalid",
                )

        async def cleanup():
            # Only this fixture's UUIDs and Redis keys, including a partially failed setup.
            for user in state.users:
                rooms = await state.db.fetch(
                    "select r.id from app.rooms r join app.campaigns c on c.id=r.campaign_id "
                    "where c.owner_user_id=$1",
                    user,
                )
                actors = await state.db.fetch(
                    "select id from app.participants where campaign_id in "
                    "(select id from app.campaigns where owner_user_id=$1)",
                    user,
                )
                redis = application.state.realtime.redis
                for room in rooms:
                    for prefix in ("vtt:presence:", "vtt:preview:"):
                        keys = [k async for k in redis.scan_iter(f"{prefix}{room['id']}:*")]
                        if keys:
                            await redis.delete(*keys)
                for actor in actors:
                    await redis.delete(
                        f"vtt:rate:{actor['id']}:tickets", f"vtt:rate:{actor['id']}:frames"
                    )
                await state.db.execute("delete from app.campaigns where owner_user_id=$1", user)
                await state.db.execute("delete from auth.users where id=$1", user)
            for ticket in state.tickets:
                await application.state.realtime.redis.delete(
                    application.state.realtime.ticket_key(ticket)
                )
            assert (
                await state.db.fetchval(
                    "select count(*) from auth.users where id=any($1)", state.users
                )
                == 0
            )
            await state.repository._engine.dispose()
            await state.service.repository.engine.dispose()
            await state.db.close()

        try:
            state.portal.call(setup)
            campaign = client.post(
                "/api/v1/campaigns", headers=state.gm_headers, json={"name": "F3 owned"}
            ).json()
            state.campaign, state.room = UUID(campaign["id"]), UUID(campaign["rooms"][0]["id"])
            state.url = f"/api/v1/rooms/{state.room}"
            invite = client.post(state.url + "/invites", headers=state.gm_headers, json={}).json()[
                "token"
            ]
            state.invite = invite
            state.gm = client.get(state.url + "/participants", headers=state.gm_headers).json()[
                "participants"
            ][0]

            def ticket(guest=False):
                response = client.post(
                    state.url + "/realtime/ticket", headers={} if guest else state.gm_headers
                )
                assert response.status_code == 200
                value = response.json()["ticket"]
                state.tickets.append(value)
                return value

            state.ticket = ticket

            def command(kind, payload, version):
                body = {
                    "command_id": str(uuid4()),
                    "room_id": str(state.room),
                    "actor_session_id": state.gm["id"],
                    "expected_aggregate_version": version,
                    "type": kind,
                    "payload": payload,
                    "client_sent_at": datetime.now(UTC).isoformat(),
                }
                result = client.post(
                    state.url + "/scene/commands", headers=state.gm_headers, json=body
                ).json()
                assert result["status"] == "accepted", result
                return result

            state.command = command
            yield state
        finally:
            if hasattr(state, "db"):
                state.portal.call(cleanup)


@pytest.mark.parametrize("endpoint", ["security-events", "participants/status"])
def test_jwt_expiry_after_final_membership_await_denies_private_output(
    security_table, monkeypatch, endpoint
):
    t = security_table
    original_encode = jwt.encode

    def short_lived(claims, *args, **kwargs):
        return original_encode(
            {**claims, "exp": datetime.now(UTC) + timedelta(seconds=2)}, *args, **kwargs
        )

    with monkeypatch.context() as patch:
        patch.setattr(jwt, "encode", short_lived)
        headers = t.headers(t.users[0])
    original = t.repository.resolve_registered
    calls = 0

    async def delayed(user_id, room_id):
        nonlocal calls
        calls += 1
        actor = await original(user_id, room_id)
        if calls == 2:
            await asyncio.sleep(2.2)
        return actor

    with monkeypatch.context() as patch:
        patch.setattr(t.repository, "resolve_registered", delayed)
        response = t.client.get(t.url + "/" + endpoint, headers=headers)
    assert calls == 2
    assert response.status_code in (401, 403)
    assert not ({"events", "participants"} & set(response.json()))
    assert t.client.get(t.url + "/" + endpoint, headers=t.gm_headers).status_code == 200


def test_failed_join_audit_append_rolls_back_membership_and_session(security_table, monkeypatch):
    import app.campaigns.repository as repository_module

    t = security_table
    before = t.portal.call(
        t.db.fetchval, "select count(*) from app.participants where room_id=$1", t.room
    )

    async def unavailable(*_, **__):
        raise RuntimeError("synthetic owned audit append unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(repository_module, "append_security_event", unavailable)
        with pytest.raises(RuntimeError, match="synthetic owned"):
            t.client.post("/api/v1/join/" + t.invite, json={"display_name": "Rollback fixture"})
    assert (
        t.portal.call(
            t.db.fetchval, "select count(*) from app.participants where room_id=$1", t.room
        )
        == before
    )
    assert (
        t.portal.call(
            t.db.fetchval,
            "select count(*) from app.guest_sessions g join app.participants p "
            "on p.id=g.participant_id where p.room_id=$1",
            t.room,
        )
        == 0
    )
    assert t.client.get(t.url + "/security-events", headers=t.gm_headers).json()["events"] == []


def test_actual_joins_are_private_durable_bounded_and_do_not_change_gameplay(security_table):
    t = security_table
    initial = t.client.get(t.url + "/security-events", headers=t.gm_headers)
    assert initial.status_code == 200
    assert initial.json() == {"events": [], "next_before_id": None}
    before = t.client.get(t.url + "/scene", headers=t.gm_headers).json()
    failed = t.client.post("/api/v1/join/not-an-invite", json={"display_name": "not joined"})
    assert failed.status_code == 404
    guest = t.client.post("/api/v1/join/" + t.invite, json={"display_name": "Guest F3"}).json()[
        "participant"
    ]
    registered = t.client.post(
        "/api/v1/join/" + t.invite + "/registered",
        headers=t.headers(t.users[1]),
        json={"display_name": "Registered F3"},
    )
    assert registered.status_code == 200
    response = t.client.get(t.url + "/security-events", headers=t.gm_headers)
    assert response.headers["cache-control"] == "no-store"
    events = response.json()["events"]
    assert len(events) == 2
    assert {e["participant_id"] for e in events} == {
        guest["id"],
        registered.json()["participant"]["id"],
    }
    assert {e["type"] for e in events} == {"participant.joined"}
    assert {e["reason"] for e in events} == {"guest_join", "registered_join"}
    assert all(
        set(e) == {"id", "participant_id", "display_name", "type", "occurred_at", "reason"}
        for e in events
    )
    assert t.invite not in str(events) and guest["guest_session_id"] not in str(events)
    assert t.client.get(t.url + "/security-events").status_code == 403
    assert (
        t.client.get(
            f"/api/v1/rooms/{UUID(int=1)}/security-events", headers=t.gm_headers
        ).status_code
        == 403
    )
    assert (
        t.client.get(t.url + "/security-events", headers=t.headers(t.users[1])).status_code == 403
    )
    assert (
        t.client.get(t.url + "/security-events?limit=101", headers=t.gm_headers).status_code == 422
    )
    one = t.client.get(t.url + "/security-events?limit=1", headers=t.gm_headers).json()
    two = t.client.get(
        t.url + "/security-events?limit=1&before_id=" + str(one["next_before_id"]),
        headers=t.gm_headers,
    ).json()
    assert (
        len(one["events"]) == len(two["events"]) == 1
        and one["events"][0]["id"] != two["events"][0]["id"]
    )
    after = t.client.get(t.url + "/scene", headers=t.gm_headers).json()
    assert (after["aggregate_version"], after["event_cursor"]) == (
        before["aggregate_version"],
        before["event_cursor"],
    )
    assert (
        t.portal.call(
            t.db.fetchval, "select count(*) from app.scene_commands where room_id=$1", t.room
        )
        == 0
    )
    assert (
        t.portal.call(
            t.db.fetchval, "select count(*) from app.room_events where room_id=$1", t.room
        )
        == 0
    )
    # A fresh application/engine must read the committed journal through HTTP.
    repository = PostgresCampaignRepository(os.environ["VTT_TEST_DATABASE_URL"])
    restarted_app = create_app(
        Settings(environment="test", redis_url=os.environ["VTT_TEST_REDIS_URL"], _env_file=None)
    )
    restarted_app.dependency_overrides[get_campaign_service] = lambda: CampaignService(repository)
    with TestClient(restarted_app) as restarted:
        try:
            persisted = restarted.get(t.url + "/security-events", headers=t.gm_headers)
            assert persisted.status_code == 200
            assert persisted.json()["events"] == events
        finally:
            restarted.portal.call(repository._engine.dispose)
