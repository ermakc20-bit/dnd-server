import json
from uuid import UUID

import pytest


@pytest.mark.asyncio
async def test_native_card_create_projection_and_canonical_event(table):
    data = {
        "name": "Страж",
        "kind": "mob",
        "visibility": "everyone",
        "fields": [
            {"key": "clan", "label": "Клан", "value": "Север", "value_type": "text"},
            {
                "key": "secret",
                "label": "Тайна",
                "value": "Секретный союз",
                "value_type": "text",
                "visibility": "gm_only",
            },
        ],
        "resources": [{"key": "blood", "label": "Очки крови", "current": 4, "max": 8}],
        "owner_participant_id": str(table.player.id),
        "notes": "Записка мастера",
    }
    command, result = await table.execute("card.create", {"card": data})
    assert result.status == "accepted"
    response = await table.client.get(table.url + "/cards")
    assert response.status_code == 200
    cards = response.json()["cards"]
    assert len(cards) == 1
    card = cards[0]
    assert card["schema_version"] == card["version"] == 1
    assert card["campaign_id"] == str(table.campaign)
    assert card["resources"][0]["current"] == 4
    assert card["fields"][0]["value"] == "Север"
    event = await table.connection.fetchrow(
        "select * from app.room_events where command_id=$1", command.command_id
    )
    assert event["scene_id"] is None and event["aggregate_id"] == table.room
    assert json.loads(event["payload"])["card"]["id"] == card["id"]
    assert event["aggregate_version"] == 1
    table.actor = table.player
    response = await table.client.get(table.url + "/cards/" + card["id"])
    assert response.status_code == 200
    assert "Секретный союз" not in response.text and "Записка мастера" not in response.text
    assert len(response.json()["fields"]) == 1
    assert response.json()["can_edit_current"] is True
    duplicate = await table.service.execute_scene_command(table.gm, command)
    assert duplicate.status == "duplicate" and duplicate.event_cursor == result.event_cursor
    assert (
        await table.connection.fetchval(
            "select count(*) from app.cards where id=$1", UUID(card["id"])
        )
        == 1
    )


@pytest.mark.asyncio
async def test_card_update_resource_clone_permissions_and_one_version_stream(table):
    data = {
        "name": "Страж",
        "kind": "mob",
        "visibility": "everyone",
        "resources": [
            {"key": "hp", "label": "Здоровье", "current": 10, "max": 10},
            {"key": "blood", "label": "Очки крови", "current": 5, "max": 8},
            {"key": "secret", "label": "Секрет", "current": 2, "visibility": "gm_only"},
        ],
    }
    await table.execute("card.create", {"card": data})
    card = (await table.client.get(table.url + "/cards")).json()["cards"][0]
    data["owner_participant_id"] = str(table.player.id)
    _, updated = await table.execute("card.update", {"card_id": card["id"], "card": data})
    assert updated.status == "accepted"
    _, cloned = await table.execute("card.clone", {"card_id": card["id"], "name": "Второй страж"})
    assert cloned.status == "accepted"
    cards = (await table.client.get(table.url + "/cards")).json()["cards"]
    clone = next(entry for entry in cards if entry["id"] != card["id"])
    assert clone["owner_participant_id"] is None
    command, changed = await table.execute(
        "card.resource",
        {"card_id": card["id"], "resource_key": "blood", "current": 3},
        table.player,
    )
    assert changed.status == "accepted"
    repeat = await table.service.execute_scene_command(table.player, command)
    assert repeat.status == "duplicate"
    assert (await table.client.get(table.url + "/cards/" + clone["id"])).json()["resources"][1][
        "current"
    ] == 5
    assert (await table.client.get(table.url + "/cards/" + card["id"])).json()["resources"][1][
        "current"
    ] == 3
    event = await table.connection.fetchrow(
        "select actor_participant_id,payload from app.room_events where command_id=$1",
        command.command_id,
    )
    assert event["actor_participant_id"] == table.player.id
    assert json.loads(event["payload"])["card"]["resources"][1]["current"] == 3
    for kind, payload in [
        ("card.update", {"card_id": card["id"], "card": data}),
        ("card.clone", {"card_id": card["id"]}),
        ("card.create", {"card": data}),
        ("card.resource", {"card_id": clone["id"], "resource_key": "hp", "current": 1}),
        ("card.resource", {"card_id": card["id"], "resource_key": "secret", "current": 1}),
    ]:
        _, rejected = await table.execute(kind, payload, table.player)
        assert rejected.error_code == "forbidden"
    for extra in ({"max": 20}, {"current": 9}, {"current": -1}):
        _, rejected = await table.execute(
            "card.resource",
            {"card_id": card["id"], "resource_key": "blood", "current": 2, **extra},
            table.player,
        )
        assert rejected.error_code == "invalid_command"
    _, scene = await table.execute("scene.create", {"name": "Стол"})
    assert scene.aggregate_version == 5
    _, stale = await table.execute("card.clone", {"card_id": card["id"]}, expected=4)
    assert stale.error_code == "stale_version"
    await table.connection.execute(
        "update app.participants set removed_at=now() where id=$1", table.player.id
    )
    _, denied = await table.execute(
        "card.resource", {"card_id": card["id"], "resource_key": "hp", "current": 1}, table.player
    )
    assert denied.error_code == "forbidden"
    assert (
        await table.connection.fetchval(
            "select count(*) from app.room_events where room_id=$1", table.room
        )
        == 5
    )


