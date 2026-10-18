import json

import pytest


@pytest.mark.asyncio
async def test_server_dice_is_bounded_idempotent_immutable_and_private(table):
    command, result = await table.execute(
        "dice.roll", {"expression": "3d1+2", "visibility": "everyone"}, table.player
    )
    assert result.status == "accepted", result
    table.actor = table.player
    journal = await table.client.get(table.url + "/journal")
    assert journal.status_code == 200
    entry = journal.json()["entries"][0]
    assert (
        entry["actor_name"] == "Guest"
        and entry["occurred_at"]
        and entry["visibility"] == "everyone"
    )
    assert entry["roll"]["results"] == [1, 1, 1] and entry["roll"]["total"] == 5
    assert entry["roll"]["expression"] == "3d1+2" and "payload" not in entry
    repeat = await table.service.execute_scene_command(table.player, command)
    assert repeat.status == "duplicate"
    assert (
        await table.connection.fetchval(
            "select count(*) from app.dice_rolls where command_id=$1", command.command_id
        )
        == 1
    )
    table.actor = table.gm
    _, secret = await table.execute("dice.roll", {"expression": "1d20", "visibility": "gm_only"})
    assert secret.status == "accepted"
    table.actor = table.player
    response = (await table.client.get(table.url + "/journal")).json()
    assert len(response["entries"]) == 1 and "gm_only" not in str(response)
    from app.events.projection import synchronize

    sync = await synchronize(table.service.repository, table.player, 0)
    assert len(sync["events"]) == 1 and sync["events"][0]["type"] == "journal.changed"
    for expression in [
        "101d6",
        "1d1001",
        "0d20",
        "1d6+10001",
        "1d6;delete",
        '__import__("os")',
        "1d6+1d6",
        "1d0",
        "1.5d6",
    ]:
        _, invalid = await table.execute("dice.roll", {"expression": expression})
        assert invalid.error_code == "invalid_command"
    _, denied = await table.execute("dice.roll", {"expression": "1d6", "visibility": "gm_only"})
    assert denied.error_code == "forbidden"
    saved = await table.connection.fetchval(
        "select to_jsonb(r) from app.dice_rolls r where command_id=$1", command.command_id
    )
    assert json.loads(saved)["total"] == 5
    import asyncpg

    with pytest.raises(asyncpg.CheckViolationError, match="immutable"):
        await table.connection.execute(
            "update app.dice_rolls set total=99 where command_id=$1", command.command_id
        )
    with pytest.raises(asyncpg.CheckViolationError, match="immutable"):
        await table.connection.execute(
            "delete from app.room_events where command_id=$1", command.command_id
        )
