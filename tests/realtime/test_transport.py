from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.identity.dependencies import resolve_room_actor
from app.identity.models import Participant
from starlette.websockets import WebSocketDisconnect


def test_ticket_fails_closed_when_redis_is_not_configured(client):
    room = uuid4()
    actor = Participant(
        id=uuid4(),
        campaign_id=uuid4(),
        room_id=room,
        role="gm",
        display_name="GM",
        user_id=uuid4(),
        joined_at=datetime.now(UTC),
    )
    client.app.dependency_overrides[resolve_room_actor] = lambda: actor
    response = client.post(f"/api/v1/rooms/{room}/realtime/ticket")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "realtime_unavailable"


def test_ticket_is_single_use_room_bound_and_sync_is_filtered(live_table):
    table = live_table
    table.command("scene.create", {"name": "Visible"})
    table.command("item.create", {"name": "Hidden", "visibility": "gm_only"})
    table.command("item.create", {"name": "Visible token"})
    table.command(
        "card.create",
        {
            "card": {
                "name": "Visible card",
                "notes": "Hidden notes",
                "fields": [
                    {
                        "key": "secret",
                        "label": "Hidden field",
                        "value": "Hidden value",
                        "value_type": "text",
                        "visibility": "gm_only",
                    }
                ],
            }
        },
    )
    table.command("card.create", {"card": {"name": "Hidden card", "visibility": "gm_only"}})
    ticket = table.ticket(player=True)
    with table.client.websocket_connect(table.url + "/realtime/ws") as ws:
        ws.send_json({"type": "subscribe", "ticket": ticket, "cursor": 0})
        sync = ws.receive_json()
        assert sync["type"] == "sync"
        assert sync["snapshot"]["aggregate_version"] == 5
        assert [item["name"] for item in sync["snapshot"]["items"]] == ["Visible token"]
        assert "Hidden" not in str(sync)
        assert len(sync["events"]) == 3
        assert sync["events"][-1]["type"] == "cards.changed"
        assert all(
            set(event) == {"cursor", "aggregate_version", "type"} for event in sync["events"]
        )
    with pytest.raises(WebSocketDisconnect):
        with table.client.websocket_connect(table.url + "/realtime/ws") as ws:
            ws.send_json({"type": "subscribe", "ticket": ticket, "cursor": 0})
            ws.receive_json()


def test_two_clients_commands_duplicates_stale_and_reconnect(live_table):
    table = live_table
    table.command("scene.create", {"name": "Shared"})
    with table.client.websocket_connect(table.url + "/realtime/ws") as gm:
        gm.send_json({"type": "subscribe", "ticket": table.ticket(), "cursor": 0})
        first = gm.receive_json()
        command = {
            "command_id": str(uuid4()),
            "room_id": str(table.room),
            "actor_session_id": str(table.gm.id),
            "expected_aggregate_version": 1,
            "type": "item.create",
            "payload": {"name": "Shared token"},
            "client_sent_at": datetime.now(UTC).isoformat(),
        }
        gm.send_json({"type": "command", "command": command})
        ack = gm.receive_json()
        assert ack["type"] == "command_result" and ack["result"]["status"] == "accepted"
        assert gm.receive_json()["snapshot"]["aggregate_version"] == 2
        gm.send_json({"type": "command", "command": command})
        assert gm.receive_json()["result"]["status"] == "duplicate"
        assert gm.receive_json()["snapshot"]["aggregate_version"] == 2
        command["command_id"] = str(uuid4())
        gm.send_json({"type": "command", "command": command})
        assert gm.receive_json()["result"]["error_code"] == "stale_version"
        with table.client.websocket_connect(table.url + "/realtime/ws") as player:
            player.send_json(
                {
                    "type": "subscribe",
                    "ticket": table.ticket(True),
                    "cursor": first["snapshot"]["event_cursor"],
                }
            )
            sync = player.receive_json()
            assert len(sync["events"]) == 1
            assert sync["snapshot"]["items"][0]["name"] == "Shared token"
            table.command(
                "scene.rename",
                {"scene_id": sync["snapshot"]["scene"]["id"], "name": "Updated"},
                version=2,
            )
            assert player.receive_json()["snapshot"]["scene"]["name"] == "Updated"
    with pytest.raises(WebSocketDisconnect):
        with table.client.websocket_connect(f"/api/v1/rooms/{uuid4()}/realtime/ws") as ws:
            ws.send_json({"type": "subscribe", "ticket": table.ticket(), "cursor": 0})
            ws.receive_json()


def test_drag_preview_is_ephemeral_filtered_and_revoke_closes_socket(live_table):
    table = live_table
    table.command("scene.create", {"name": "Shared"})
    table.command("item.create", {"name": "Owned", "owner_participant_id": str(table.player.id)})
    with table.client.websocket_connect(table.url + "/realtime/ws") as player:
        player.send_json({"type": "subscribe", "ticket": table.ticket(True), "cursor": 0})
        snapshot = player.receive_json()["snapshot"]
        with table.client.websocket_connect(table.url + "/realtime/ws") as gm:
            gm.send_json({"type": "subscribe", "ticket": table.ticket(), "cursor": 0})
            gm.receive_json()
            player.send_json(
                {"type": "preview", "item_id": snapshot["items"][0]["id"], "x": 123, "y": 77}
            )
            preview = gm.receive_json()
            assert preview["type"] == "preview" and preview["x"] == 123
            assert (
                table.portal.call(
                    table.db.fetchval, "select scene_version from app.rooms where id=$1", table.room
                )
                == 2
            )
            assert (
                table.portal.call(
                    table.db.fetchval,
                    "select count(*) from app.room_events where room_id=$1",
                    table.room,
                )
                == 2
            )
            assert (
                table.client.delete(table.url + f"/participants/{table.player.id}").status_code
                == 204
            )
            with pytest.raises(WebSocketDisconnect) as closed:
                while True:
                    player.receive_json()
            assert closed.value.code == 4403


def test_ticket_rate_limit_and_cache_policy(live_table):
    responses = [live_table.client.post(live_table.url + "/realtime/ticket") for _ in range(21)]
    assert responses[0].headers.get("cache-control") == "no-store"
    assert responses[0].json()["expires_in"] == 30
    assert responses[-1].status_code == 429
    assert responses[-1].json()["detail"]["code"] == "rate_limited"
