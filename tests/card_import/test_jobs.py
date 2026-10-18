import asyncio
import json
from uuid import UUID, uuid4

import pytest


@pytest.mark.asyncio
async def test_txt_fragments_are_immutable_private_and_erased_on_confirm(table, caplog):
    source = (
        "UNASSIGNED_PRIVATE_FRAGMENT\n"
        "schema_version: 1\nКарточка: guard\nНазвание: Страж\nТип: Моб\n"  # noqa: RUF001 - literal Russian markup
        "Количество: 2\nРесурс: hp | HP | 12 | 12\nЗнамя: Синее\n"  # noqa: RUF001 - literal Russian markup
        "  ASSOCIATED_PRIVATE_FRAGMENT  \n"
    )
    url = table.url + "/imports"
    response = await table.client.post(url + "?format=txt", content=source.encode(),
                                       headers={"Content-Type": "text/plain"})
    assert response.status_code == 201
    job = response.json()
    fragments = job["draftset"]["fragments"]
    assert [(f["external_key"], f["row"], f["text"]) for f in fragments] == [
        (None, 1, "UNASSIGNED_PRIVATE_FRAGMENT\n"),
        ("guard", 9, "  ASSOCIATED_PRIVATE_FRAGMENT  \n"),
    ]
    assert await table.connection.fetchval(
        "select count(*) from app.cards where room_id=$1", table.room
    ) == 0
    table.actor = table.player
    for response in [await table.client.get(url),
                     await table.client.get(url + "/" + job["id"]),
                     await table.client.post(url + "?format=txt", content=source.encode(),
                                             headers={"Content-Type": "text/plain"})]:
        assert response.status_code == 403
        assert "PRIVATE_FRAGMENT" not in response.text
    table.actor = table.gm
    drafts = job["draftset"]["drafts"]
    drafts[0]["card"]["name"] = "Проверенный страж"
    drafts[0]["create_token"] = True
    drafts[0]["source"] = {}
    tampered = await table.client.patch(url + "/" + job["id"], json={
        "expected_version": 1, "drafts": drafts, "fragments": []
    })
    assert tampered.status_code == 422 and "PRIVATE_FRAGMENT" not in tampered.text
    response = await table.client.patch(url + "/" + job["id"], json={
        "expected_version": 1, "drafts": drafts
    })
    assert response.status_code == 200
    edited = response.json()
    assert edited["draftset"]["fragments"] == fragments
    assert edited["draftset"]["drafts"][0]["source"]["name"]["row"] == 4
    await table.execute("scene.create", {"name": "Стол"})
    command, result = await table.execute("import.confirm", {
        "job_id": job["id"], "expected_job_version": edited["version"]
    })
    assert result.status == "accepted"
    assert (await table.service.execute_scene_command(table.gm, command)).status == "duplicate"
    confirmed = (await table.client.get(url + "/" + job["id"])).json()
    assert confirmed["status"] == "confirmed" and confirmed["draftset"]["fragments"] == []
    assert len(confirmed["card_ids"]) == len(set(confirmed["card_ids"])) == 2
    row = await table.connection.fetchrow(
        "select source_bytes,draftset from app.import_jobs where id=$1", UUID(job["id"])
    )
    assert row["source_bytes"] is None and "PRIVATE_FRAGMENT" not in row["draftset"]
    cards = (await table.client.get(table.url + "/cards")).json()["cards"]
    assert len(cards) == 2 and all(c["name"] == "Проверенный страж" for c in cards)
    assert all(c["fields"][0]["value"] == "Синее" for c in cards)
    tokens = await table.connection.fetch(
        "select id,card_id from app.scene_items where campaign_id=$1", table.campaign
    )
    assert len(tokens) == len({t["id"] for t in tokens}) == len({t["card_id"] for t in tokens}) == 2
    await table.execute("card.resource", {
        "card_id": cards[0]["id"], "resource_key": "hp", "current": 3
    })
    refreshed = (await table.client.get(table.url + "/cards")).json()["cards"]
    assert sorted(c["resources"][0]["current"] for c in refreshed) == [3, 12]
    events = await table.connection.fetch(
        "select payload from app.room_events where room_id=$1", table.room
    )
    assert "PRIVATE_FRAGMENT" not in json.dumps(cards) + json.dumps([r["payload"] for r in events])
    assert "PRIVATE_FRAGMENT" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["cancel", "expire"])
