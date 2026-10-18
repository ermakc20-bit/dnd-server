from uuid import UUID

import pytest


async def cards(table, actor=None):
    table.actor = actor or table.gm
    response = await table.client.get(table.url + "/cards")
    assert response.status_code == 200
    return response.json()["cards"]


@pytest.mark.asyncio
async def test_duplicate_linked_token_is_an_independent_owned_character(table):
    data = {
        "name": "Страж",
        "kind": "mob",
        "visibility": "owner_only",
        "owner_participant_id": str(table.player.id),
        "external_key": "guard",
        "fields": [{"key": "state", "label": "Состояние", "value": "Готов"}],
        "resources": [
            {"key": "hp", "label": "HP", "current": 10, "max": 10},
            {"key": "blood", "label": "Кровь", "current": 5, "max": 8},
        ],
        "notes": "Исходная заметка",
        "inventory": [{"name": "Меч"}],
        "abilities": [{"name": "Знак"}],
    }
    assert (await table.execute("card.create", {"card": data}))[1].status == "accepted"
    original = (await cards(table))[0]
    await table.execute("scene.create", {"name": "Стол"})
    await table.execute(
        "item.create",
        {
            "name": "Страж",
            "card_id": original["id"],
            "owner_participant_id": str(table.player.id),
            "visibility": "owner_only",
        },
    )
    initial = await table.service.repository.get_projection(table.gm, table.room)
    command, result = await table.execute("item.duplicate", {"item_id": str(initial.items[0].id)})
    assert result.status == "accepted"
    copied = await cards(table)
    assert len(copied) == 2, "ordinary duplicate must create a separate card"
    clone = next(c for c in copied if c["id"] != original["id"])
    assert clone["owner_participant_id"] == original["owner_participant_id"]
    assert clone["external_key"] is None
    assert clone["inventory"][0]["id"] != original["inventory"][0]["id"]
    assert clone["abilities"][0]["id"] != original["abilities"][0]["id"]
    projection = await table.service.repository.get_projection(table.gm, table.room)
    token = next(item for item in projection.items if str(item.card_id) == clone["id"])
    assert token.owner_participant_id == table.player.id
    assert (await table.service.execute_scene_command(table.gm, command)).status == "duplicate"
    assert len(await cards(table)) == 2
    assert (
        await table.execute(
            "card.resource",
            {"card_id": clone["id"], "resource_key": "hp", "current": 2},
            table.player,
        )
    )[1].status == "accepted"
    changed = {key: value for key, value in data.items()}
    changed.update(
        notes="Новая заметка",
        external_key=None,
        fields=[{"key": "state", "label": "Состояние", "value": "Оглушён"}],
        resources=[
            {"key": "hp", "label": "HP", "current": 2, "max": 10},
            {"key": "blood", "label": "Кровь", "current": 1, "max": 8},
        ],
    )
    assert (
        await table.execute("card.update", {"card_id": clone["id"], "card": changed}, table.gm)
    )[1].status == "accepted"
    current = {c["id"]: c for c in await cards(table)}
    assert current[original["id"]]["resources"][0]["current"] == 10
    assert current[original["id"]]["resources"][1]["current"] == 5
    assert current[original["id"]]["fields"][0]["value"] == "Готов"
    assert current[original["id"]]["notes"] == "Исходная заметка"
    assert (await table.execute("item.duplicate", {"item_id": str(token.id)}, table.player))[
        1
    ].error_code == "forbidden"
    assert (
        await table.connection.fetchval(
            "select count(*) from app.cards where campaign_id=$1", table.campaign
        )
        == 2
    )
    assert UUID(clone["id"]) != UUID(original["id"])


