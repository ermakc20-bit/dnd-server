import json
from uuid import uuid4

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verb", ["first_scene", "scene.create", "scene.activate", "item.create", "map", "dice.roll"]
)
async def test_remaining_verbs_compensate_state_keep_receipts_and_history(table, verb):
    if verb != "first_scene":
        await table.execute("scene.create", {"name": "Previous"})
    before = (await table.client.get(table.url + "/scene")).json()
    asset = None
    if verb in {"first_scene", "scene.create", "scene.activate"}:
        if verb == "scene.activate":
            await table.execute("scene.create", {"name": "Other"})
            before = (await table.client.get(table.url + "/scene")).json()
            payload = {"scene_id": str(before["scenes"][0]["id"])}
            kind = verb
        else:
            payload, kind = {"name": "Created"}, "scene.create"
    elif verb in {"item.create", "map"}:
        kind, payload = "item.create", {"name": "Created object"}
        if verb == "map":
            asset = uuid4()
            await table.connection.execute(
                """insert into app.assets
                (id,campaign_id,owner_user_id,name,kind,object_key,content_type,byte_size,status)
                values($1,$2,$3,'Map','map',$4,'image/png',1,'ready')""",
                asset,
                table.campaign,
                table.gm.user_id,
                "fixture/" + str(asset),
            )
            payload.update(kind="map", asset_id=str(asset))
    else:
        kind, payload = verb, {"expression": "2d6+3"}
    original, accepted = await table.execute(kind, payload)
    assert accepted.status == "accepted"
    saved_event = await table.connection.fetchval(
        "select payload from app.room_events where command_id=$1", original.command_id
    )
    saved_receipt = await table.connection.fetchval(
        "select result from app.scene_commands where command_id=$1", original.command_id
    )
    roll = await table.connection.fetchrow(
        "select * from app.dice_rolls where command_id=$1", original.command_id
    )
    journal = (await table.client.get(table.url + "/journal")).json()
    assert journal["entries"][0]["cursor"] == accepted.event_cursor
    assert journal["entries"][0]["can_undo"] is True
    undo, compensated = await table.execute("action.undo", {"event_cursor": accepted.event_cursor})
    assert compensated.status == "accepted", compensated
    after = (await table.client.get(table.url + "/scene")).json()
    assert after["aggregate_version"] == before["aggregate_version"] + 2
    assert after["event_cursor"] == compensated.event_cursor
    assert after["scene"] == before["scene"] and after["scenes"] == before["scenes"]
    assert after["items"] == before["items"]
    assert (
        await table.connection.fetchval(
            "select payload from app.room_events where command_id=$1", original.command_id
        )
        == saved_event
    )
    assert (
        await table.connection.fetchval(
            "select result from app.scene_commands where command_id=$1", original.command_id
        )
        == saved_receipt
    )
    assert (await table.service.execute_scene_command(table.gm, undo)).status == "duplicate"
    _, repeated = await table.execute("action.undo", {"event_cursor": accepted.event_cursor})
    assert repeated.error_code == "not_reversible"
    if asset:
        assert (
            await table.connection.fetchval("select status from app.assets where id=$1", asset)
            == "ready"
        )
    if roll:
        assert (
            await table.connection.fetchrow(
                "select * from app.dice_rolls where command_id=$1", original.command_id
            )
            == roll
        )
        assert (
            await table.connection.fetchval(
                "select count(*) from app.dice_rolls where room_id=$1", table.room
            )
            == 1
        )
        journal = (await table.client.get(table.url + "/journal")).json()
        original_entry = next(e for e in journal["entries"] if e["cursor"] == accepted.event_cursor)
        assert (
            original_entry["revoked"] is True
            and original_entry["roll"] == json.loads(saved_event)["roll"]
        )
        table.actor = table.player
        guest = (await table.client.get(table.url + "/journal")).json()
        assert (
            next(e for e in guest["entries"] if e["cursor"] == accepted.event_cursor)["revoked"]
            is True
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario", ["guest", "stale", "nonlatest", "crossroom", "pointer", "children", "tombstone"]
)
async def test_lifecycle_undo_rejects_unsafe_or_unauthorized_commands(table, scenario):
    from datetime import UTC, datetime
    from uuid import UUID

    from app.campaigns.repository import PostgresCampaignRepository
    from app.scenes.models import Command

    await table.execute("scene.create", {"name": "Previous"})
    previous = (await table.client.get(table.url + "/scene")).json()["scene"]["id"]
    _, created = await table.execute("scene.create", {"name": "New"})
    new = (await table.client.get(table.url + "/scene")).json()["scene"]["id"]
    if scenario == "guest":
        _, denied = await table.execute(
            "action.undo", {"event_cursor": created.event_cursor}, table.player
        )
        assert denied.error_code == "forbidden"
    elif scenario == "stale":
        _, denied = await table.execute(
            "action.undo", {"event_cursor": created.event_cursor}, expected=0
        )
        assert denied.error_code == "stale_version"
    elif scenario == "nonlatest":
        await table.execute("dice.roll", {"expression": "1d6"})
        _, denied = await table.execute("action.undo", {"event_cursor": created.event_cursor})
        assert denied.error_code == "not_reversible"
    elif scenario in {"crossroom", "pointer", "children"}:
        room = uuid4()
        await table.connection.execute(
            """insert into app.rooms(id,campaign_id,owner_user_id,name)
            values($1,$2,$3,'Other room')""",
            room,
            table.campaign,
            table.gm.user_id,
        )
        await table.connection.execute(
            """insert into app.participants(campaign_id,room_id,user_id,role,display_name)
            values($1,$2,$3,'gm','Other GM')""",
            table.campaign,
            room,
            table.gm.user_id,
        )
        campaigns = PostgresCampaignRepository(
            table.service.repository.engine.url.render_as_string(hide_password=False).replace(
                "postgresql+asyncpg", "postgresql"
            )
        )
        try:
            other = await campaigns.resolve_registered(table.gm.user_id, room)

            async def remote(kind, payload):
                projection = await table.service.repository.get_projection(other, room)
                command = Command(
                    command_id=uuid4(),
                    room_id=room,
                    actor_session_id=other.id,
                    expected_aggregate_version=projection.aggregate_version,
                    type=kind,
                    payload=payload,
                    client_sent_at=datetime.now(UTC),
                )
                return await table.service.execute_scene_command(other, command)

            if scenario == "crossroom":
                denied = await remote("action.undo", {"event_cursor": created.event_cursor})
                assert denied.error_code == "not_reversible"
            else:
                assert (await remote("scene.activate", {"scene_id": new})).status == "accepted"
                if scenario == "children":
                    assert (
                        await remote("item.create", {"name": "Foreign child"})
                    ).status == "accepted"
                    assert (
                        await remote("scene.activate", {"scene_id": previous})
                    ).status == "accepted"
                    table.version = (
                        await table.service.repository.get_projection(table.gm, table.room)
                    ).aggregate_version
                _, denied = await table.execute(
                    "action.undo", {"event_cursor": created.event_cursor}
                )
                assert denied.error_code in {"scene_in_use", "not_reversible"}
                assert (
                    await table.connection.fetchval(
                        "select deleted_at from app.scenes where id=$1", UUID(new)
                    )
                    is None
                )
        finally:
            await campaigns._engine.dispose()
    else:
        _, undone = await table.execute("action.undo", {"event_cursor": created.event_cursor})
        assert undone.status == "accepted"
        assert (await table.client.get(table.url + "/scene")).json()["scene"]["id"] == previous
        _, denied = await table.execute("scene.activate", {"scene_id": new})
        assert denied.error_code == "scene_unavailable"
        _, denied = await table.execute("scene.rename", {"scene_id": new, "name": "Restore bypass"})
        assert denied.error_code == "scene_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["everyone", "gm_only"])
