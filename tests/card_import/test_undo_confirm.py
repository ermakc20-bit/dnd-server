# ruff: noqa: RUF001 - literal Russian import markup
import json
from uuid import UUID

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("tokens", [False, True])
async def test_confirm_compensation_only_own_ids_keeps_terminal_job_and_receipt(table, tokens):
    if tokens:
        await table.execute("scene.create", {"name": "Imports"})
    await table.execute("card.create", {"card": {"name": "Existing", "visibility": "everyone"}})
    existing = (await table.client.get(table.url + "/cards")).json()["cards"][0]["id"]
    source = (
        "schema_version: 1\nКарточка: guard\nНазвание: Страж\nКоличество: 2\nPRIVATE_RAW_FRAGMENT\n"
    )
    response = await table.client.post(
        table.url + "/imports?format=txt",
        content=source.encode(),
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 201
    job = response.json()
    drafts = job["draftset"]["drafts"]
    drafts[0]["create_token"] = tokens
    edited = (
        await table.client.patch(
            table.url + "/imports/" + job["id"],
            json={"expected_version": job["version"], "drafts": drafts},
        )
    ).json()
    original, accepted = await table.execute(
        "import.confirm", {"job_id": job["id"], "expected_job_version": edited["version"]}
    )
    assert accepted.status == "accepted"
    journal = (await table.client.get(table.url + "/journal")).json()
    assert journal["entries"][0]["can_undo"] is True
    durable = await table.connection.fetchrow(
        "select * from app.import_jobs where id=$1", UUID(job["id"])
    )
    receipt = await table.connection.fetchval(
        "select result from app.scene_commands where command_id=$1", original.command_id
    )
    assert durable["status"] == "confirmed" and durable["source_bytes"] is None
    assert "PRIVATE_RAW_FRAGMENT" not in durable["draftset"]
    ids = durable["card_ids"]
    assert len(ids) == len(set(ids)) == 2
    undo, result = await table.execute("action.undo", {"event_cursor": accepted.event_cursor})
    assert result.status == "accepted", result
    cards = (await table.client.get(table.url + "/cards")).json()["cards"]
    assert [c["id"] for c in cards] == [existing]
    assert (await table.client.get(table.url + "/scene")).json()["items"] == []
    assert (
        await table.connection.fetchval(
            "select count(*) from app.cards where id=any($1::uuid[]) and deleted_at is not null",
            ids,
        )
        == 2
    )
    assert (
        await table.connection.fetchrow(
            "select * from app.import_jobs where id=$1", UUID(job["id"])
        )
        == durable
    )
    assert (
        await table.connection.fetchval(
            "select result from app.scene_commands where command_id=$1", original.command_id
        )
        == receipt
    )
    assert (await table.service.execute_scene_command(table.gm, original)).status == "duplicate"
    assert (await table.service.execute_scene_command(table.gm, undo)).status == "duplicate"
    _, reconfirm = await table.execute(
        "import.confirm", {"job_id": job["id"], "expected_job_version": edited["version"]}
    )
    assert reconfirm.status == "rejected"
    assert (
        await table.connection.fetchval(
            "select count(*) from app.cards where room_id=$1", table.room
        )
        == 3
    )
    assert "PRIVATE_RAW_FRAGMENT" not in json.dumps(
        (await table.client.get(table.url + "/journal")).json()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("later", ["card.resource", "item.update"])
async def test_import_compensation_after_safe_later_object_compensation_keeps_receipt(table, later):
    await table.execute("scene.create", {"name": "Imports"})
    response = await table.client.post(
        table.url + "/imports?format=json",
        json={
            "schema_version": 1,
            "cards": [
                {
                    "external_key": "guard",
                    "name": "Guard",
                    "count": 2,
                    "resources": [{"key": "hp", "label": "HP", "current": 10, "max": 10}],
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()
    drafts = job["draftset"]["drafts"]
    drafts[0]["count"] = 2
    drafts[0]["create_token"] = True
    response = await table.client.patch(
        table.url + "/imports/" + job["id"],
        json={"expected_version": job["version"], "drafts": drafts},
    )
    assert response.status_code == 200
    edited = response.json()
    original, imported = await table.execute(
        "import.confirm", {"job_id": job["id"], "expected_job_version": edited["version"]}
    )
    assert imported.status == "accepted"
    card = (await table.client.get(table.url + "/cards")).json()["cards"][0]
    item = (await table.client.get(table.url + "/scene")).json()["items"][0]
    payload = (
        {"card_id": card["id"], "resource_key": "hp", "current": 3}
        if later == "card.resource"
        else {"item_id": item["id"], "x": 128}
    )
    _, changed = await table.execute(later, payload)
    assert changed.status == "accepted"
    _, denied = await table.execute("action.undo", {"event_cursor": imported.event_cursor})
    assert denied.error_code == "not_reversible"
    assert (await table.execute("action.undo", {"event_cursor": changed.event_cursor}))[
        1
    ].status == "accepted"
    assert (await table.execute("action.undo", {"event_cursor": imported.event_cursor}))[
        1
    ].status == "accepted"
    assert (await table.client.get(table.url + "/cards")).json()["cards"] == []
    assert (await table.client.get(table.url + "/scene")).json()["items"] == []
    assert (await table.client.get(table.url + "/imports/" + job["id"])).json()[
        "status"
    ] == "confirmed"
    assert (await table.service.execute_scene_command(table.gm, original)).status == "duplicate"
