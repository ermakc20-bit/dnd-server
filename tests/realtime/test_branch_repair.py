"""Public regressions for JWT lifetime and campaign-shared scene convergence."""

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from app.auth.jwt import SupabaseJWTVerifier
from app.config import Settings, get_settings
from app.identity import dependencies as identity_dependencies
from app.identity.dependencies import resolve_room_actor
from app.identity.models import Participant
from app.scenes.models import Command
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from starlette.websockets import WebSocketDisconnect


def authenticated(table, monkeypatch, seconds):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = SupabaseJWTVerifier(
        issuer="http://fixture.invalid/auth/v1",
        audience="authenticated",
        signing_key_resolver=lambda _token: key.public_key(),
    )
    monkeypatch.setattr(identity_dependencies, "get_verifier", lambda _settings: verifier)
    table.client.app.dependency_overrides.pop(resolve_room_actor, None)
    expiry = int(time.time()) + seconds
    token = jwt.encode(
        {
            "iss": "http://fixture.invalid/auth/v1",
            "aud": "authenticated",
            "sub": str(table.gm.user_id),
            "iat": int(time.time()),
            "exp": expiry,
        },
        key,
        algorithm="RS256",
    )
    table.client.headers["Authorization"] = "Bearer " + token
    return expiry


def command(table, kind, payload, room=None, actor=None, version=0):
    actor = actor or table.gm
    return {
        "command_id": str(uuid4()),
        "room_id": str(room or table.room),
        "actor_session_id": str(actor.guest_session_id or actor.id),
        "expected_aggregate_version": version,
        "type": kind,
        "payload": payload,
        "client_sent_at": datetime.now(UTC).isoformat(),
    }


def close_socket(socket):
    socket.send_json({"type": "fixture-close"})
    with pytest.raises(WebSocketDisconnect) as closed:
        while True:
            socket.receive_json()
    assert closed.value.code == 4400


@pytest.mark.parametrize("already_open", [False, True])
def test_real_registered_jwt_expiry_closes_ticket_and_open_socket(
    live_table, monkeypatch, already_open
):
    table = live_table
    expiry = authenticated(table, monkeypatch, 2)
    ticket = table.ticket()
    before = table.portal.call(
        table.db.fetchval, "select count(*) from app.room_events where room_id=$1", table.room
    )
    with table.client.websocket_connect(table.url + "/realtime/ws") as socket:
        if already_open:
            socket.send_json({"type": "subscribe", "ticket": ticket, "cursor": 0})
            assert socket.receive_json()["type"] == "sync"
        time.sleep(max(0, expiry - time.time() + 0.15))
        assert table.client.get(table.url + "/scene").status_code == 401
        if already_open:
            socket.send_json(
                {"type": "command", "command": command(table, "dice.roll", {"expression": "1d1"})}
            )
        else:
            socket.send_json({"type": "subscribe", "ticket": ticket, "cursor": 0})
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 4401
    assert (
        table.portal.call(
            table.db.fetchval, "select count(*) from app.room_events where room_id=$1", table.room
        )
        == before
    )
    authenticated(table, monkeypatch, 60)
    with table.client.websocket_connect(table.url + "/realtime/ws") as socket:
        socket.send_json({"type": "subscribe", "ticket": table.ticket(), "cursor": 0})
        assert socket.receive_json()["type"] == "sync"
        socket.send_json(
            {"type": "command", "command": command(table, "dice.roll", {"expression": "1d1"})}
        )
        assert socket.receive_json()["result"]["status"] == "accepted"
        close_socket(socket)


def test_ws_command_waiting_for_room_lock_cannot_commit_after_jwt_expiry(live_table, monkeypatch):
    table = live_table
    expiry = authenticated(table, monkeypatch, 2)
    with table.client.websocket_connect(table.url + "/realtime/ws") as socket:
        socket.send_json({"type": "subscribe", "ticket": table.ticket(), "cursor": 0})
        assert socket.receive_json()["type"] == "sync"
        transaction = table.db.transaction()
        table.portal.call(transaction.start)
        try:
            table.portal.call(
                table.db.fetchval, "select id from app.rooms where id=$1 for update", table.room
            )
            socket.send_json(
                {"type": "command", "command": command(table, "dice.roll", {"expression": "1d1"})}
            )
            # Verify the public command really reached the lock, rather than
            # merely sleeping before an unprocessed frame.
            for _ in range(100):
                waiting = table.portal.call(
                    table.db.fetchval,
                    "select exists(select 1 from pg_stat_activity "
                    "where $1=any(pg_blocking_pids(pid)))",
                    table.db.get_server_pid(),
                )
                if waiting:
                    break
                time.sleep(0.01)
            assert waiting
            time.sleep(max(0, expiry - time.time() + 0.15))
        finally:
            table.portal.call(transaction.commit)
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 4401
    assert (
        table.portal.call(
            table.db.fetchval, "select scene_version from app.rooms where id=$1", table.room
        )
        == 0
    )
    assert (
        table.portal.call(
            table.db.fetchval,
            "select count(*) from app.scene_commands where room_id=$1",
            table.room,
        )
        == 0
    )
    assert (
        table.portal.call(
            table.db.fetchval, "select count(*) from app.room_events where room_id=$1", table.room
        )
        == 0
    )
    authenticated(table, monkeypatch, 60)
    with table.client.websocket_connect(table.url + "/realtime/ws") as socket:
        socket.send_json({"type": "subscribe", "ticket": table.ticket(), "cursor": 0})
        assert socket.receive_json()["type"] == "sync"
        socket.send_json(
            {"type": "command", "command": command(table, "dice.roll", {"expression": "1d1"})}
        )
        assert socket.receive_json()["result"]["status"] == "accepted"
        close_socket(socket)
    assert (
        table.portal.call(
            table.db.fetchval, "select count(*) from app.room_events where room_id=$1", table.room
        )
        == 1
    )