async def test_dice_compensation_preserves_privacy_sync_and_original_result(table, visibility):
    _, rolled = await table.execute("dice.roll", {"expression": "1d6", "visibility": visibility})
    before = (await table.client.get(table.url + "/journal")).json()["entries"][0]["roll"]
    _, undone = await table.execute("action.undo", {"event_cursor": rolled.event_cursor})
    assert undone.status == "accepted"
    table.actor = table.player
    journal = (await table.client.get(table.url + "/journal")).json()
    assert "undo_state" not in str(journal)
    from app.events.projection import synchronize

    sync = await synchronize(table.service.repository, table.player, 0)
    if visibility == "gm_only":
        assert journal["entries"] == [] and sync["events"] == []
        assert str(before["id"]) not in str(journal) + str(sync)
    else:
        assert journal["entries"][1]["roll"] == before and journal["entries"][1]["revoked"] is True
        assert all(e["type"] == "journal.changed" for e in sync["events"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verb",
    [
        "scene.rename",
        "scene.grid",
        "item.update",
        "item.duplicate",
        "item.delete",
        "card.create",
        "card.update",
        "card.clone",
        "card.delete",
        "card.resource",
        "ability.present",
        "ability.clear",
        "fog.fill",
        "fog.reset",
        "fog.reveal",
        "annotation.create",
        "annotation.update",
        "annotation.delete",
    ],
)
async def test_existing_registry_verbs_keep_public_compensation_proofs(table, verb):
    await table.execute("scene.create", {"name": "Baseline"})
    card = {
        "name": "Hero",
        "visibility": "everyone",
        "resources": [{"key": "hp", "label": "HP", "current": 10, "max": 10}],
        "abilities": [
            {"name": "Area", "geometry": {"shape": "circle", "radius": 5, "origin": "point"}}
        ],
    }
    await table.execute("card.create", {"card": card})
    card = (await table.client.get(table.url + "/cards")).json()["cards"][0]
    await table.execute("item.create", {"name": "Baseline token"})
    snapshot = (await table.client.get(table.url + "/scene")).json()
    token = snapshot["items"][0]
    if verb in {"fog.reset", "fog.reveal"}:
        await table.execute("fog.fill", {})
    if verb in {"annotation.update", "annotation.delete"}:
        await table.execute(
            "annotation.create", {"kind": "label", "points": [{"x": 1, "y": 2}], "label": "Before"}
        )
    if verb == "ability.clear":
        await table.execute(
            "ability.present",
            {
                "card_id": card["id"],
                "ability_id": card["abilities"][0]["id"],
                "origin": {"x": 1, "y": 2},
            },
        )
    before = (await table.client.get(table.url + "/scene")).json()
    cards_before = (await table.client.get(table.url + "/cards")).json()["cards"]
    payloads = {
        "scene.rename": {"scene_id": snapshot["scene"]["id"], "name": "Changed"},
        "scene.grid": {"grid_size": 80},
        "item.update": {"item_id": token["id"], "x": 128},
        "item.duplicate": {"item_id": token["id"]},
        "item.delete": {"item_id": token["id"]},
        "card.create": {"card": {"name": "New card"}},
        "card.clone": {"card_id": card["id"]},
        "card.update": {
            "card_id": card["id"],
            "card": {
                k: v
                for k, v in card.items()
                if k
                in {
                    "name",
                    "kind",
                    "system_id",
                    "system_version",
                    "visibility",
                    "resources",
                    "abilities",
                    "owner_participant_id",
                    "inventory",
                    "fields",
                }
            }
            | {"name": "Changed"},
        },
        "card.delete": {"card_id": card["id"]},
        "card.resource": {"card_id": card["id"], "resource_key": "hp", "current": 3},
        "ability.present": {
            "card_id": card["id"],
            "ability_id": card["abilities"][0]["id"],
            "origin": {"x": 1, "y": 2},
        },
        "fog.fill": {},
        "fog.reset": {},
        "fog.reveal": {"points": [{"x": 0, "y": 0}, {"x": 20, "y": 0}, {"x": 0, "y": 20}]},
        "annotation.create": {"kind": "label", "points": [{"x": 1, "y": 2}], "label": "Created"},
    }
    if verb == "ability.clear":
        payloads[verb] = {"presentation_id": before["ability_presentations"][0]["id"]}
    if verb.startswith("annotation.") and verb != "annotation.create":
        payloads[verb] = {"annotation_id": before["annotations"][0]["id"]}
        if verb == "annotation.update":
            payloads[verb]["annotation"] = {
                "kind": "label",
                "points": [{"x": 3, "y": 4}],
                "label": "Changed",
            }
    original, accepted = await table.execute(verb, payloads[verb])
    assert accepted.status == "accepted", accepted
    original_payload = await table.connection.fetchval(
        "select payload from app.room_events where command_id=$1", original.command_id
    )
    assert (await table.client.get(table.url + "/journal")).json()["entries"][0]["can_undo"] is True
    undo, undone = await table.execute("action.undo", {"event_cursor": accepted.event_cursor})
    assert undone.status == "accepted", undone
    after = (await table.client.get(table.url + "/scene")).json()
    for key in ("scene", "scenes", "items", "fog", "annotations", "ability_presentations"):
        assert after[key] == before[key], key
    cards_after = (await table.client.get(table.url + "/cards")).json()["cards"]

    def gameplay_cards(cards):
        return [{k: v for k, v in c.items() if k not in {"version", "updated_at"}} for c in cards]

    assert gameplay_cards(cards_after) == gameplay_cards(cards_before)
    assert (
        await table.connection.fetchval(
            "select payload from app.room_events where command_id=$1", original.command_id
        )
        == original_payload
    )
    assert (await table.service.execute_scene_command(table.gm, undo)).status == "duplicate"
    assert (await table.client.get(table.url + "/journal")).json()["entries"][0][
        "can_undo"
    ] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["item", "card", "fog", "scene"])
