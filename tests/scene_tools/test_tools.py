import pytest


@pytest.mark.asyncio
async def test_fog_commands_project_objects_and_realtime_safely(table):
    await table.execute("scene.create", {"name": "Fog test"})
    await table.execute("item.create", {"name": "Guard", "x": 128, "y": 128})
    await table.execute(
        "item.create", {"name": "Secret", "visibility": "gm_only", "x": 128, "y": 128}
    )
    command, filled = await table.execute("fog.fill", {})
    assert filled.status == "accepted", filled
    gm = (await table.client.get(table.url + "/scene")).json()
    table.actor = table.player
    player = (await table.client.get(table.url + "/scene")).json()
    assert gm["fog"]["enabled"] is True and len(gm["items"]) == 2
    assert player["items"] == [] and player["annotations"] == []
    assert "Secret" not in str(player)
    _, denied = await table.execute("fog.reset", {})
    assert denied.error_code == "forbidden"
    duplicate = await table.service.execute_scene_command(table.gm, command)
    assert duplicate.status == "duplicate"
    table.actor = table.gm
    _, revealed = await table.execute(
        "fog.reveal",
        {
            "points": [
                {"x": 64, "y": 64},
                {"x": 256, "y": 64},
                {"x": 256, "y": 256},
                {"x": 64, "y": 256},
            ]
        },
    )
    assert revealed.status == "accepted"
    table.actor = table.player
    player = (await table.client.get(table.url + "/scene")).json()
    assert [item["name"] for item in player["items"]] == ["Guard"]
    assert player["fog"]["reveals"][0]["points"][0] == {"x": 64.0, "y": 64.0}
    from app.events.projection import synchronize

    sync = await synchronize(table.service.repository, table.player, 0)
    assert "Secret" not in str(sync) and all("payload" not in event for event in sync["events"])
    table.actor = table.gm
    _, polygon = await table.execute(
        "fog.reveal", {"points": [{"x": 0, "y": 0}, {"x": 30, "y": 0}, {"x": 15, "y": 30}]}
    )
    assert polygon.status == "accepted"
    for points in [
        [{"x": 0, "y": 0}, {"x": 6, "y": 4}, {"x": 0, "y": 5}, {"x": 4, "y": 0}],
        [{"x": 0, "y": 0}] * 3,
        [{"x": float("inf"), "y": 0}, {"x": 1, "y": 1}, {"x": 2, "y": 0}],
    ]:
        _, invalid = await table.execute("fog.reveal", {"points": points})
        assert invalid.error_code == "invalid_command"


@pytest.mark.asyncio
async def test_annotation_owner_rights_hidden_projection_and_tombstone(table):
    await table.execute("scene.create", {"name": "Marks"})
    command, result = await table.execute(
        "annotation.create",
        {"kind": "arrow", "points": [{"x": 10, "y": 20}, {"x": 90, "y": 20}]},
        table.player,
    )
    assert result.status == "accepted", result
    table.actor = table.player
    marks = (await table.client.get(table.url + "/scene")).json()["annotations"]
    assert len(marks) == 1 and marks[0]["can_edit"] is True
    mark = marks[0]
    table.actor = table.gm
    _, secret = await table.execute(
        "annotation.create",
        {
            "kind": "label",
            "points": [{"x": 15, "y": 25}],
            "label": "Hidden label",
            "visibility": "gm_only",
        },
    )
    assert secret.status == "accepted"
    _, denied = await table.execute(
        "annotation.create",
        {
            "kind": "label",
            "points": [{"x": 15, "y": 25}],
            "label": "Hidden label",
            "visibility": "gm_only",
        },
        table.player,
    )
    assert denied.error_code == "forbidden"
    _, edited = await table.execute(
        "annotation.update",
        {
            "annotation_id": mark["id"],
            "annotation": {"kind": "line", "points": [{"x": 1, "y": 2}, {"x": 30, "y": 40}]},
        },
        table.player,
    )
    assert edited.status == "accepted"
    table.actor = table.player
    projection = (await table.client.get(table.url + "/scene")).json()
    assert "Hidden label" not in str(projection) and len(projection["annotations"]) == 1
    _, deleted = await table.execute("annotation.delete", {"annotation_id": mark["id"]})
    assert deleted.status == "accepted"
    assert (await table.client.get(table.url + "/scene")).json()["annotations"] == []
    from uuid import UUID

    assert await table.connection.fetchval(
        "select deleted_at is not null from app.scene_annotations where id=$1", UUID(mark["id"])
    )
    duplicate = await table.service.execute_scene_command(table.player, command)
    assert duplicate.status == "duplicate"