def shared_room(table):
    room, gm = uuid4(), uuid4()
    table.portal.call(
        table.db.execute,
        "insert into app.rooms(id,campaign_id,owner_user_id,name) values($1,$2,$3,'Shared B')",
        room,
        table.campaign,
        table.gm.user_id,
    )
    table.portal.call(
        table.db.execute,
        "insert into app.participants(id,campaign_id,room_id,user_id,role,display_name) "
        "values($1,$2,$3,$4,'gm','GM B')",
        gm,
        table.campaign,
        room,
        table.gm.user_id,
    )
    return Participant(
        id=gm,
        room_id=room,
        campaign_id=table.campaign,
        user_id=table.gm.user_id,
        role="gm",
        display_name="GM B",
        joined_at=datetime.now(UTC),
        authorization_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_shared_scene_two_room_versions_auto_sync_and_stale_guard(live_table):
    table = live_table
    table.command("scene.create", {"name": "Shared"})
    actor_b = shared_room(table)
    scene = table.client.get(table.url + "/scene").json()["scene"]["id"]
    table.portal.call(
        table.service.execute_scene_command,
        actor_b,
        Command.model_validate(
            command(
                table, "scene.activate", {"scene_id": scene}, room=actor_b.room_id, actor=actor_b
            )
        ),
    )
    with table.client.websocket_connect(table.url + "/realtime/ws") as socket:
        socket.send_json({"type": "subscribe", "ticket": table.ticket(True), "cursor": 0})
        first = socket.receive_json()["snapshot"]
        changed = table.portal.call(
            table.service.execute_scene_command,
            actor_b,
            Command.model_validate(
                command(
                    table,
                    "scene.rename",
                    {"scene_id": scene, "name": "Renamed in B"},
                    room=actor_b.room_id,
                    actor=actor_b,
                    version=1,
                )
            ),
        )
        assert changed.status == "accepted"
        # No resync/ping from A: ordinary periodic reconciliation must deliver it.
        update = socket.receive_json()
        assert update["type"] == "sync"
        assert update["snapshot"]["scene"]["name"] == "Renamed in B"
        assert update["snapshot"]["aggregate_version"] == first["aggregate_version"] + 1
        assert update["snapshot"]["event_cursor"] > first["event_cursor"]
        assert update["events"][-1]["type"] == "scene.changed"
        assert update["events"][-1]["aggregate_version"] == update["snapshot"]["aggregate_version"]
        stale = table.client.post(
            table.url + "/scene/commands",
            json=command(
                table, "scene.grid", {"grid_size": 128}, version=first["aggregate_version"]
            ),
        ).json()
        assert stale["error_code"] == "stale_version"
        assert (
            table.portal.call(
                table.db.fetchval,
                "select count(*) from app.room_events where command_id=$1",
                changed.command_id,
            )
            == 1
        )
        assert UUID(update["snapshot"]["scene"]["id"]) == UUID(scene)
        close_socket(socket)


def test_documented_loopback_origin_allowed_and_foreign_origin_rejected(live_table):
    import json
    from pathlib import Path

    table = live_table
    example = Path(__file__).parents[2] / ".env.example"
    origins = json.loads(
        next(
            line.partition("=")[2]
            for line in example.read_text().splitlines()
            if line.startswith("VTT_FRONTEND_ORIGINS=")
        )
    )
    assert "http://127.0.0.1:5173" in origins
    table.client.app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", frontend_origins=origins, _env_file=None
    )
    with table.client.websocket_connect(
        table.url + "/realtime/ws", headers={"origin": "http://127.0.0.1:5173"}
    ) as socket:
        socket.send_json({"type": "subscribe", "ticket": table.ticket(), "cursor": 0})
        assert socket.receive_json()["type"] == "sync"
        close_socket(socket)
    with pytest.raises(WebSocketDisconnect) as closed:
        with table.client.websocket_connect(
            table.url + "/realtime/ws", headers={"origin": "https://foreign.invalid"}
        ):
            pass
    assert closed.value.code == 4403