async def test_compensation_chain_returns_to_last_not_yet_undone_forward_command(table, kind):
    await table.execute("scene.create", {"name": "First"})
    if kind == "item":
        _, first = await table.execute("item.create", {"name": "Token", "x": 0})
        token = (await table.client.get(table.url + "/scene")).json()["items"][0]
        _, second = await table.execute("item.update", {"item_id": token["id"], "x": 128})
    elif kind == "card":
        _, first = await table.execute(
            "card.create",
            {
                "card": {
                    "name": "Hero",
                    "resources": [{"key": "hp", "label": "HP", "current": 10, "max": 10}],
                }
            },
        )
        card = (await table.client.get(table.url + "/cards")).json()["cards"][0]
        _, second = await table.execute(
            "card.resource", {"card_id": card["id"], "resource_key": "hp", "current": 3}
        )
    elif kind == "fog":
        _, first = await table.execute("fog.fill", {})
        _, second = await table.execute(
            "fog.reveal", {"points": [{"x": 0, "y": 0}, {"x": 30, "y": 0}, {"x": 0, "y": 30}]}
        )
    else:
        _, first = await table.execute("scene.create", {"name": "Second"})
        scene = (await table.client.get(table.url + "/scene")).json()["scene"]["id"]
        _, second = await table.execute("scene.rename", {"scene_id": scene, "name": "Changed"})
    _, denied = await table.execute("action.undo", {"event_cursor": first.event_cursor})
    assert denied.error_code == "not_reversible"
    assert (await table.execute("action.undo", {"event_cursor": second.event_cursor}))[
        1
    ].status == "accepted"
    journal = (await table.client.get(table.url + "/journal")).json()["entries"]
    assert (
        next(entry for entry in journal if entry["cursor"] == first.event_cursor)["can_undo"]
        is True
    )
    _, undone = await table.execute("action.undo", {"event_cursor": first.event_cursor})
    assert undone.status == "accepted", undone
    projection = (await table.client.get(table.url + "/scene")).json()
    if kind == "item":
        assert projection["items"] == []
    elif kind == "card":
        assert (await table.client.get(table.url + "/cards")).json()["cards"] == []
    elif kind == "fog":
        assert projection["fog"] == {"enabled": False, "reveals": []}
    else:
        assert [scene["name"] for scene in projection["scenes"]] == ["First"]