@pytest.mark.asyncio
async def test_npc_defaults_and_explicit_visibility_apply_to_cards_and_linked_tokens(table):
    for kind in ("npc", "mob"):
        assert (await table.execute("card.create", {"card": {"name": kind, "kind": kind}}))[
            1
        ].status == "accepted"
    assert {card["visibility"] for card in await cards(table)} == {"gm_only"}
    assert await cards(table, table.player) == []
    table.actor = table.gm
    await table.execute(
        "card.create", {"card": {"name": "Открытый", "kind": "npc", "visibility": "everyone"}}
    )
    public = next(card for card in await cards(table) if card["name"] == "Открытый")
    await table.execute(
        "card.create",
        {
            "card": {
                "name": "Назначенный",
                "kind": "mob",
                "visibility": "owner_only",
                "owner_participant_id": str(table.player.id),
            }
        },
    )
    owned = next(card for card in await cards(table) if card["name"] == "Назначенный")
    assert {card["name"] for card in await cards(table, table.player)} == {
        "Открытый",
        "Назначенный",
    }
    table.actor = table.gm
    hidden = next(card for card in await cards(table) if card["name"] == "npc")
    await table.execute("scene.create", {"name": "Стол"})
    for card in (hidden, public, owned):
        assert (
            await table.execute(
                "item.create",
                {
                    "name": card["name"],
                    "card_id": card["id"],
                    "owner_participant_id": card["owner_participant_id"],
                },
            )
        )[1].status == "accepted"
    guest = await table.service.repository.get_projection(table.player, table.room)
    assert {item.name for item in guest.items} == {"Открытый", "Назначенный"}
    table.actor = table.player
    assert (await table.client.get(table.url + "/cards/" + hidden["id"])).status_code == 403
    from app.events.projection import synchronize

    sync = await synchronize(table.service.repository, table.player, 0)
    assert hidden["name"] not in str(sync["snapshot"])
    assert hidden["id"] not in str(sync)


@pytest.mark.asyncio
async def test_delete_is_gm_only_reference_safe_soft_and_reversible(table):
    await table.execute("card.create", {"card": {"name": "Персонаж", "notes": "Сохрани меня"}})
    card = (await cards(table))[0]
    _, guest = await table.execute("card.delete", {"card_id": card["id"]}, table.player)
    assert guest.error_code == "forbidden"
    _, deleted = await table.execute("card.delete", {"card_id": card["id"]}, table.gm)
    assert deleted.status == "accepted", "card.delete must be a native durable command"
    assert await cards(table) == []
    assert (await table.client.get(table.url + "/cards/" + card["id"])).status_code == 404
    _, undo = await table.execute("action.undo", {"event_cursor": deleted.event_cursor})
    assert undo.status == "accepted", "card can be undone before the first scene"
    restored = (await cards(table))[0]
    assert restored["id"] == card["id"] and restored["notes"] == "Сохрани меня"
    assert restored["version"] > card["version"]
    await table.execute("scene.create", {"name": "Стол"})
    await table.execute("item.create", {"name": "Представление", "card_id": card["id"]})
    token = (await table.service.repository.get_projection(table.gm, table.room)).items[0]
    _, in_use = await table.execute("card.delete", {"card_id": card["id"]})
    assert in_use.error_code == "card_in_use"
    _, guest_delete = await table.execute("item.delete", {"item_id": str(token.id)}, table.player)
    assert guest_delete.error_code == "forbidden"
    command, deleted_token = await table.execute("item.delete", {"item_id": str(token.id)})
    assert deleted_token.status == "accepted"
    assert len(await cards(table)) == 1
    assert (await table.service.repository.get_projection(table.gm, table.room)).items == []
    assert await table.connection.fetchval(
        "select deleted_at is not null from app.scene_items where id=$1", token.id
    )
    assert (await table.service.execute_scene_command(table.gm, command)).status == "duplicate"
    _, restored_token = await table.execute(
        "action.undo", {"event_cursor": deleted_token.event_cursor}
    )
    assert restored_token.status == "accepted"
    assert (await table.service.repository.get_projection(table.gm, table.room)).items[
        0
    ].id == token.id
    await table.execute("item.delete", {"item_id": str(token.id)})
    _, deleted_card = await table.execute("card.delete", {"card_id": card["id"]})
    assert deleted_card.status == "accepted"
    assert await table.connection.fetchval(
        "select deleted_at is not null from app.cards where id=$1", UUID(card["id"])
    )
    _, unavailable = await table.execute(
        "card.resource", {"card_id": card["id"], "resource_key": "hp", "current": 1}
    )
    assert unavailable.error_code == "card_unavailable"
    _, invalid = await table.execute("item.create", {"card_id": card["id"]})
    assert invalid.error_code == "card_unavailable"
    assert (
        await table.connection.fetchval(
            "select count(*) from app.room_events where room_id=$1 and event_type='action.undo'",
            table.room,
        )
        == 2
    )