@pytest.mark.parametrize("transport", ["http", "websocket"])
def test_shared_supported_mutations_converge_without_foreign_card_or_hidden_payload(
    live_table, transport
):
    table = live_table
    table.command("scene.create", {"name": "Shared table"})
    actor_b = shared_room(table)

    def actor(request: Request):
        if UUID(request.path_params["room_id"]) == actor_b.room_id:
            return actor_b
        return table.player if request.headers.get("x-test-actor") == "player" else table.gm

    table.client.app.dependency_overrides[resolve_room_actor] = actor
    route_b = f"/api/v1/rooms/{actor_b.room_id}"
    scene = table.client.get(table.url + "/scene").json()["scene"]["id"]
    assert (
        table.client.post(
            route_b + "/scene/commands",
            json=command(
                table, "scene.activate", {"scene_id": scene}, room=actor_b.room_id, actor=actor_b
            ),
        ).json()["status"]
        == "accepted"
    )
    with table.client.websocket_connect(table.url + "/realtime/ws") as receiving:
        receiving.send_json({"type": "subscribe", "ticket": table.ticket(True), "cursor": 0})
        snapshot = receiving.receive_json()["snapshot"]
        version_b = 1
        with table.client.websocket_connect(route_b + "/realtime/ws") as sender:
            ticket = table.client.post(route_b + "/realtime/ticket").json()["ticket"]
            sender.send_json({"type": "subscribe", "ticket": ticket, "cursor": 0})
            sender.receive_json()

            def mutate(kind, payload, shared=True):
                nonlocal snapshot, version_b
                body = command(
                    table, kind, payload, room=actor_b.room_id, actor=actor_b, version=version_b
                )
                if transport == "http":
                    result = table.client.post(route_b + "/scene/commands", json=body).json()
                else:
                    sender.send_json({"type": "command", "command": body})
                    while True:
                        frame = sender.receive_json()
                        if frame["type"] == "command_result":
                            result = frame["result"]
                            break
                assert result["status"] == "accepted", result
                version_b = result["aggregate_version"]
                if shared:
                    previous = snapshot
                    for _ in range(2):
                        update = receiving.receive_json()
                        if update["type"] == "sync":
                            break
                    else:
                        pytest.fail("Shared-scene change was not delivered before two heartbeats")
                    snapshot = update["snapshot"]
                    assert snapshot["aggregate_version"] == previous["aggregate_version"] + 1
                    assert snapshot["event_cursor"] > previous["event_cursor"]
                    assert all(
                        set(event) == {"cursor", "aggregate_version", "type"}
                        for event in update["events"]
                    )
                    assert "PRIVATE_CANARY" not in str(update)
                    assert all(event["type"] == "scene.changed" for event in update["events"])
                return result

            mutate("item.create", {"name": "Visible shared token", "x": 64, "y": 64})
            token = snapshot["items"][0]["id"]
            mutate("item.update", {"item_id": token, "x": 128})
            assert snapshot["items"][0]["x"] == 128
            mutate("scene.grid", {"grid_size": 32, "unit_label": "ft"})
            assert snapshot["scene"]["grid_size"] == 32
            mutate("fog.fill", {})
            assert snapshot["items"] == []
            mutate("fog.reset", {})
            assert snapshot["items"][0]["id"] == token
            mutate(
                "annotation.create",
                {"kind": "label", "points": [{"x": 64, "y": 64}], "label": "Shared mark"},
            )
            annotation = snapshot["annotations"][0]["id"]
            deleted = mutate("annotation.delete", {"annotation_id": annotation})
            assert snapshot["annotations"] == []
            mutate("action.undo", {"event_cursor": deleted["event_cursor"]})
            assert snapshot["annotations"][0]["id"] == annotation
            mutate(
                "card.create",
                {
                    "card": {
                        "name": "PRIVATE_CANARY room B",
                        "visibility": "gm_only",
                        "abilities": [
                            {
                                "name": "Area",
                                "geometry": {
                                    "shape": "circle",
                                    "radius": 10,
                                    "units": "ft",
                                    "origin": "point",
                                },
                            }
                        ],
                    }
                },
                shared=False,
            )
            card = table.client.get(route_b + "/cards").json()["cards"][0]
            mutate(
                "ability.present",
                {
                    "card_id": card["id"],
                    "ability_id": card["abilities"][0]["id"],
                    "origin": {"x": 64, "y": 64},
                },
            )
            assert len(snapshot["ability_presentations"]) == 1
            mutate("ability.clear", {"presentation_id": snapshot["ability_presentations"][0]["id"]})
            assert snapshot["ability_presentations"] == []
            assert (
                table.client.get(table.url + "/cards", headers={"x-test-actor": "player"}).json()[
                    "cards"
                ]
                == []
            )
            stale = table.client.post(
                table.url + "/scene/commands",
                json=command(table, "item.update", {"item_id": token, "x": 96}, version=1),
            ).json()
            assert stale["error_code"] == "stale_version"
            close_socket(sender)
        close_socket(receiving)
