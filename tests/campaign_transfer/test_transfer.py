# ruff: noqa: RUF001 - Russian gameplay fixture names
import asyncio
import json
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from app.auth.dependencies import get_current_identity
from app.campaigns.repository import PostgresCampaignRepository
from app.cards.models import Ability, CardData, Geometry, InventoryItem, Resource
from app.identity.models import Participant
from app.scenes.models import Command
from PIL import Image


async def terminal(client, job):
    for _ in range(300):
        response = await client.get(f"/api/v1/campaign-transfers/{job}")
        assert response.status_code == 200, response.text
        state = response.json()
        if state["phase"] == "cleanup_pending":
            await asyncio.sleep(0.03)
            state = (await client.get(f"/api/v1/campaign-transfers/{job}")).json()
        if state["phase"] in {"completed", "failed", "cancelled", "expired", "cleanup_pending"}:
            return state
        await asyncio.sleep(0.01)
    pytest.fail("Transfer did not reach terminal phase")


async def test_empty_campaign_portable_roundtrip_and_request_replay(transfer):
    job = uuid4()
    path = f"/api/v1/campaign-transfers/{job}"
    request = {
        "campaign_id": str(transfer.campaign),
        "include_history": True,
        "include_snapshot": True,
    }
    response = await transfer.client.post(path + "/export", json=request)
    assert response.status_code == 202, response.text
    state = await terminal(transfer.client, job)
    assert state["phase"] == "completed", state
    archive = await transfer.client.get(path + "/archive")
    assert archive.status_code == 200
    with ZipFile(BytesIO(archive.content)) as zipped:
        manifest = json.loads(zipped.read("manifest.json"))
        assert manifest["schema_version"] == 1
        assert {
            "campaign.json",
            "cards.json",
            "scenes.json",
            "items.json",
            "packages.json",
            "snapshot.json",
            "journal.json",
        } <= set(zipped.namelist())
        assert str(transfer.campaign).encode() not in b"".join(
            zipped.read(n) for n in zipped.namelist()
        )
    identity = transfer.application.dependency_overrides[get_current_identity]
    transfer.application.dependency_overrides[get_current_identity] = lambda: identity().model_copy(
        update={"user_id": uuid4()}
    )
    try:
        assert (await transfer.client.get(path)).status_code == 403
        assert (await transfer.client.delete(path)).status_code == 403
        assert (await transfer.client.get(path + "/archive")).status_code in {403, 410}
        assert (
            await transfer.client.post(f"/api/v1/campaign-transfers/{uuid4()}/export", json=request)
        ).status_code == 403
    finally:
        transfer.application.dependency_overrides[get_current_identity] = identity
    imported = uuid4()
    response = await transfer.client.put(
        f"/api/v1/campaign-transfers/{imported}/import",
        content=archive.content,
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 202, response.text
    result = await terminal(transfer.client, imported)
    assert result["phase"] == "completed", result
    assert result["result_campaign_id"] != str(transfer.campaign)
    assert (
        await transfer.connection.fetchval(
            "select name from app.campaigns where id=$1",
            UUID(result["result_campaign_id"]),
        )
        == "Cards"
    )
    replay = await transfer.client.put(
        f"/api/v1/campaign-transfers/{imported}/import",
        content=archive.content,
        headers={"Content-Type": "application/zip"},
    )
    assert (
        replay.status_code == 202
        and replay.json()["result_campaign_id"] == result["result_campaign_id"]
    )

    await transfer.connection.execute(
        "delete from app.campaigns where id=$1", UUID(result["result_campaign_id"])
    )
    deleted = await transfer.client.get(f"/api/v1/campaign-transfers/{imported}")
    assert (
        deleted.status_code == 200
        and deleted.json()["phase"] == "completed"
        and deleted.json()["result_campaign_id"] is None
    )
    replay = await transfer.client.put(
        f"/api/v1/campaign-transfers/{imported}/import",
        content=archive.content,
        headers={"Content-Type": "application/zip"},
    )
    assert replay.status_code == 202 and replay.json()["result_campaign_id"] is None
    assert (
        await transfer.connection.fetchval(
            "select count(*) from app.campaigns where owner_user_id=$1", transfer.gm.user_id
        )
        == 1
    )


async def export_bytes(transfer):
    job = uuid4()
    response = await transfer.client.post(
        f"/api/v1/campaign-transfers/{job}/export",
        json={
            "campaign_id": str(transfer.campaign),
            "include_history": True,
            "include_snapshot": True,
        },
    )
    assert response.status_code == 202, response.text
    state = await terminal(transfer.client, job)
    assert state["phase"] == "completed", state
    response = await transfer.client.get(f"/api/v1/campaign-transfers/{job}/archive")
    assert response.status_code == 200, response.text
    return response.content


async def test_full_state_roundtrip_retains_usable_ownership_and_independent_resources(transfer):
    _, result = await transfer.execute("scene.create", {"name": "Башня"})
    assert result.status == "accepted"
    image = BytesIO()
    Image.new("RGB", (3, 2), (50, 80, 120)).save(image, format="PNG")
    prepared = await transfer.client.post(
        transfer.url + "/assets/prepare",
        json={
            "name": "Карта",
            "content_type": "image/png",
            "byte_size": len(image.getvalue()),
            "kind": "map",
        },
    )
    assert prepared.status_code == 201
    asset = prepared.json()["id"]
    uploaded = await transfer.client.put(
        prepared.json()["upload_url"],
        content=image.getvalue(),
        headers={"Content-Type": "image/png"},
    )
    assert uploaded.status_code == 200
    ability = Ability(name="Круг", geometry=Geometry(shape="circle", radius=20))
    card = CardData(
        name="Моб",
        kind="mob",
        visibility="everyone",
        owner_participant_id=transfer.player.id,
        image_asset_id=UUID(asset),
        resources=[Resource(key="hp", label="HP", current=7, max=10)],
        inventory=[InventoryItem(name="Ключ")],
        abilities=[ability],
        notes="Скрытая заметка",
    )
    ids = []
    for x in (10, 50):
        _, result = await transfer.execute("card.create", {"card": card.model_dump(mode="json")})
        assert result.status == "accepted"
        saved = await transfer.client.get(transfer.url + "/cards")
        card_id = saved.json()["cards"][-1]["id"]
        ids.append(card_id)
        _, result = await transfer.execute(
            "item.create",
            {
                "kind": "token",
                "name": "Моб",
                "card_id": card_id,
                "asset_id": asset,
                "owner_participant_id": str(transfer.player.id),
                "x": x,
                "y": 10,
            },
        )
        assert result.status == "accepted"
    _, result = await transfer.execute(
        "card.resource", {"card_id": ids[0], "resource_key": "hp", "current": 3}
    )
    assert result.status == "accepted"
    _, result = await transfer.execute("fog.fill", {})
    assert result.status == "accepted"
    _, result = await transfer.execute(
        "annotation.create",
        {"kind": "label", "points": [{"x": 20, "y": 20}], "label": "Знак", "visibility": "gm_only"},
    )
    assert result.status == "accepted"
    scene = (await transfer.client.get(transfer.url + "/scene")).json()
    item = scene["items"][0]["id"]
    _, result = await transfer.execute(
        "ability.present",
        {"card_id": ids[0], "ability_id": str(ability.id), "origin_item_id": item},
    )
    assert result.status == "accepted"
    _, result = await transfer.execute(
        "dice.roll", {"expression": "2d6+3", "visibility": "gm_only"}
    )
    assert result.status == "accepted"
    await transfer.connection.execute(
        "update app.rooms set system_config=$1::jsonb,pin_hash='fixture-pin-hash' where id=$2",
        json.dumps({"custom": {"label": "Мои правила", "counter": 5}}),
        transfer.room,
    )
    archive = await export_bytes(transfer)
    with ZipFile(BytesIO(archive)) as zipped:
        content = b"".join(zipped.read(n) for n in zipped.namelist() if n.endswith(".json"))
        for value in (
            str(transfer.gm.user_id),
            str(transfer.player.id),
            asset,
            "fixture-pin-hash",
            "object_key",
            "owner_user_id",
            "guest_session_id",
        ):
            assert value.encode() not in content
    job = uuid4()
    response = await transfer.client.put(
        f"/api/v1/campaign-transfers/{job}/import",
        content=archive,
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 202, response.text
    state = await terminal(transfer.client, job)
    assert state["phase"] == "completed", state
    campaign = UUID(state["result_campaign_id"])
    room = await transfer.connection.fetchval(
        "select id from app.rooms where campaign_id=$1", campaign
    )
    repository = PostgresCampaignRepository(
        transfer.service.repository.engine.url.render_as_string(hide_password=False)
    )
    try:
        transfer.actor = await repository.resolve_registered(transfer.gm.user_id, room)
    finally:
        await repository._engine.dispose()
    target = f"/api/v1/rooms/{room}"
    cards = (await transfer.client.get(target + "/cards")).json()["cards"]
    assert sorted(c["resources"][0]["current"] for c in cards) == [3, 7]
    assert all(
        c["id"] not in ids
        and c["image_asset_id"] != asset
        and c["owner_participant_id"] != str(transfer.player.id)
        for c in cards
    )
    assert all(c["abilities"][0]["id"] != str(ability.id) for c in cards)
    projection = (await transfer.client.get(target + "/scene")).json()
    assert projection["fog"]["enabled"] and len(projection["annotations"]) == 1
    assert len(projection["ability_presentations"]) == 1 and len(projection["items"]) == 2
    imported_assets = await transfer.connection.fetch(
        "select object_key from app.assets where campaign_id=$1", campaign
    )
    assert (
        len(imported_assets) == 1
        and await transfer.storage.get(imported_assets[0]["object_key"], 1000) == image.getvalue()
    )
    assert await transfer.connection.fetchval(
        "select system_config from app.rooms where id=$1", room
    ) == json.dumps(
        {"custom": {"label": "Мои правила", "counter": 5}}, ensure_ascii=False
    ) or json.loads(
        await transfer.connection.fetchval(
            "select system_config::text from app.rooms where id=$1", room
        )
    ) == {"custom": {"label": "Мои правила", "counter": 5}}
    version = projection["aggregate_version"]
    changed = await transfer.service.execute_scene_command(
        transfer.actor,
        Command(
            command_id=uuid4(),
            room_id=room,
            actor_session_id=transfer.actor.id,
            expected_aggregate_version=version,
            type="card.resource",
            payload={"card_id": cards[0]["id"], "resource_key": "hp", "current": 1},
            client_sent_at=datetime.now(UTC),
        ),
    )
    assert changed.status == "accepted", changed
    later = (await transfer.client.get(target + "/cards")).json()["cards"]
    assert sum(c["resources"][0]["current"] == 1 for c in later) == 1
    assert (await transfer.client.get(target + "/journal")).status_code == 200
    new_player, new_session = uuid4(), uuid4()
    assert (
        await transfer.connection.fetchval(
            "select count(*) from app.guest_sessions g join app.participants p "
            "on p.id=g.participant_id where p.campaign_id=$1",
            campaign,
        )
        == 0
    )
    await transfer.connection.execute(
        """insert into app.participants(id,campaign_id,room_id,
        identity_kind,display_name) values($1,$2,$3,'guest','Restored player')""",
        new_player,
        campaign,
        room,
    )
    await transfer.connection.execute(
        """insert into app.guest_sessions(id,participant_id,token_hash,
        expires_at) values($1,$2,$3,now()+interval '1 hour')""",
        new_session,
        new_player,
        str(uuid4()),
    )
    version = changed.aggregate_version

    async def command(kind, payload, actor=None):
        nonlocal version
        actor = actor or transfer.actor
        result = await transfer.service.execute_scene_command(
            actor,
            Command(
                command_id=uuid4(),
                room_id=room,
                actor_session_id=actor.guest_session_id or actor.id,
                expected_aggregate_version=version,
                type=kind,
                payload=payload,
                client_sent_at=datetime.now(UTC),
            ),
        )
        if result.status == "accepted":
            version = result.aggregate_version
        return result

    data = {key: cards[0][key] for key in CardData.model_fields}
    rejected = await command("card.create", {"card": data})
    assert rejected.status == "rejected" and rejected.error_code == "forbidden"
    data["name"] = "Edited restored card"
    assert (
        await command("card.update", {"card_id": cards[0]["id"], "card": data})
    ).status == "accepted"
    data["owner_participant_id"] = str(new_player)
    assert (
        await command("card.update", {"card_id": cards[0]["id"], "card": data})
    ).status == "accepted"
    linked = next(item for item in projection["items"] if item["card_id"] == cards[0]["id"])
    assert (
        await command(
            "item.update", {"item_id": linked["id"], "owner_participant_id": str(new_player)}
        )
    ).status == "accepted"
    assert (await command("fog.reset", {})).status == "accepted"
    player = Participant(
        id=new_player,
        campaign_id=campaign,
        room_id=room,
        role="player",
        display_name="Restored player",
        guest_session_id=new_session,
        joined_at=datetime.now(UTC),
    )
    assert (
        await command(
            "card.resource", {"card_id": cards[0]["id"], "resource_key": "hp", "current": 2}, player
        )
    ).status == "accepted"
    assert (
        await command("item.update", {"item_id": linked["id"], "x": 99}, player)
    ).status == "accepted"
    assert sorted(
        json.loads(r["data"])["resources"][0]["current"]
        for r in await transfer.connection.fetch(
            "select data::text as data from app.cards where campaign_id=$1", transfer.campaign
        )
    ) == [3, 7]
    assert (
        await transfer.connection.fetchval(
            "select count(*) from app.guest_sessions g join app.participants p "
            "on p.id=g.participant_id where p.campaign_id=$1",
            campaign,
        )
        == 1
    )


async def test_imported_history_remains_readable_and_filtered_without_undo(transfer):
    _, result = await transfer.execute(
        "dice.roll", {"expression": "2d6+3", "visibility": "gm_only"}
    )
    assert result.status == "accepted"
    archive = await export_bytes(transfer)
    job = uuid4()
    await transfer.client.put(
        f"/api/v1/campaign-transfers/{job}/import",
        content=archive,
        headers={"Content-Type": "application/zip"},
    )
    state = await terminal(transfer.client, job)
    assert state["phase"] == "completed", state
    campaign = UUID(state["result_campaign_id"])
    room = await transfer.connection.fetchval(
        "select id from app.rooms where campaign_id=$1", campaign
    )
    repository = PostgresCampaignRepository(
        transfer.service.repository.engine.url.render_as_string(hide_password=False)
    )
    try:
        transfer.actor = await repository.resolve_registered(transfer.gm.user_id, room)
    finally:
        await repository._engine.dispose()
    response = await transfer.client.get(f"/api/v1/rooms/{room}/journal")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1 and entries[0]["action"] == "Бросок кубов"
    assert entries[0]["roll"]["expression"] == "2d6+3"
    assert entries[0]["visibility"] == "gm_only" and not entries[0]["can_undo"]


async def test_duplicate_json_keys_and_late_invalid_references_never_create_campaign(transfer):
    import hashlib

    archive = await export_bytes(transfer)
    with ZipFile(BytesIO(archive)) as zipped:
        entries = {n: zipped.read(n) for n in zipped.namelist()}
    manifest = json.loads(entries["manifest.json"])
    campaign = entries["campaign.json"]
    duplicate = campaign.replace(b'"name":"Cards"', b'"name":"Private","name":"Cards"')
    entries["campaign.json"] = duplicate
    manifest["entries"]["campaign.json"]["sha256"] = hashlib.sha256(duplicate).hexdigest()
    manifest["entries"]["campaign.json"]["byte_size"] = len(duplicate)
    entries["manifest.json"] = json.dumps(manifest).encode()
    target = BytesIO()
    with ZipFile(target, "w") as zipped:
        for name, content in entries.items():
            zipped.writestr(name, content)
    before = await transfer.connection.fetchval(
        "select count(*) from app.campaigns where owner_user_id=$1", transfer.gm.user_id
    )
    job = uuid4()
    response = await transfer.client.put(
        f"/api/v1/campaign-transfers/{job}/import",
        content=target.getvalue(),
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 202
    state = await terminal(transfer.client, job)
    assert state["phase"] == "failed", state
    assert (
        await transfer.connection.fetchval(
            "select count(*) from app.campaigns where owner_user_id=$1", transfer.gm.user_id
        )
        == before
    )
    # Independent archive rewrites exercise public validation before any gameplay write.
    import stat
    from zipfile import ZipInfo

    def rewritten(changes=None, extra=None, version=1, checksum=True):
        with ZipFile(BytesIO(archive)) as zipped:
            content = {name: zipped.read(name) for name in zipped.namelist()}
        content.update(changes or {})
        manifest = json.loads(content["manifest.json"])
        manifest["schema_version"] = version
        if checksum:
            for name, value in content.items():
                if name != "manifest.json":
                    manifest["entries"][name]["sha256"] = hashlib.sha256(value).hexdigest()
                    manifest["entries"][name]["byte_size"] = len(value)
        content["manifest.json"] = json.dumps(manifest).encode()
        result = BytesIO()
        with ZipFile(result, "w") as zipped:
            for name, value in content.items():
                zipped.writestr(name, value)
            if extra:
                zipped.writestr(*extra)
        return result.getvalue()

    with ZipFile(BytesIO(archive)) as zipped:
        card = CardData(name="Late invalid", image_asset_id=None).model_dump(mode="json")
        card["image_asset_id"] = "asset:999"
        room_ref = json.loads(zipped.read("campaign.json"))["rooms"][0]["ref"]
    link = ZipInfo("assets/asset-1.bin")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    cases = [
        rewritten(version=2),
        rewritten({"campaign.json": b"{}"}, checksum=False),
        rewritten(extra=("../escape.json", b"{}")),
        rewritten(extra=(link, b"../outside")),
        rewritten(
            {
                "cards.json": json.dumps(
                    [{"ref": "card:1", "room_ref": room_ref, "data": card}]
                ).encode()
            }
        ),
        rewritten({"packages.json": b"[]"}),
    ]
    for invalid in cases:
        bad = uuid4()
        response = await transfer.client.put(
            f"/api/v1/campaign-transfers/{bad}/import",
            content=invalid,
            headers={"Content-Type": "application/zip"},
        )
        assert response.status_code == 202, response.text
        rejected = await terminal(transfer.client, bad)
        assert rejected["phase"] == "failed", rejected
        assert (
            await transfer.connection.fetchval(
                "select count(*) from app.campaigns where owner_user_id=$1", transfer.gm.user_id
            )
            == before
        )


async def test_archive_excludes_card_token_and_annotation_trash(transfer):
    await transfer.execute("scene.create", {"name": "Стол"})
    for name in ("Active hero", "Deleted hero"):
        await transfer.execute("card.create", {"card": {"name": name}})
    saved = (await transfer.client.get(transfer.url + "/cards")).json()["cards"]
    active = next(card for card in saved if card["name"] == "Active hero")
    deleted = next(card for card in saved if card["name"] == "Deleted hero")
    for card in (active, deleted):
        assert (
            await transfer.execute("item.create", {"name": card["name"], "card_id": card["id"]})
        )[1].status == "accepted"
    projected = (await transfer.client.get(transfer.url + "/scene")).json()
    token = next(item for item in projected["items"] if item["card_id"] == deleted["id"])
    assert (await transfer.execute("item.delete", {"item_id": token["id"]}))[1].status == "accepted"
    assert (await transfer.execute("card.delete", {"card_id": deleted["id"]}))[
        1
    ].status == "accepted"
    archive = await export_bytes(transfer)
    with ZipFile(BytesIO(archive)) as zipped:
        docs = {
            name: json.loads(zipped.read(name))
            for name in ("cards.json", "items.json", "annotations.json")
        }
        assert [row["data"]["name"] for row in docs["cards.json"]] == ["Active hero"], (
            "ZIP must not carry campaign trash"
        )
        assert [row["name"] for row in docs["items.json"]] == ["Active hero"]
        assert b"Deleted hero" not in b"".join(zipped.read(name) for name in zipped.namelist())
    imported = uuid4()
    response = await transfer.client.put(
        f"/api/v1/campaign-transfers/{imported}/import",
        content=archive,
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 202
    result = await terminal(transfer.client, imported)
    assert result["phase"] == "completed"
    campaign = UUID(result["result_campaign_id"])
    try:
        assert (
            await transfer.connection.fetchval(
                "select count(*) from app.cards where campaign_id=$1", campaign
            )
            == 1
        )
        assert (
            await transfer.connection.fetchval(
                "select count(*) from app.scene_items where campaign_id=$1", campaign
            )
            == 1
        )
        assert (
            await transfer.connection.fetchval(
                "select count(*) from app.cards where campaign_id=$1 and deleted_at is not null",
                campaign,
            )
            == 0
        )
        assert (
            await transfer.connection.fetchval(
                "select count(*) from app.scene_items where campaign_id=$1 "
                "and deleted_at is not null",
                campaign,
            )
            == 0
        )
    finally:
        await transfer.connection.execute("delete from app.campaigns where id=$1", campaign)
        assert (
            await transfer.connection.fetchval(
                "select count(*) from app.campaigns where id=$1", campaign
            )
            == 0
        )


async def test_compensated_lifecycle_exports_active_state_and_safe_revoked_dice(transfer):
    await transfer.execute("scene.create", {"name": "Kept"})
    _, created = await transfer.execute("scene.create", {"name": "Removed"})
    assert (await transfer.execute("action.undo", {"event_cursor": created.event_cursor}))[
        1
    ].status == "accepted"
    _, rolled = await transfer.execute("dice.roll", {"expression": "2d6+3"})
    assert (await transfer.execute("action.undo", {"event_cursor": rolled.event_cursor}))[
        1
    ].status == "accepted"
    archive = await export_bytes(transfer)
    with ZipFile(BytesIO(archive)) as zipped:
        scenes = json.loads(zipped.read("scenes.json"))
        assert [scene["name"] for scene in scenes] == ["Kept"]
        history = json.loads(zipped.read("journal.json"))
        roll = next(entry for entry in history if entry["type"] == "dice.roll")
        assert roll["action"] == "Бросок кубов · отменён мастером"
        assert roll["roll"]["expression"] == "2d6+3"
        assert "undo_state" not in str(history) and "undo_of" not in str(history)
    imported = uuid4()
    response = await transfer.client.put(
        f"/api/v1/campaign-transfers/{imported}/import",
        content=archive,
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 202, response.text
    result = await terminal(transfer.client, imported)
    assert result["phase"] == "completed", result
    room = await transfer.connection.fetchval(
        "select id from app.rooms where campaign_id=$1", UUID(result["result_campaign_id"])
    )
    campaigns = PostgresCampaignRepository(
        transfer.service.repository.engine.url.render_as_string(hide_password=False).replace(
            "postgresql+asyncpg", "postgresql"
        )
    )
    try:
        actor = await campaigns.resolve_registered(transfer.gm.user_id, room)
        from app.dice_log.journal import get_journal

        restored = await get_journal(transfer.service.repository, actor, room, 0, 100)
        entry = next(entry for entry in restored["entries"] if entry["type"] == "dice.roll")
        assert entry["revoked"] is True and entry["roll"]["total"] == roll["roll"]["total"]
        assert not any(entry["can_undo"] for entry in restored["entries"])
    finally:
        await campaigns._engine.dispose()