@pytest.mark.asyncio
@pytest.mark.parametrize("shared", [False, True])
async def test_inactive_scene_rename_compensation_preserves_active_pointer_and_history(
    table, shared
):
    from datetime import UTC, datetime
    from uuid import UUID

    from app.campaigns.repository import PostgresCampaignRepository
    from app.scenes.models import Command

    await table.execute("scene.create", {"name": "Original A"})
    a = (await table.client.get(table.url + "/scene")).json()["scene"]["id"]
    await table.execute("scene.create", {"name": "Active B"})
    before = (await table.client.get(table.url + "/scene")).json()
    other = None
    campaigns = None
    try:
        if shared:
            other_room = uuid4()
            await table.connection.execute(
                """insert into app.rooms(id,campaign_id,owner_user_id,name)
                values($1,$2,$3,'Shared rename')""",
                other_room,
                table.campaign,
                table.gm.user_id,
            )
            await table.connection.execute(
                """insert into app.participants(campaign_id,room_id,user_id,role,display_name)
                values($1,$2,$3,'gm','Shared GM')""",
                table.campaign,
                other_room,
                table.gm.user_id,
            )
            campaigns = PostgresCampaignRepository(
                table.service.repository.engine.url.render_as_string(hide_password=False).replace(
                    "postgresql+asyncpg", "postgresql"
                )
            )
            other = await campaigns.resolve_registered(table.gm.user_id, other_room)
            projection = await table.service.repository.get_projection(other, other_room)
            activate = Command(
                command_id=uuid4(),
                room_id=other_room,
                actor_session_id=other.id,
                expected_aggregate_version=projection.aggregate_version,
                type="scene.activate",
                payload={"scene_id": a},
                client_sent_at=datetime.now(UTC),
            )
            assert (await table.service.execute_scene_command(other, activate)).status == "accepted"
        original, renamed = await table.execute(
            "scene.rename", {"scene_id": a, "name": "Renamed inactive A"}
        )
        assert renamed.status == "accepted"
        event = await table.connection.fetchrow(
            "select payload,aggregate_version from app.room_events where command_id=$1",
            original.command_id,
        )
        receipt = await table.connection.fetchval(
            "select result from app.scene_commands where command_id=$1", original.command_id
        )
        journal = (await table.client.get(table.url + "/journal")).json()["entries"]
        assert next(e for e in journal if e["cursor"] == renamed.event_cursor)["can_undo"] is True
        other_before = (
            await table.service.repository.get_projection(other, other.room_id) if other else None
        )
        undo, undone = await table.execute("action.undo", {"event_cursor": renamed.event_cursor})
        assert undone.status == "accepted", undone
        after = (await table.client.get(table.url + "/scene")).json()
        assert after["scene"] == before["scene"] and after["items"] == before["items"]
        assert after["scenes"] == before["scenes"]
        assert after["aggregate_version"] == renamed.aggregate_version + 1
        assert after["event_cursor"] == undone.event_cursor
        assert (
            await table.connection.fetchval("select name from app.scenes where id=$1", UUID(a))
            == "Original A"
        )
        assert (
            await table.connection.fetchrow(
                "select payload,aggregate_version from app.room_events where command_id=$1",
                original.command_id,
            )
            == event
        )
        assert (
            await table.connection.fetchval(
                "select result from app.scene_commands where command_id=$1", original.command_id
            )
            == receipt
        )
        assert (await table.service.execute_scene_command(table.gm, undo)).status == "duplicate"
        assert (
            await table.connection.fetchval(
                "select count(*) from app.room_events where command_id=$1", undo.command_id
            )
            == 1
        )
        if other:
            other_after = await table.service.repository.get_projection(other, other.room_id)
            assert other_after.scene.id == UUID(a) and other_after.scene.name == "Original A"
            assert other_after.aggregate_version == other_before.aggregate_version + 1
            assert other_after.event_cursor == undone.event_cursor
    finally:
        if campaigns:
            await campaigns._engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["everyone", "gm_only"])