async def test_raw_fragments_erased_on_cancel_or_24h_expiry(table, operation):
    response = await table.client.post(table.url + "/imports?format=txt", content=(
        "schema_version: 1\nКарточка: a\nНазвание: Страж\nERASE_PRIVATE_FRAGMENT"  # noqa: RUF001 - literal Russian markup
    ).encode(), headers={"Content-Type": "text/plain"})
    assert response.status_code == 201
    job = response.json()
    assert job["draftset"]["fragments"][0]["text"] == "ERASE_PRIVATE_FRAGMENT"
    interval = await table.connection.fetchval(
        "select extract(epoch from expires_at-created_at) from app.import_jobs where id=$1",
        UUID(job["id"]),
    )
    assert interval == 86400
    if operation == "cancel":
        response = await table.client.delete(
            table.url + "/imports/" + job["id"] + "?expected_version=1"
        )
        assert response.status_code == 200 and response.json()["status"] == "cancelled"
    else:
        await table.connection.execute(
            "update app.import_jobs set expires_at=now()-interval '1 second' where id=$1",
            UUID(job["id"]),
        )
        response = await table.client.get(table.url + "/imports/" + job["id"])
        assert response.status_code == 200 and response.json()["status"] == "expired"
    assert response.json()["draftset"]["fragments"] == []
    row = await table.connection.fetchrow(
        "select source_bytes,draftset from app.import_jobs where id=$1", UUID(job["id"])
    )
    assert row["source_bytes"] is None and "PRIVATE_FRAGMENT" not in row["draftset"]
    assert await table.connection.fetchval(
        "select count(*) from app.cards where room_id=$1", table.room
    ) == 0


@pytest.mark.asyncio
async def test_import_review_atomic_confirmation_and_same_command_receipt(table):
    source = {
        "schema_version": 1,
        "cards": [
            {
                "external_key": "guard",
                "name": "Страж",
                "kind": "mob",
                "resources": [{"key": "hp", "label": "HP", "current": 12, "max": 12}],
            },
            {"external_key": "torch", "name": "Факел", "kind": "object"},
        ],
    }
    response = await table.client.post(table.url + "/imports?format=json", json=source)
    assert response.status_code == 201, response.text
    job = response.json()
    assert (
        await table.connection.fetchval(
            "select count(*) from app.cards where room_id=$1", table.room
        )
        == 0
    )
    draft = job["draftset"]["drafts"]
    draft[0].update(count=3, create_token=True)
    draft[0]["card"]["name"] = "Проверенный страж"
    draft[1]["included"] = False
    job = (
        await table.client.patch(
            table.url + "/imports/" + job["id"],
            json={"expected_version": job["version"], "drafts": draft},
        )
    ).json()
    await table.execute("scene.create", {"name": "Стол"})
    command, result = await table.execute(
        "import.confirm", {"job_id": job["id"], "expected_job_version": job["version"]}
    )
    assert result.status == "accepted"
    repeated = await table.service.execute_scene_command(table.gm, command)
    assert repeated.status == "duplicate"
    cards = (await table.client.get(table.url + "/cards")).json()["cards"]
    assert len(cards) == len({c["id"] for c in cards}) == 3
    assert all(c["name"] == "Проверенный страж" for c in cards)
    tokens = await table.connection.fetch(
        "select id,card_id from app.scene_items where campaign_id=$1", table.campaign
    )
    assert len(tokens) == len({t["id"] for t in tokens}) == len({t["card_id"] for t in tokens}) == 3
    assert await table.connection.fetchval(
        "select source_bytes is null from app.import_jobs where id=$1", UUID(job["id"])
    )
    event = json.loads(
        await table.connection.fetchval(
            "select payload from app.room_events where command_id=$1", command.command_id
        )
    )
    assert len(event["cards"]) == 3 and len(event["items"]) == 3