@pytest.mark.asyncio
async def test_latest_card_and_presentation_changes_compensate_without_erasing_history(table):
    await table.execute(
        "card.create",
        {
            "card": {
                "name": "Герой",
                "owner_participant_id": str(table.player.id),
                "resources": [{"key": "hp", "label": "HP", "current": 10, "max": 10}],
                "abilities": [
                    {
                        "name": "Сфера",
                        "geometry": {
                            "shape": "circle",
                            "origin": "token",
                            "radius": 10,
                            "units": "фут",
                        },
                    }
                ],
            }
        },
    )
    card = (await cards(table))[0]
    change_command, changed = await table.execute(
        "card.resource", {"card_id": card["id"], "resource_key": "hp", "current": 2}, table.player
    )
    assert changed.status == "accepted"
    _, guest = await table.execute(
        "action.undo", {"event_cursor": changed.event_cursor}, table.player
    )
    assert guest.error_code == "forbidden"
    undo_command, undone = await table.execute(
        "action.undo", {"event_cursor": changed.event_cursor}, table.gm
    )
    assert undone.status == "accepted", "resource changes must be reversible before a scene exists"
    assert (await cards(table))[0]["resources"][0]["current"] == 10
    assert (await table.service.execute_scene_command(table.gm, undo_command)).status == "duplicate"
    _, repeated_inverse = await table.execute("action.undo", {"event_cursor": changed.event_cursor})
    assert repeated_inverse.error_code == "not_reversible"
    assert (
        await table.connection.fetchval(
            "select count(*) from app.scene_commands where command_id=$1", change_command.command_id
        )
        == 1
    )
    assert (
        await table.connection.fetchval(
            "select count(*) from app.room_events where id=$1", changed.event_cursor
        )
        == 1
    )
    await table.execute("scene.create", {"name": "Стол"})
    await table.execute(
        "item.create",
        {"name": "Герой", "card_id": card["id"], "owner_participant_id": str(table.player.id)},
    )
    token = (await table.service.repository.get_projection(table.gm, table.room)).items[0]
    request = {
        "card_id": card["id"],
        "ability_id": card["abilities"][0]["id"],
        "origin_item_id": str(token.id),
    }
    _, presented = await table.execute("ability.present", request, table.player)
    assert presented.status == "accepted"
    first = (
        await table.service.repository.get_projection(table.gm, table.room)
    ).ability_presentations[0]
    _, replaced = await table.execute("ability.present", request, table.player)
    assert replaced.status == "accepted"
    assert (await table.execute("action.undo", {"event_cursor": replaced.event_cursor}, table.gm))[
        1
    ].status == "accepted"
    assert (
        await table.service.repository.get_projection(table.gm, table.room)
    ).ability_presentations[0].id == first.id
    _, cleared = await table.execute(
        "ability.clear", {"presentation_id": str(first.id)}, table.player
    )
    assert cleared.status == "accepted"
    assert (
        await table.service.repository.get_projection(table.gm, table.room)
    ).ability_presentations == []
    assert (await table.execute("action.undo", {"event_cursor": cleared.event_cursor}, table.gm))[
        1
    ].status == "accepted"
    assert (
        await table.service.repository.get_projection(table.gm, table.room)
    ).ability_presentations[0].id == first.id
    _, cloned = await table.execute("card.clone", {"card_id": card["id"]}, table.gm)
    assert cloned.status == "accepted"
    assert len(await cards(table)) == 2
    assert (await table.execute("action.undo", {"event_cursor": cloned.event_cursor}))[
        1
    ].status == "accepted"
    assert len(await cards(table)) == 1
    from app.events.projection import synchronize

    sync = await synchronize(table.service.repository, table.player, changed.event_cursor)
    assert any(event["type"] == "cards.changed" for event in sync["events"])
    assert (
        await table.connection.fetchval(
            "select count(*) from app.room_events where room_id=$1 and event_type='action.undo'",
            table.room,
        )
        == 4
    )


