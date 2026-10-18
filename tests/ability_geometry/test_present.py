from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_assigned_ability_presents_without_changing_card_and_is_idempotent(table):
    await table.execute("scene.create", {"name": "Geometry"})
    ability = str(uuid4())
    _, result = await table.execute(
        "card.create",
        {
            "card": {
                "name": "Mage",
                "owner_participant_id": str(table.player.id),
                "resources": [{"key": "hp", "label": "HP", "current": 10}],
                "abilities": [
                    {
                        "id": ability,
                        "name": "Circle",
                        "uses": {
                            "key": "uses",
                            "label": "Uses",
                            "current": 0,
                            "visibility": "gm_only",
                        },
                        "geometry": {
                            "shape": "circle",
                            "origin": "point",
                            "radius": 10,
                            "units": "фут",
                        },
                    }
                ],
            }
        },
    )
    assert result.status == "accepted"
    cards = (await table.client.get(table.url + "/cards")).json()["cards"]
    card = cards[0]
    await table.execute("scene.grid", {"snap_enabled": False})
    await table.execute("item.create", {"name": "Boundary", "x": 96, "y": -32})
    table.actor = table.player
    command, presented = await table.execute(
        "ability.present",
        {"card_id": card["id"], "ability_id": ability, "origin": {"x": 0, "y": 0}},
    )
    assert presented.status == "accepted", presented
    projection = (await table.client.get(table.url + "/scene")).json()
    overlay = projection["ability_presentations"][0]
    assert overlay["geometry"]["radius"] == 128
    assert overlay["affected_item_ids"] == [projection["items"][0]["id"]]
    assert "card_id" not in overlay and "ability_id" not in overlay
    duplicate = await table.service.execute_scene_command(table.player, command)
    assert duplicate.status == "duplicate"
    journal = (await table.client.get(table.url + "/journal")).json()
    assert journal["entries"][0]["type"] == "ability.present"
    assert "payload" not in str(journal)
    table.actor = table.gm
    unchanged = (await table.client.get(table.url + "/cards")).json()["cards"][0]
    assert unchanged == card
    count = await table.connection.fetchval(
        "select count(*) from app.room_events where command_id=$1", command.command_id
    )
    assert count == 1