@pytest.mark.asyncio
async def test_package_validation_keeps_extensions_and_rejects_rules(table):
    invalid = {
        "name": "Воин",
        "system_id": "dnd-like",
        "fields": [
            {"key": "strength", "label": "Сила", "value_type": "text", "value": "Неверный тип"}
        ],
    }
    _, result = await table.execute("card.create", {"card": invalid})
    assert result.error_code == "invalid_command"
    package = (await table.client.get("/api/v1/system-packages/dnd-like/1")).json()
    data = {"name": "Воин", "system_id": "dnd-like", **package["defaults"]}
    data["fields"].append({"key": "clan", "label": "Клан", "value": "Север"})
    for kind in ("player_character", "npc", "mob", "object"):
        _, result = await table.execute("card.create", {"card": {**data, "kind": kind}})
        assert result.status == "accepted"
    for override in (
        {"schema_version": 2},
        {"fields": [{"key": "a", "label": "A", "value_type": "number", "value": "text"}]},
        {"abilities": [{"name": "Правило", "automation": "roll"}]},
        {"resources": [{"key": "x", "label": "X", "current": 2, "max": 1}]},
        {"system_version": 2},
        {"owner_participant_id": str(UUID(int=2))},
    ):
        _, result = await table.execute("card.create", {"card": {**data, **override}})
        assert result.status == "rejected"
    page = (
        await table.client.get(table.url + "/cards", params={"limit": 2, "search": "Воин"})
    ).json()
    assert len(page["cards"]) == 2 and page["has_more"]
    assert page["cards"][0]["fields"][-1]["value"] == "Север"


@pytest.mark.asyncio
async def test_export_is_authorized_versioned_roundtrip_and_script_safe(table):
    data = {
        "name": "</script><img src=x onerror=alert(1)>",
        "notes": "ONLY_GM",
        "owner_participant_id": str(table.player.id),
        "resources": [{"key": "blood", "label": "Очки крови", "current": 5, "max": 8}],
        "abilities": [{"name": "Знак", "description": "<svg onload=alert(1)>", "automation": None}],
        "inventory": [{"name": "Меч", "quantity": 1}],
        "skills": [{"key": "hide", "name": "Скрытность", "bonus": 2}],
    }
    await table.execute("card.create", {"card": data})
    card = (await table.client.get(table.url + "/cards")).json()["cards"][0]
    export_url = table.url + "/cards/" + card["id"] + "/export"
    response = await table.client.get(export_url, params={"format": "json"})
    assert response.status_code == 200
    document = response.json()
    assert document["schema_version"] == 1
    assert "can_export" not in document and document["resources"][0]["label"] == "Очки крови"
    from app.cards.models import Card

    assert Card.model_validate(document).model_dump(mode="json") == document
    html = await table.client.get(export_url, params={"format": "html"})
    assert html.status_code == 200 and "text/html" in html.headers["content-type"]
    assert "<img src=x" not in html.text and "<svg onload" not in html.text
    assert "default-src 'none'" in html.text
    table.actor = table.player
    assert (await table.client.get(export_url)).status_code == 403
    table.actor = table.gm
    data["allow_player_export"] = True
    await table.execute("card.update", {"card_id": card["id"], "card": data})
    table.actor = table.player
    exported = await table.client.get(export_url)
    assert exported.status_code == 200 and "ONLY_GM" not in exported.text
    assert "ONLY_GM" not in (await table.client.get(export_url, params={"format": "html"})).text
    assert (await table.client.get(export_url, params={"format": "js"})).status_code == 422


@pytest.mark.asyncio
async def test_token_card_link_is_authorized_and_hidden_ids_are_not_projected(table):
    await table.execute("card.create", {"card": {"name": "Скрытая", "visibility": "gm_only"}})
    card = (await table.client.get(table.url + "/cards")).json()["cards"][0]
    await table.execute("scene.create", {"name": "Стол"})
    _, result = await table.execute("item.create", {"name": "Токен", "card_id": card["id"]})
    assert result.status == "accepted"
    gm = await table.service.repository.get_projection(table.gm, table.room)
    player = await table.service.repository.get_projection(table.player, table.room)
    assert str(gm.items[0].card_id) == card["id"]
    assert player.items == []
    table.actor = table.player
    assert (await table.client.get(table.url + "/cards")).json()["cards"] == []
    assert (await table.client.get(table.url + "/cards/" + card["id"])).status_code == 403
    assert (await table.client.get(f"/api/v1/rooms/{UUID(int=1)}/cards")).status_code == 403
    table.actor = table.gm
    _, result = await table.execute(
        "item.update", {"item_id": str(gm.items[0].id), "card_id": None}
    )
    assert result.status == "accepted"
    _, result = await table.execute("item.create", {"name": "Токен", "card_id": str(UUID(int=1))})
    assert result.status == "rejected"


@pytest.mark.asyncio
async def test_map_cannot_acquire_card_link_through_partial_update(table):
    await table.execute("card.create", {"card": {"name": "Объект", "kind": "object"}})
    card = (await table.client.get(table.url + "/cards")).json()["cards"][0]
    await table.execute("scene.create", {"name": "Стол"})
    scene = (await table.service.repository.get_projection(table.gm, table.room)).scene
    item_id = await table.connection.fetchval(
        "insert into app.scene_items(scene_id,campaign_id,kind,name) "
        "values($1,$2,'map','Map') returning id",
        scene.id,
        table.campaign,
    )
    _, rejected = await table.execute(
        "item.update", {"item_id": str(item_id), "card_id": card["id"]}
    )
    assert rejected.status == "rejected" and rejected.error_code == "card_unavailable"