@pytest.mark.asyncio
async def test_creation_update_duplicate_and_linked_creation_have_safe_compensation_controls(table):
    data = {
        "name": "Герой",
        "resources": [{"key": "hp", "label": "HP", "current": 10, "max": 10}],
        "owner_participant_id": str(table.player.id),
        "visibility": "owner_only",
    }
    _, created = await table.execute("card.create", {"card": data})
    assert created.status == "accepted"
    card = (await cards(table))[0]
    _, undone = await table.execute("action.undo", {"event_cursor": created.event_cursor})
    assert undone.status == "accepted" and await cards(table) == []
    _, created = await table.execute("card.create", {"card": data})
    card = (await cards(table))[0]
    _, updated = await table.execute(
        "card.update",
        {"card_id": card["id"], "card": {**data, "name": "Новое имя", "notes": "Изменённое"}},
    )
    assert updated.status == "accepted"
    assert (await table.execute("action.undo", {"event_cursor": updated.event_cursor}))[
        1
    ].status == "accepted"
    restored = (await cards(table))[0]
    assert restored["name"] == "Герой" and restored["notes"] is None
    assert restored["version"] == 3
    await table.execute("scene.create", {"name": "Стол"})
    _, represented = await table.execute(
        "item.create", {"card_id": card["id"], "owner_participant_id": str(table.player.id)}
    )
    assert represented.status == "accepted"
    assert (await table.execute("action.undo", {"event_cursor": represented.event_cursor}))[
        1
    ].status == "accepted"
    assert len(await cards(table)) == 1
    assert (await table.service.repository.get_projection(table.gm, table.room)).items == []
    await table.execute(
        "item.create", {"card_id": card["id"], "owner_participant_id": str(table.player.id)}
    )
    token = (await table.service.repository.get_projection(table.gm, table.room)).items[0]
    _, duplicated = await table.execute("item.duplicate", {"item_id": str(token.id)})
    assert duplicated.status == "accepted" and len(await cards(table)) == 2
    assert (await table.execute("action.undo", {"event_cursor": duplicated.event_cursor}))[
        1
    ].status == "accepted"
    assert len(await cards(table)) == 1
    projection = await table.service.repository.get_projection(table.gm, table.room)
    assert [item.id for item in projection.items] == [token.id]
    # An explicitly public silhouette can represent a private card without leaking its ID.
    await table.execute("card.create", {"card": {"name": "Secret NPC", "kind": "npc"}})
    private = next(c for c in await cards(table) if c["name"] == "Secret NPC")
    await table.execute(
        "item.create",
        {"name": "Public silhouette", "card_id": private["id"], "visibility": "everyone"},
    )
    public = await table.service.repository.get_projection(table.player, table.room)
    assert any(item.name == "Public silhouette" and item.card_id is None for item in public.items)
    from app.events.projection import synchronize

    sync = await synchronize(table.service.repository, table.player, 0)
    assert private["id"] not in str(sync)
    journal = await table.client.get(table.url + "/journal")
    assert journal.status_code == 200
    assert "undo_state" not in journal.text and "Secret NPC" not in journal.text
    # A removed owner must not be silently resurrected by card undo.
    _, removed = await table.execute("card.delete", {"card_id": card["id"]})
    assert removed.status == "rejected" and removed.error_code == "card_in_use"
    await table.execute("item.delete", {"item_id": str(token.id)})
    _, deleted = await table.execute("card.delete", {"card_id": card["id"]})
    assert deleted.status == "accepted"
    await table.connection.execute(
        "update app.participants set removed_at=now() where id=$1", table.player.id
    )
    _, invalid = await table.execute("action.undo", {"event_cursor": deleted.event_cursor})
    assert invalid.error_code == "forbidden"
    assert all(c["id"] != card["id"] for c in await cards(table))