@pytest.mark.asyncio
async def test_duplicates_resume_cancel_expiry_and_access_are_explicit(table):
    source = {"schema_version": 1, "cards": [{"external_key": "a", "name": "Private"}]}
    url = table.url + "/imports"
    job = (await table.client.post(url + "?format=json", json=source)).json()
    assert (await table.client.get(url)).json()[0]["id"] == job["id"]
    assert (await table.client.get(url + "/" + job["id"])).json()["version"] == 1
    duplicate = await table.client.post(url + "?format=json", json=source)
    assert duplicate.status_code == 409 and duplicate.json()["detail"]["code"] == "duplicate_file"
    update = (await table.client.post(url + "?format=json&mode=update_drafts", json=source)).json()
    assert update["id"] == job["id"] and update["version"] == 2
    new = (await table.client.post(url + "?format=json&mode=new_instances", json=source)).json()
    assert new["id"] != job["id"]
    table.actor = table.player
    for response in [
        await table.client.get(url),
        await table.client.get(url + "/" + job["id"]),
        await table.client.post(url + "?format=json", json=source),
        await table.client.delete(url + "/" + job["id"] + "?expected_version=2"),
        await table.client.get(url + "/templates/docx"),
    ]:
        assert response.status_code == 403 and "Private" not in response.text
    _, forbidden = await table.execute(
        "import.confirm", {"job_id": job["id"], "expected_job_version": 2}
    )
    assert forbidden.status == "rejected"
    table.actor = table.gm
    cancelled = await table.client.delete(url + "/" + job["id"] + "?expected_version=2")
    assert cancelled.json()["status"] == "cancelled"
    assert await table.connection.fetchval(
        "select source_bytes is null from app.import_jobs where id=$1", UUID(job["id"])
    )
    await table.connection.execute(
        "update app.import_jobs set expires_at=now()-interval '1 second' where id=$1",
        UUID(new["id"]),
    )
    expired = (await table.client.get(url + "/" + new["id"])).json()
    assert expired["status"] == "expired"
    assert await table.connection.fetchval(
        "select source_bytes is null from app.import_jobs where id=$1", UUID(new["id"])
    )
    assert (
        await table.connection.fetchval(
            "select count(*) from app.cards where room_id=$1", table.room
        )
        == 0
    )


@pytest.mark.asyncio
async def test_confirmation_rolls_back_first_card_when_later_reference_is_invalid(table):
    source = {
        "schema_version": 1,
        "cards": [
            {"external_key": "first", "name": "Valid"},
            {"external_key": "second", "name": "Invalid", "image_asset_id": str(UUID(int=2))},
        ],
    }
    job = (await table.client.post(table.url + "/imports?format=json", json=source)).json()
    _, result = await table.execute(
        "import.confirm", {"job_id": job["id"], "expected_job_version": 1}
    )
    assert result.status == "rejected" and result.error_code == "asset_unavailable"
    assert (
        await table.connection.fetchval(
            "select count(*) from app.cards where room_id=$1", table.room
        )
        == 0
    )
    assert (
        await table.connection.fetchval(
            "select count(*) from app.room_events where room_id=$1", table.room
        )
        == 0
    )
    assert await table.connection.fetchval(
        "select source_bytes is not null from app.import_jobs where id=$1", UUID(job["id"])
    )