async def test_dice_compensation_journal_visibility_matches_actual_access(table, visibility):
    _, rolled = await table.execute("dice.roll", {"expression": "2d6+3", "visibility": visibility})
    original = (await table.client.get(table.url + "/journal")).json()["entries"][0]
    _, undone = await table.execute("action.undo", {"event_cursor": rolled.event_cursor})
    assert undone.status == "accepted"
    journal = (await table.client.get(table.url + "/journal")).json()["entries"]
    compensation = next(e for e in journal if e["cursor"] == undone.event_cursor)
    assert compensation["visibility"] == visibility
    retained = next(e for e in journal if e["cursor"] == rolled.event_cursor)
    assert retained["roll"] == original["roll"] and retained["revoked"] is True
    table.actor = table.player
    guest = (await table.client.get(table.url + "/journal")).json()["entries"]
    if visibility == "gm_only":
        assert guest == []
    else:
        assert (
            next(e for e in guest if e["cursor"] == undone.event_cursor)["visibility"] == "everyone"
        )
        assert (
            next(e for e in guest if e["cursor"] == rolled.event_cursor)["roll"] == original["roll"]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["foreign", "deleted", "live_newer", "shared_live_newer"])
async def test_inactive_scene_rename_undo_retains_reference_and_newer_state_guards(table, scenario):
    from datetime import UTC, datetime
    from uuid import UUID

    from app.campaigns.repository import PostgresCampaignRepository
    from app.scenes.models import Command

    await table.execute("scene.create", {"name": "A"})
    a = (await table.client.get(table.url + "/scene")).json()["scene"]["id"]
    await table.execute("scene.create", {"name": "B"})
    if scenario == "foreign":
        campaign, room, scene = uuid4(), uuid4(), uuid4()
        try:
            await table.connection.execute(
                "insert into app.campaigns(id,owner_user_id,name) values($1,$2,'Foreign fixture')",
                campaign,
                table.gm.user_id,
            )
            await table.connection.execute(
                "insert into app.rooms(id,campaign_id,owner_user_id,name) "
                "values($1,$2,$3,'Foreign fixture')",
                room,
                campaign,
                table.gm.user_id,
            )
            await table.connection.execute(
                "insert into app.scenes(id,room_id,campaign_id,name) "
                "values($1,$2,$3,'Foreign fixture')",
                scene,
                room,
                campaign,
            )
            _, denied = await table.execute(
                "scene.rename", {"scene_id": str(scene), "name": "Forbidden"}
            )
            assert denied.error_code == "scene_unavailable"
            assert (
                await table.connection.fetchval("select name from app.scenes where id=$1", scene)
                == "Foreign fixture"
            )
        finally:
            await table.connection.execute("delete from app.campaigns where id=$1", campaign)
        return
    _, renamed = await table.execute("scene.rename", {"scene_id": a, "name": "Renamed A"})
    assert renamed.status == "accepted"
    if scenario == "deleted":
        await table.connection.execute(
            "update app.scenes set deleted_at=now() where id=$1", UUID(a)
        )
        _, denied = await table.execute("action.undo", {"event_cursor": renamed.event_cursor})
        assert denied.error_code == "scene_unavailable"
        assert (
            await table.connection.fetchval("select name from app.scenes where id=$1", UUID(a))
            == "Renamed A"
        )
    elif scenario == "live_newer":
        await table.execute("scene.grid", {"grid_size": 80})
        _, denied = await table.execute("action.undo", {"event_cursor": renamed.event_cursor})
        assert denied.error_code == "not_reversible"
        assert (await table.client.get(table.url + "/scene")).json()["scene"]["grid_size"] == 80
    else:
        room = uuid4()
        campaigns = None
        try:
            await table.connection.execute(
                "insert into app.rooms(id,campaign_id,owner_user_id,name) "
                "values($1,$2,$3,'Shared newer')",
                room,
                table.campaign,
                table.gm.user_id,
            )
            await table.connection.execute(
                "insert into app.participants(campaign_id,room_id,user_id,role,display_name) "
                "values($1,$2,$3,'gm','Shared GM')",
                table.campaign,
                room,
                table.gm.user_id,
            )
            campaigns = PostgresCampaignRepository(
                table.service.repository.engine.url.render_as_string(hide_password=False).replace(
                    "postgresql+asyncpg", "postgresql"
                )
            )
            other = await campaigns.resolve_registered(table.gm.user_id, room)

            async def remote(kind, payload):
                projection = await table.service.repository.get_projection(other, room)
                command = Command(
                    command_id=uuid4(),
                    room_id=room,
                    actor_session_id=other.id,
                    expected_aggregate_version=projection.aggregate_version,
                    type=kind,
                    payload=payload,
                    client_sent_at=datetime.now(UTC),
                )
                return await table.service.execute_scene_command(other, command)

            assert (await remote("scene.activate", {"scene_id": a})).status == "accepted"
            assert (await remote("scene.grid", {"grid_size": 80})).status == "accepted"
            # Inactive A's grid does not advance origin room B, but is still live newer state.
            assert (await table.client.get(table.url + "/scene")).json()[
                "aggregate_version"
            ] == renamed.aggregate_version
            journal = (await table.client.get(table.url + "/journal")).json()["entries"]
            assert (
                next(e for e in journal if e["cursor"] == renamed.event_cursor)["can_undo"] is False
            )
            _, denied = await table.execute("action.undo", {"event_cursor": renamed.event_cursor})
            assert denied.error_code == "not_reversible"
            remote_state = await table.service.repository.get_projection(other, room)
            assert remote_state.scene.name == "Renamed A" and remote_state.scene.grid_size == 80
        finally:
            if campaigns:
                await campaigns._engine.dispose()