@pytest.mark.asyncio
async def test_cross_room_assignment_and_invalid_restore_references_are_rejected(table):
    from uuid import uuid4

    foreign_room, foreign_owner = uuid4(), uuid4()
    await table.connection.execute(
        "insert into app.rooms(id,campaign_id,owner_user_id,name) values($1,$2,$3,$4)",
        foreign_room,
        table.campaign,
        table.gm.user_id,
        "Other room",
    )
    try:
        await table.connection.execute(
            "insert into app.participants(id,campaign_id,room_id,identity_kind,display_name) "
            "values($1,$2,$3,'guest','Foreign')",
            foreign_owner,
            table.campaign,
            foreign_room,
        )
        _, foreign_card = await table.execute(
            "card.create",
            {"card": {"name": "Foreign owner", "owner_participant_id": str(foreign_owner)}},
        )
        assert foreign_card.error_code == "forbidden"
        data = {
            "name": "Owned",
            "visibility": "owner_only",
            "owner_participant_id": str(table.player.id),
            "abilities": [
                {
                    "name": "Circle",
                    "geometry": {"shape": "circle", "origin": "token", "radius": 5, "units": "фут"},
                }
            ],
        }
        await table.execute("card.create", {"card": data})
        card = (await cards(table))[0]
        await table.execute("scene.create", {"name": "Table"})
        _, foreign_token = await table.execute(
            "item.create", {"card_id": card["id"], "owner_participant_id": str(foreign_owner)}
        )
        assert foreign_token.error_code == "forbidden"
        await table.execute("item.create", {"card_id": card["id"]})
        token = (await table.service.repository.get_projection(table.gm, table.room)).items[0]
        _, mismatch = await table.execute("item.duplicate", {"item_id": str(token.id)})
        assert mismatch.error_code == "forbidden"
        assert len(await cards(table)) == 1
        await table.execute(
            "item.update", {"item_id": str(token.id), "owner_participant_id": str(table.player.id)}
        )
        _, presented = await table.execute(
            "ability.present",
            {
                "card_id": card["id"],
                "ability_id": card["abilities"][0]["id"],
                "origin_item_id": str(token.id),
            },
        )
        assert presented.status == "accepted"
        presentation = (
            await table.service.repository.get_projection(table.gm, table.room)
        ).ability_presentations[0]
        _, cleared = await table.execute("ability.clear", {"presentation_id": str(presentation.id)})
        assert cleared.status == "accepted"
        # Fixture-controlled stale references exercise the public undo rejection.
        await table.connection.execute(
            "update app.scene_items set deleted_at=now() where id=$1", token.id
        )
        _, missing_origin = await table.execute(
            "action.undo", {"event_cursor": cleared.event_cursor}
        )
        assert missing_origin.error_code == "item_unavailable"
        assert (
            await table.service.repository.get_projection(table.gm, table.room)
        ).ability_presentations == []
        await table.connection.execute(
            "update app.scene_items set deleted_at=null where id=$1", token.id
        )
        _, deleted = await table.execute("item.delete", {"item_id": str(token.id)})
        assert deleted.status == "accepted"
        await table.connection.execute(
            "update app.scene_items set version=version+1 where id=$1", token.id
        )
        _, stale = await table.execute("action.undo", {"event_cursor": deleted.event_cursor})
        assert stale.error_code == "stale_version"
        assert (await table.service.repository.get_projection(table.gm, table.room)).items == []
        # Card compensation keeps the source room's authority stream even when a scene is shared.
        import os

        from app.campaigns.repository import PostgresCampaignRepository
        from app.events.projection import synchronize

        await table.connection.execute(
            "insert into app.participants(campaign_id,room_id,user_id,role,display_name) "
            "values($1,$2,$3,'gm','Other GM')",
            table.campaign,
            foreign_room,
            table.gm.user_id,
        )
        scene = (await table.service.repository.get_projection(table.gm, table.room)).scene
        await table.connection.execute(
            "update app.rooms set active_scene_id=$1 where id=$2", scene.id, foreign_room
        )
        authority = PostgresCampaignRepository(os.environ["VTT_TEST_DATABASE_URL"])
        try:
            other_gm = await authority.resolve_registered(table.gm.user_id, foreign_room)
            before = await table.service.repository.get_projection(other_gm, foreign_room)
            await table.execute(
                "card.create",
                {
                    "card": {
                        "name": "Room-local",
                        "resources": [{"key": "hp", "label": "HP", "current": 4}],
                    }
                },
            )
            local = next(c for c in await cards(table) if c["name"] == "Room-local")
            _, changed = await table.execute(
                "card.resource", {"card_id": local["id"], "resource_key": "hp", "current": 1}
            )
            assert (await table.execute("action.undo", {"event_cursor": changed.event_cursor}))[
                1
            ].status == "accepted"
            after = await table.service.repository.get_projection(other_gm, foreign_room)
            assert after.aggregate_version == before.aggregate_version
            assert after.event_cursor == before.event_cursor
            assert (await synchronize(table.service.repository, other_gm, before.event_cursor))[
                "events"
            ] == []
        finally:
            await authority._engine.dispose()
    finally:
        await table.connection.execute("delete from app.rooms where id=$1", foreign_room)
        assert (
            await table.connection.fetchval(
                "select count(*) from app.rooms where id=$1", foreign_room
            )
            == 0
        )
        assert (
            await table.connection.fetchval(
                "select count(*) from app.participants where id=$1", foreign_owner
            )
            == 0
        )


