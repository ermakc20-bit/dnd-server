from uuid import UUID, uuid4

import pytest
from app.events.projection import synchronize


async def card(table, geometry, *, owner=True, hidden=False):
    ability = str(uuid4())
    await table.execute(
        "card.create",
        {
            "card": {
                "name": "Secret card" if hidden else "Mage",
                "owner_participant_id": str(table.player.id) if owner else None,
                "visibility": "gm_only" if hidden else "everyone",
                "abilities": [
                    {
                        "id": ability,
                        "name": "Secret spell" if hidden else "Area",
                        "geometry": geometry,
                    }
                ],
            }
        },
    )
    saved = (await table.client.get(table.url + "/cards")).json()["cards"][-1]
    return saved["id"], ability


@pytest.mark.asyncio
async def test_hidden_and_fog_targets_stay_out_of_affected_list_realtime_and_journal(table):
    await table.execute("scene.create", {"name": "Privacy"})
    ids = await card(table, {"shape": "circle", "origin": "point", "radius": 100, "units": "фут"})
    await table.execute("item.create", {"name": "Visible", "x": 0, "y": 0})
    await table.execute("item.create", {"name": "Fog secret", "x": 640, "y": 640})
    await table.execute("item.create", {"name": "GM secret", "visibility": "gm_only"})
    await table.execute("fog.fill", {})
    await table.execute(
        "fog.reveal",
        {
            "points": [
                {"x": -10, "y": -10},
                {"x": 100, "y": -10},
                {"x": 100, "y": 100},
                {"x": -10, "y": 100},
            ]
        },
    )
    table.actor = table.player
    _, result = await table.execute(
        "ability.present", {"card_id": ids[0], "ability_id": ids[1], "origin": {"x": 32, "y": 32}}
    )
    assert result.status == "accepted", result
    player = (await table.client.get(table.url + "/scene")).json()
    assert len(player["items"]) == 1
    assert player["ability_presentations"][0]["affected_item_ids"] == [player["items"][0]["id"]]
    sync = await synchronize(table.service.repository, table.player, 0)
    journal = (await table.client.get(table.url + "/journal")).json()
    assert "GM secret" not in str(sync) + str(journal)
    assert "Fog secret" not in str(sync) + str(journal)
    assert all("payload" not in event for event in sync["events"])
    table.actor = table.gm
    gm = (await table.client.get(table.url + "/scene")).json()
    assert len(gm["ability_presentations"][0]["affected_item_ids"]) == 3
    # Add hidden targets after confirmation: player public DTO and geometry output remain equal.
    before = player["ability_presentations"]
    for _ in range(8):
        await table.execute(
            "item.create", {"name": "Another hidden target", "visibility": "gm_only"}
        )
    table.actor = table.player
    after = (await table.client.get(table.url + "/scene")).json()["ability_presentations"]
    assert before == after


@pytest.mark.asyncio
async def test_authorization_token_origin_bounds_stale_and_clear(table):
    await table.execute("scene.create", {"name": "Permissions"})
    ids = await card(
        table, {"shape": "line", "origin": "token", "length": 5, "width": 5, "units": "фут"}
    )
    await table.execute("item.create", {"name": "Caster", "card_id": ids[0]})
    token = (await table.client.get(table.url + "/scene")).json()["items"][0]["id"]
    payload = {
        "card_id": ids[0],
        "ability_id": ids[1],
        "origin_item_id": token,
        "direction": {"x": 160, "y": 32},
    }
    table.actor = table.player
    _, result = await table.execute("ability.present", payload)
    assert result.status == "accepted"
    _, stale = await table.execute("ability.present", payload, expected=0)
    assert stale.error_code == "stale_version"
    for invalid in [
        {**payload, "origin_item_id": str(uuid4())},
        {**payload, "ability_id": str(uuid4())},
        {**payload, "card_id": str(uuid4())},
    ]:
        _, denied = await table.execute("ability.present", invalid)
        assert denied.error_code == "forbidden"
    for invalid in [
        {**payload, "direction": {"x": 1000001, "y": 0}},
        {**payload, "direction": {"x": float("nan"), "y": 0}},
        {**payload, "direction": {"x": 32, "y": 32}},
        {**payload, "origin": {"x": 0, "y": 0}},
    ]:
        # SceneService's finite payload validation is public, before any persistence.
        _, denied = await table.execute("ability.present", invalid)
        assert denied.status == "rejected"
    area = (await table.client.get(table.url + "/scene")).json()["ability_presentations"][0]
    table.actor = table.gm
    other = await card(
        table, {"shape": "circle", "origin": "point", "radius": 1, "units": "фут"}, owner=False
    )
    table.actor = table.player
    _, denied = await table.execute(
        "ability.present", {"card_id": other[0], "ability_id": other[1], "origin": {"x": 0, "y": 0}}
    )
    assert denied.error_code == "forbidden"
    command, cleared = await table.execute("ability.clear", {"presentation_id": area["id"]})
    assert cleared.status == "accepted"
    assert (await table.client.get(table.url + "/scene")).json()["ability_presentations"] == []
    assert (await table.service.execute_scene_command(table.player, command)).status == "duplicate"
    assert (
        await table.connection.fetchval(
            "select count(*) from app.room_events where command_id=$1", command.command_id
        )
        == 1
    )