@pytest.mark.asyncio
async def test_undo_compensates_head_version_preserves_history_and_is_idempotent(table):
    await table.execute("scene.create", {"name": "Undo"})
    original, filled = await table.execute("fog.fill", {})
    command, result = await table.execute("action.undo", {"event_cursor": filled.event_cursor})
    assert result.status == "accepted", result
    gm = (await table.client.get(table.url + "/scene")).json()
    assert gm["fog"]["enabled"] is False and gm["aggregate_version"] == 3
    assert (
        await table.connection.fetchval(
            "select count(*) from app.room_events where room_id=$1", table.room
        )
        == 3
    )
    assert (
        await table.connection.fetchval(
            "select payload->'fog'->>'enabled' from app.room_events where command_id=$1",
            original.command_id,
        )
        == "true"
    )
    assert (await table.service.execute_scene_command(table.gm, command)).status == "duplicate"
    journal = (await table.client.get(table.url + "/journal")).json()
    assert journal["entries"][0]["type"] == "action.undo" and not journal["entries"][0]["can_undo"]
    _, filled = await table.execute("fog.fill", {})
    _, stale = await table.execute("action.undo", {"event_cursor": filled.event_cursor}, expected=3)
    assert stale.error_code == "stale_version"
    _, denied = await table.execute(
        "action.undo", {"event_cursor": filled.event_cursor}, table.player
    )
    assert denied.error_code == "forbidden"
    _, roll = await table.execute("dice.roll", {"expression": "1d1"})
    original_roll = await table.connection.fetchrow(
        "select * from app.dice_rolls where room_id=$1", table.room
    )
    _, compensated = await table.execute("action.undo", {"event_cursor": roll.event_cursor})
    assert compensated.status == "accepted"
    assert (
        await table.connection.fetchrow("select * from app.dice_rolls where room_id=$1", table.room)
        == original_roll
    )
    assert (
        await table.connection.fetchval(
            "select count(*) from app.dice_rolls where room_id=$1", table.room
        )
        == 1
    )
    journal = (await table.client.get(table.url + "/journal")).json()
    assert (
        next(entry for entry in journal["entries"] if entry["cursor"] == roll.event_cursor)[
            "revoked"
        ]
        is True
    )
    await table.execute("fog.reset", {})
    _, _created = await table.execute(
        "annotation.create", {"kind": "label", "points": [{"x": 10, "y": 20}], "label": "Note"}
    )
    mark = (await table.client.get(table.url + "/scene")).json()["annotations"][0]
    _, deleted = await table.execute("annotation.delete", {"annotation_id": mark["id"]})
    _, restored = await table.execute("action.undo", {"event_cursor": deleted.event_cursor})
    assert restored.status == "accepted"
    assert (await table.client.get(table.url + "/scene")).json()["annotations"][0][
        "label"
    ] == "Note"
    await table.execute("item.create", {"name": "Token"})
    item = (await table.client.get(table.url + "/scene")).json()["items"][0]
    _, moved = await table.execute("item.update", {"item_id": item["id"], "x": 128, "rotation": 45})
    _, restored = await table.execute("action.undo", {"event_cursor": moved.event_cursor})
    assert restored.status == "accepted"
    assert (await table.client.get(table.url + "/scene")).json()["items"][0]["x"] == 0
    _, renamed = await table.execute(
        "scene.rename", {"scene_id": gm["scene"]["id"], "name": "Changed"}
    )
    _, restored = await table.execute("action.undo", {"event_cursor": renamed.event_cursor})
    assert restored.status == "accepted"
    assert (await table.client.get(table.url + "/scene")).json()["scene"]["name"] == "Undo"


@pytest.mark.asyncio
async def test_fog_blocks_known_hidden_token_transform_and_asset_grant(table):
    from uuid import uuid4

    from app.assets.service import AssetService
    from app.assets.storage import MemoryStorage

    asset = uuid4()
    await table.connection.execute(
        """
insert into
app.assets(id,owner_user_id,campaign_id,uploaded_by,name,kind,object_key,content_type,byte_size,status)
values($1,$2,$3,$4,'Token','image',$5,'image/png',10,'ready')
""",
        asset,
        table.gm.user_id,
        table.campaign,
        table.gm.id,
        str(asset),
    )
    await table.execute("scene.create", {"name": "Fog security"})
    await table.execute(
        "item.create",
        {
            "name": "Hidden token",
            "asset_id": str(asset),
            "owner_participant_id": str(table.player.id),
        },
    )
    item = (await table.client.get(table.url + "/scene")).json()["items"][0]
    _, filled = await table.execute("fog.fill", {})
    assert filled.status == "accepted"
    _, denied = await table.execute("item.update", {"item_id": item["id"], "x": 128}, table.player)
    assert denied.error_code == "forbidden", denied
    storage = MemoryStorage()
    service = AssetService(
        str(table.service.repository.engine.url).replace("postgresql+asyncpg", "postgresql"),
        storage,
    )
    from app.scenes.models import SceneFailure

    try:
        with pytest.raises(SceneFailure, match="Нет доступа"):
            await service.authorize_download(table.player, asset)
    finally:
        await service.engine.dispose()