@pytest.mark.asyncio
async def test_shared_scene_delete_undo_preserves_origin_room_card_and_owner(table):
    import os
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.campaigns.repository import PostgresCampaignRepository
    from app.scenes.models import Command

    await table.execute(
        "card.create",
        {"card": {"name": "Origin owned card", "owner_participant_id": str(table.player.id)}},
    )
    card = (await cards(table))[0]
    await table.execute("scene.create", {"name": "Shared"})
    await table.execute(
        "item.create", {"card_id": card["id"], "owner_participant_id": str(table.player.id)}
    )
    before = await table.service.repository.get_projection(table.gm, table.room)
    token = before.items[0]
    other_room = uuid4()
    authority = PostgresCampaignRepository(os.environ["VTT_TEST_DATABASE_URL"])
    await table.connection.execute(
        "insert into app.rooms(id,campaign_id,owner_user_id,name,active_scene_id,scene_version) "
        "values($1,$2,$3,'Shared observer',$4,0)",
        other_room,
        table.campaign,
        table.gm.user_id,
        before.scene.id,
    )
    try:
        await table.connection.execute(
            "insert into app.participants(campaign_id,room_id,user_id,role,display_name) "
            "values($1,$2,$3,'gm','Shared GM')",
            table.campaign,
            other_room,
            table.gm.user_id,
        )
        other_gm = await authority.resolve_registered(table.gm.user_id, other_room)

        async def command(kind, payload):
            current = await table.service.repository.get_projection(other_gm, other_room)
            return await table.service.execute_scene_command(
                other_gm,
                Command(
                    command_id=uuid4(),
                    room_id=other_room,
                    actor_session_id=other_gm.id,
                    expected_aggregate_version=current.aggregate_version,
                    type=kind,
                    payload=payload,
                    client_sent_at=datetime.now(UTC),
                ),
            )

        # Retaining an existing reference is distinct from creating a new foreign assignment.
        foreign = await command(
            "item.create", {"card_id": card["id"], "owner_participant_id": str(table.player.id)}
        )
        assert foreign.status == "rejected" and foreign.error_code == "card_unavailable"
        assigned = await command(
            "item.update", {"item_id": str(token.id), "owner_participant_id": str(table.player.id)}
        )
        assert assigned.status == "rejected" and assigned.error_code == "forbidden"
        deleted = await command("item.delete", {"item_id": str(token.id)})
        assert deleted.status == "accepted"
        undone = await command("action.undo", {"event_cursor": deleted.event_cursor})
        assert undone.status == "accepted", (undone.error_code, undone.message)
        restored = await table.service.repository.get_projection(table.gm, table.room)
        observer = await table.service.repository.get_projection(other_gm, other_room)
        assert len(restored.items) == len(observer.items) == 1
        assert restored.items[0].id == observer.items[0].id == token.id
        assert restored.items[0].card_id == UUID(card["id"])
        assert restored.items[0].owner_participant_id == table.player.id
        assert restored.aggregate_version == before.aggregate_version + 2
        assert observer.aggregate_version == 2
        assert undone.aggregate_version == 2
        assert restored.event_cursor == observer.event_cursor == undone.event_cursor
        assert (
            await table.connection.fetchval(
                "select version from app.scene_items where id=$1", token.id
            )
            == 3
        )
        assert (
            await table.connection.fetchval(
                "select count(*) from app.scene_items where scene_id=$1 and deleted_at is null",
                before.scene.id,
            )
            == 1
        )
        deleted_again = await command("item.delete", {"item_id": str(token.id)})
        assert deleted_again.status == "accepted"
        await table.connection.execute(
            "update app.participants set removed_at=now() where id=$1", table.player.id
        )
        invalid_owner = await command("action.undo", {"event_cursor": deleted_again.event_cursor})
        assert invalid_owner.status == "rejected" and invalid_owner.error_code == "forbidden"
        await table.connection.execute(
            "update app.participants set removed_at=null where id=$1", table.player.id
        )
        await table.connection.execute(
            "update app.cards set deleted_at=now() where id=$1", UUID(card["id"])
        )
        invalid_card = await command("action.undo", {"event_cursor": deleted_again.event_cursor})
        assert invalid_card.status == "rejected" and invalid_card.error_code == "card_unavailable"
        assert (
            await table.service.repository.get_projection(table.gm, table.room)
        ).aggregate_version == before.aggregate_version + 3
        assert (
            await table.service.repository.get_projection(other_gm, other_room)
        ).aggregate_version == 3
        assert await table.connection.fetchval(
            "select deleted_at is not null from app.scene_items where id=$1", token.id
        )
        assert (
            await table.connection.fetchval(
                "select version from app.scene_items where id=$1", token.id
            )
            == 4
        )
    finally:
        await authority._engine.dispose()
        await table.connection.execute("delete from app.rooms where id=$1", other_room)
        assert (
            await table.connection.fetchval(
                "select count(*) from app.rooms where id=$1", other_room
            )
            == 0
        )
