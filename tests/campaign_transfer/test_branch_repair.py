"""Public archive regressions for portable text, pending uploads and shared scenes."""

import asyncio
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from app.cards.models import CardData
from app.identity.models import Participant
from app.scenes.models import Command


async def terminal(client, job):
    for _ in range(300):
        response = await client.get(f"/api/v1/campaign-transfers/{job}")
        assert response.status_code == 200
        state = response.json()
        if state["phase"] in {"completed", "failed", "cancelled", "expired"}:
            return state
        await asyncio.sleep(0.01)
    pytest.fail("Transfer did not reach terminal phase")


async def export_bytes(table):
    job = uuid4()
    response = await table.client.post(
        f"/api/v1/campaign-transfers/{job}/export",
        json={
            "campaign_id": str(table.campaign),
            "include_history": True,
            "include_snapshot": True,
        },
    )
    assert response.status_code == 202
    state = await terminal(table.client, job)
    assert state["phase"] == "completed", state
    response = await table.client.get(f"/api/v1/campaign-transfers/{job}/archive")
    assert response.status_code == 200
    return response.content


@pytest.mark.parametrize("field", ["notes", "subtitle", "field", "ability", "inventory"])
async def test_signed_url_in_card_text_fails_export_without_echo_or_source_mutation(
    transfer, field
):
    signed = "https://bucket.s3.amazonaws.com/image.png?X-Amz-Signature=synthetic-canary"
    data = CardData(name="Ordinary card").model_dump(mode="json")
    if field in {"notes", "subtitle"}:
        data[field] = signed
    elif field == "field":
        data["fields"] = [
            {"key": "flavor", "label": "Flavor", "value": signed, "value_type": "text"}
        ]
    elif field == "ability":
        data["abilities"] = [{"name": "Ordinary ability", "description": signed}]
    else:
        data["inventory"] = [{"name": signed}]
    _, created = await transfer.execute("card.create", {"card": data})
    assert created.status == "accepted"
    job = uuid4()
    response = await transfer.client.post(
        f"/api/v1/campaign-transfers/{job}/export", json={"campaign_id": str(transfer.campaign)}
    )
    assert response.status_code == 202
    state = await terminal(transfer.client, job)
    assert state["phase"] == "failed"
    assert state["error_code"] == "unsafe_config"
    assert signed not in str(state)
    assert (
        await transfer.client.get(f"/api/v1/campaign-transfers/{job}/archive")
    ).status_code != 200
    assert signed in await transfer.connection.fetchval(
        "select data::text from app.cards where room_id=$1", transfer.room
    )


async def test_ordinary_card_text_and_unsigned_links_roundtrip(transfer):
    text = "Dragon's notes: https://public.invalid/rules?chapter=4 and token tactics"
    _, created = await transfer.execute("card.create", {"card": {"name": "Dragon", "notes": text}})
    assert created.status == "accepted"
    archive = await export_bytes(transfer)
    job = uuid4()
    assert (
        await transfer.client.put(
            f"/api/v1/campaign-transfers/{job}/import",
            content=archive,
            headers={"Content-Type": "application/zip"},
        )
    ).status_code == 202
    state = await terminal(transfer.client, job)
    assert state["phase"] == "completed"
    assert (
        await transfer.connection.fetchval(
            "select data->>'notes' from app.cards where campaign_id=$1",
            UUID(state["result_campaign_id"]),
        )
        == text
    )


async def test_unused_failed_upload_does_not_block_confirmed_campaign_export(transfer):
    prepared = await transfer.client.post(
        transfer.url + "/assets/prepare",
        json={"name": "Abandoned", "content_type": "image/png", "byte_size": 4, "kind": "map"},
    )
    assert prepared.status_code == 201
    assert (
        await transfer.client.put(
            prepared.json()["upload_url"], content=b"nope", headers={"Content-Type": "image/png"}
        )
    ).status_code == 400
    before = await transfer.connection.fetchrow(
        "select * from app.assets where id=$1", UUID(prepared.json()["id"])
    )
    archive = await export_bytes(transfer)
    with ZipFile(BytesIO(archive)) as zipped:
        assert zipped.read("assets.json") == b"[]"
    after = await transfer.connection.fetchrow(
        "select * from app.assets where id=$1", UUID(prepared.json()["id"])
    )
    assert before == after and after["status"] == "pending"
    assert transfer.storage.put_count == 0


async def test_two_rooms_restore_same_campaign_scene_and_cross_room_content(transfer):
    _, result = await transfer.execute("scene.create", {"name": "Shared scene"})
    assert result.status == "accepted"
    scene = (await transfer.service.repository.get_projection(transfer.gm, transfer.room)).scene.id
    room, actor_id = uuid4(), uuid4()
    await transfer.connection.execute(
        "insert into app.rooms(id,campaign_id,owner_user_id,name) values($1,$2,$3,'Room B')",
        room,
        transfer.campaign,
        transfer.gm.user_id,
    )
    await transfer.connection.execute(
        "insert into app.participants(id,campaign_id,room_id,user_id,role,display_name) "
        "values($1,$2,$3,$4,'gm','GM B')",
        actor_id,
        transfer.campaign,
        room,
        transfer.gm.user_id,
    )
    actor = Participant(
        id=actor_id,
        room_id=room,
        campaign_id=transfer.campaign,
        user_id=transfer.gm.user_id,
        role="gm",
        display_name="GM B",
        joined_at=datetime.now(UTC),
    )
    version = 0

    async def execute(kind, payload):
        nonlocal version
        result = await transfer.service.execute_scene_command(
            actor,
            Command(
                command_id=uuid4(),
                room_id=room,
                actor_session_id=actor_id,
                expected_aggregate_version=version,
                type=kind,
                payload=payload,
                client_sent_at=datetime.now(UTC),
            ),
        )
        assert result.status == "accepted", result
        version = result.aggregate_version
        return result

    await execute("scene.activate", {"scene_id": str(scene)})
    await execute("card.create", {"card": {"name": "Room B card"}})
    card = await transfer.connection.fetchval("select id from app.cards where room_id=$1", room)
    await execute(
        "item.create",
        {"name": "B token", "card_id": str(card), "owner_participant_id": str(actor_id)},
    )
    await execute(
        "annotation.create", {"kind": "label", "points": [{"x": 64, "y": 64}], "label": "B mark"}
    )
    archive = await export_bytes(transfer)
    job = uuid4()
    assert (
        await transfer.client.put(
            f"/api/v1/campaign-transfers/{job}/import",
            content=archive,
            headers={"Content-Type": "application/zip"},
        )
    ).status_code == 202
    state = await terminal(transfer.client, job)
    assert state["phase"] == "completed", state
    imported = UUID(state["result_campaign_id"])
    rooms = await transfer.connection.fetch(
        "select id,active_scene_id from app.rooms where campaign_id=$1", imported
    )
    assert len(rooms) == 2 and len({r["active_scene_id"] for r in rooms}) == 1
    restored_scene = rooms[0]["active_scene_id"]
    assert restored_scene != scene
    assert (
        await transfer.connection.fetchval(
            "select count(*) from app.scene_items where scene_id=$1", restored_scene
        )
        == 1
    )
    assert (
        await transfer.connection.fetchval(
            "select count(*) from app.scene_annotations where scene_id=$1", restored_scene
        )
        == 1
    )
    assert (
        await transfer.connection.fetchval(
            "select count(*) from app.room_events where room_id=any($1::uuid[])",
            [r["id"] for r in rooms],
        )
        == 5
    )
