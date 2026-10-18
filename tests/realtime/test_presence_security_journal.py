"""Actor leases and observed connection journal through real public transports."""

import asyncio
import threading
import time
from uuid import UUID

import pytest
import test_room_security_journal as shared_fixtures
from redis.exceptions import RedisError
from starlette.websockets import WebSocketDisconnect

security_table = shared_fixtures.security_table


def status(t):
    response = t.client.get(t.url + "/participants/status", headers=t.gm_headers)
    assert response.status_code == 200
    return {row["id"]: row for row in response.json()["participants"]}


def test_membership_revoked_during_open_audit_never_receives_cached_sync(
    security_table, monkeypatch
):
    t = security_table
    guest = t.client.post("/api/v1/join/" + t.invite, json={"display_name": "Revoke gate"}).json()[
        "participant"
    ]
    ticket = t.ticket(True)
    waiting, released = threading.Event(), threading.Event()
    original = t.repository.connection_event

    async def gated(actor, event_type, reason):
        if event_type == "connection.opened":
            waiting.set()
            for _ in range(500):
                if released.is_set():
                    break
                await asyncio.sleep(0.01)
            assert released.is_set(), "owned concurrency gate timed out"
        await original(actor, event_type, reason)

    with monkeypatch.context() as patch:
        patch.setattr(t.repository, "connection_event", gated)
        with t.client.websocket_connect(t.url + "/realtime/ws") as ws:
            ws.send_json({"type": "subscribe", "ticket": ticket, "cursor": 0})
            try:
                assert waiting.wait(5), "authorized socket did not reach durable-open gate"
                assert (
                    t.client.delete(
                        t.url + "/participants/" + guest["id"], headers=t.gm_headers
                    ).status_code
                    == 204
                )
            finally:
                released.set()
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 4403
    events = t.client.get(t.url + "/security-events", headers=t.gm_headers).json()["events"]
    assert [e["type"] for e in reversed(events)] == [
        "participant.joined",
        "connection.opened",
        "connection.closed",
    ]
    assert all(e["participant_id"] == guest["id"] for e in events)

    async def leases():
        return [
            key
            async for key in t.client.app.state.realtime.redis.scan_iter(f"vtt:presence:{t.room}:*")
        ]

    assert t.portal.call(leases) == []


def test_actor_sockets_deduplicate_close_and_journal_remaining_status(security_table):
    t = security_table
    guest = t.client.post("/api/v1/join/" + t.invite, json={"display_name": "Multi socket"}).json()[
        "participant"
    ]
    assert status(t)[guest["id"]]["connection_status"] == "disconnected"
    before = t.client.get(t.url + "/scene", headers=t.gm_headers).json()
    with t.client.websocket_connect(t.url + "/realtime/ws") as one:
        one.send_json({"type": "subscribe", "ticket": t.ticket(True), "cursor": 0})
        assert one.receive_json()["type"] == "sync"
        with t.client.websocket_connect(t.url + "/realtime/ws") as two:
            two.send_json({"type": "subscribe", "ticket": t.ticket(True), "cursor": 0})
            assert two.receive_json()["type"] == "sync"
            assert status(t)[guest["id"]]["connection_status"] == "connected"
            assert len(status(t)) == 2
            one.send_json({"type": "ping"})
            heartbeat = one.receive_json()
            assert heartbeat == {"type": "heartbeat", "presence_count": 1}
        assert status(t)[guest["id"]]["connection_status"] == "connected"
    for _ in range(100):
        if status(t)[guest["id"]]["connection_status"] == "disconnected":
            break
        time.sleep(0.01)
    assert status(t)[guest["id"]]["connection_status"] == "disconnected"
    events = t.client.get(t.url + "/security-events", headers=t.gm_headers).json()["events"]
    assert [e["type"] for e in reversed(events)] == [
        "participant.joined",
        "connection.opened",
        "connection.opened",
        "connection.closed",
        "connection.closed",
    ]
    closes = [e for e in events if e["type"] == "connection.closed"]
    assert {e["reason"] for e in closes} == {
        "socket_closed_actor_connected",
        "socket_closed_actor_disconnected",
    }
    after = t.client.get(t.url + "/scene", headers=t.gm_headers).json()
    assert (before["aggregate_version"], before["event_cursor"]) == (
        after["aggregate_version"],
        after["event_cursor"],
    )
    assert t.client.get(t.url + "/participants/status").status_code == 403


def test_active_assignments_and_redis_failure_unknown(security_table, monkeypatch):
    t = security_table
    guest = t.client.post("/api/v1/join/" + t.invite, json={"display_name": "Assigned"}).json()[
        "participant"
    ]
    assert status(t)[guest["id"]]["assigned_tokens"] == []
    t.command("scene.create", {"name": "Active"}, 0)
    t.command(
        "item.create",
        {"kind": "token", "name": "Active token", "owner_participant_id": guest["id"]},
        1,
    )
    token = t.client.get(t.url + "/scene", headers=t.gm_headers).json()["items"][0]
    assigned = status(t)[guest["id"]]["assigned_tokens"]
    assert assigned == [
        {
            "id": token["id"],
            "name": "Active token",
            "scene_id": t.client.get(t.url + "/scene", headers=t.gm_headers).json()["scene"]["id"],
            "scene_name": "Active",
        }
    ]
    t.command("item.delete", {"item_id": token["id"]}, 2)
    assert status(t)[guest["id"]]["assigned_tokens"] == []

    async def unavailable(*_, **__):
        raise RedisError("synthetic unavailable")

    async def failing():
        raise RedisError("synthetic unavailable")
        yield

    with monkeypatch.context() as patch:
        patch.setattr(t.client.app.state.realtime.redis, "mget", unavailable)
        patch.setattr(t.client.app.state.realtime.redis, "scan_iter", lambda *_: failing())
        assert {row["connection_status"] for row in status(t).values()} == {"unknown"}
    assert (
        t.client.get(
            f"/api/v1/rooms/{UUID(int=1)}/participants/status", headers=t.gm_headers
        ).status_code
        == 403
    )