@pytest.mark.asyncio
async def test_point_origin_with_range_needs_no_token_and_does_not_infer_casting_legality(table):
    await table.execute("scene.create", {"name": "Manual"})
    ids = await card(
        table, {"shape": "radius", "origin": "point", "range": 0, "radius": 1, "units": "фут"}
    )
    table.actor = table.player
    _, result = await table.execute(
        "ability.present",
        {"card_id": ids[0], "ability_id": ids[1], "origin": {"x": 999999, "y": -999999}},
    )
    assert result.status == "accepted"
    table.actor = table.gm
    hidden = await card(
        table,
        {"shape": "circle", "origin": "point", "radius": 1, "units": "фут"},
        owner=False,
        hidden=True,
    )
    _, result = await table.execute(
        "ability.present",
        {"card_id": hidden[0], "ability_id": hidden[1], "origin": {"x": 10, "y": 10}},
    )
    assert result.status == "accepted"
    table.actor = table.player
    snapshot = (await table.client.get(table.url + "/scene")).json()
    assert len(snapshot["ability_presentations"]) == 2
    assert "Secret card" not in str(snapshot) and "Secret spell" not in str(snapshot)
    journal = (await table.client.get(table.url + "/journal")).json()
    assert "Secret card" not in str(journal) and "Secret spell" not in str(journal)
    gm_area = next(area for area in snapshot["ability_presentations"] if not area["can_clear"])
    _, denied = await table.execute("ability.clear", {"presentation_id": gm_area["id"]})
    assert denied.error_code == "forbidden"
    # Canonical geometry only; no global affected-list or card secrets are stored.
    data = await table.connection.fetchval(
        "select geometry from app.ability_presentations where id=$1", UUID(gm_area["id"])
    )
    assert "affected" not in str(data) and "card" not in str(data)


@pytest.mark.asyncio
async def test_derived_token_center_outside_input_limit_and_invalid_units_are_safe(table):
    await table.execute("scene.create", {"name": "Derived center"})
    ids = await card(table, {"shape": "circle", "origin": "token", "radius": 5, "units": "фут"})
    await table.execute("scene.grid", {"snap_enabled": False})
    _, result = await table.execute(
        "item.create",
        {
            "name": "Edge caster",
            "card_id": ids[0],
            "owner_participant_id": str(table.player.id),
            "x": 1000000,
            "y": 1000000,
        },
    )
    assert result.status == "accepted"
    table.actor = table.player
    token = (await table.client.get(table.url + "/scene")).json()["items"][0]["id"]
    _, result = await table.execute(
        "ability.present", {"card_id": ids[0], "ability_id": ids[1], "origin_item_id": token}
    )
    assert result.status == "accepted"
    area = (await table.client.get(table.url + "/scene")).json()["ability_presentations"][0]
    assert area["geometry"]["origin"] == {"x": 1000032, "y": 1000032}
    assert area["affected_item_ids"] == [token]
    table.actor = table.gm
    bad = await card(table, {"shape": "circle", "origin": "point", "radius": 5, "units": "метр"})
    for geometry_ids in [bad, (ids[0], str(uuid4()))]:
        _, rejected = await table.execute(
            "ability.present",
            {"card_id": geometry_ids[0], "ability_id": geometry_ids[1], "origin": {"x": 0, "y": 0}},
        )
        assert rejected.status == "rejected"