@pytest.mark.asyncio
async def test_other_gm_cannot_read_or_confirm_another_creators_job(table):
    source = "schema_version: 1\nКарточка: a\nНазвание: Страж\nPRIVATE_SOURCE_TEXT"  # noqa: RUF001 - literal Russian markup
    job = (await table.client.post(table.url + "/imports?format=txt", content=source.encode(),
                                   headers={"Content-Type": "text/plain"})).json()
    assert job["draftset"]["fragments"][0]["text"] == "PRIVATE_SOURCE_TEXT"
    user, actor_id, other_room, room_actor = [uuid4() for _ in range(4)]
    await table.connection.execute(
        "insert into auth.users(id,email) values($1,$2)", user, f"other-{user}@example.invalid"
    )
    try:
        await table.connection.execute(
            "insert into app.participants(id,campaign_id,room_id,user_id,role,display_name) "
            "values($1,$2,$3,$4,'gm','Other GM')",
            actor_id,
            table.campaign,
            table.room,
            user,
        )
        other = table.gm.model_copy(update={"id": actor_id, "user_id": user})
        table.actor = other
        response = await table.client.get(table.url + "/imports/" + job["id"])
        assert response.status_code == 404 and "PRIVATE_SOURCE_TEXT" not in response.text
        assert (await table.client.get(table.url + "/imports")).json() == []
        for response in [await table.client.patch(table.url + "/imports/" + job["id"], json={
                            "expected_version": 1, "drafts": job["draftset"]["drafts"]}),
                         await table.client.delete(table.url + "/imports/" + job["id"] +
                                                   "?expected_version=1")]:
            assert response.status_code == 404 and "PRIVATE_SOURCE_TEXT" not in response.text
        _, result = await table.execute(
            "import.confirm", {"job_id": job["id"], "expected_job_version": 1}
        )
        assert result.status == "rejected" and result.error_code == "import_unavailable"
        await table.connection.execute(
            "insert into app.rooms(id,campaign_id,owner_user_id,name) "
            "values($1,$2,$3,'Other room')",
            other_room,
            table.campaign,
            user,
        )
        await table.connection.execute(
            "insert into app.participants(id,campaign_id,room_id,user_id,role,display_name) "
            "values($1,$2,$3,$4,'gm','Other room GM')",
            room_actor,
            table.campaign,
            other_room,
            user,
        )
        table.actor = other.model_copy(update={"id": room_actor, "room_id": other_room})
        response = await table.client.get(f"/api/v1/rooms/{other_room}/imports/{job['id']}")
        assert response.status_code == 404 and "PRIVATE_SOURCE_TEXT" not in response.text
    finally:
        table.actor = table.gm
        await table.connection.execute(
            "delete from app.scene_commands where actor_participant_id=$1", actor_id
        )
        await table.connection.execute("delete from app.rooms where id=$1", other_room)
        await table.connection.execute("delete from auth.users where id=$1", user)


@pytest.mark.asyncio
async def test_concurrent_duplicate_upload_stale_edit_and_filtered_batch_sync(table):
    from app.events.projection import synchronize

    source = {
        "schema_version": 1,
        "cards": [{"name": "Hidden", "visibility": "gm_only"}, {"name": "Visible"}],
    }
    url = table.url + "/imports"
    responses = await asyncio.gather(
        *(table.client.post(url + "?format=json", json=source) for _ in range(2))
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    job = next(r.json() for r in responses if r.status_code == 201)
    update = {"expected_version": 1, "drafts": job["draftset"]["drafts"]}
    first = await table.client.patch(url + "/" + job["id"], json=update)
    assert first.status_code == 200
    stale = await table.client.patch(url + "/" + job["id"], json=update)
    assert stale.status_code == 409
    _, stale_confirm = await table.execute(
        "import.confirm", {"job_id": job["id"], "expected_job_version": 1}
    )
    assert stale_confirm.error_code == "stale_import"
    _, accepted = await table.execute(
        "import.confirm", {"job_id": job["id"], "expected_job_version": 2}
    )
    assert accepted.status == "accepted"
    sync = await synchronize(table.service.repository, table.player, 0)
    assert sync["events"][-1]["type"] == "cards.changed"
    assert "Hidden" not in json.dumps(sync) and "Visible" not in json.dumps(sync)
    assert len(sync["events"]) == 1
    _, closed = await table.execute(
        "import.confirm", {"job_id": job["id"], "expected_job_version": 2}
    )
    assert closed.error_code == "import_closed"
