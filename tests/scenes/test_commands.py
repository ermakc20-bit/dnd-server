from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg
import pytest
from app.campaigns.repository import PostgresCampaignRepository
from app.identity.models import Participant
from app.scenes.models import Command
from app.scenes.repository import SceneRepository
from app.scenes.service import SceneService

DATABASE_URL = os.getenv("VTT_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="local PostgreSQL not configured")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "lifecycle",
        "authorization",
        "concurrency",
        "validation",
        "500",
        "event_scene_create",
        "event_item_create",
        "event_item_update",
        "event_item_duplicate",
    ],
)
async def test_scene_command_contract(scenario: str) -> None:
    assert DATABASE_URL is not None
    connection = await asyncpg.connect(DATABASE_URL)
    owner, campaign, room, guest, guest_session = (uuid4() for _ in range(5))
    await connection.execute(
        "insert into auth.users(id,email) values($1,$2)", owner, f"command-{owner}@example.invalid"
    )
    await connection.execute(
        "insert into app.campaigns(id,owner_user_id,name) values($1,$2,'Commands')",
        campaign,
        owner,
    )
    await connection.execute(
        "insert into app.rooms(id,campaign_id,owner_user_id,name) values($1,$2,$3,'Commands')",
        room,
        campaign,
        owner,
    )
    await connection.execute(
        """insert into app.participants
        (campaign_id,room_id,user_id,role,display_name) values($1,$2,$3,'gm','GM')""",
        campaign,
        room,
        owner,
    )
    await connection.execute(
        """insert into app.participants
        (id,campaign_id,room_id,identity_kind,display_name) values($1,$2,$3,'guest','Guest')""",
        guest,
        campaign,
        room,
    )
    await connection.execute(
        """insert into app.guest_sessions
        (id,participant_id,token_hash,expires_at) values($1,$2,$3,now()+interval '1 hour')""",
        guest_session,
        guest,
        str(uuid4()),
    )
    gm = await PostgresCampaignRepository(DATABASE_URL).resolve_registered(owner, room)
    player = Participant(
        id=guest,
        campaign_id=campaign,
        room_id=room,
        role="player",
        display_name="Guest",
        guest_session_id=guest_session,
        joined_at=datetime.now(UTC),
    )
    repository = SceneRepository(DATABASE_URL)
    service = SceneService(repository)
    version = 0

    async def execute(
        kind: str, payload: dict, actor: Participant = gm, expected: int | None = None
    ):
        nonlocal version
        command = Command(
            command_id=uuid4(),
            room_id=room,
            actor_session_id=actor.guest_session_id or actor.id,
            expected_aggregate_version=version if expected is None else expected,
            type=kind,
            payload=payload,
            client_sent_at=datetime.now(UTC),
        )
        result = await service.execute_scene_command(actor, command)
        if result.status == "accepted":
            version = result.aggregate_version
        return command, result

    try:
        initial_command, result = await execute("scene.create", {"name": "Battlefield"})
        assert result.status == "accepted"
        assert result.aggregate_version == 1 and result.event_cursor is not None
        projection = await repository.get_projection(gm, room)
        scene_id = str(projection.scene.id)
        assert projection.scene.name == "Battlefield"
        assert projection.aggregate_version == 1

        if scenario.startswith("event_"):
            command = initial_command
            expected_position = None
            if scenario != "event_scene_create":
                command, result = await execute(
                    "item.create",
                    {"name": "Secret", "x": 96, "y": -33, "visibility": "gm_only"},
                )
                original = (await repository.get_projection(gm, room)).items[0]
                expected_position = (128, -64)
                if scenario == "event_item_update":
                    command, result = await execute(
                        "item.update",
                        {"item_id": str(original.id), "x": 161, "y": 33, "rotation": 45},
                    )
                    expected_position = (192, 64)
                elif scenario == "event_item_duplicate":
                    command, result = await execute("item.duplicate", {"item_id": str(original.id)})
                    expected_position = (192, 0)
            assert result.status == "accepted"
            state = await repository.get_projection(gm, room)
            event = await connection.fetchrow(
                """select id,scene_id,aggregate_id,aggregate_version,event_type,payload
                from app.room_events where command_id=$1""",
                command.command_id,
            )
            assert event["id"] == result.event_cursor == state.event_cursor
            assert event["scene_id"] == state.scene.id
            assert event["aggregate_id"] == room
            assert event["aggregate_version"] == result.aggregate_version == state.aggregate_version
            assert event["event_type"] == command.type
            canonical = json.loads(event["payload"])
            if scenario == "event_scene_create":
                durable = json.loads(
                    await connection.fetchval(
                        """select to_jsonb(saved) from (
                    select id,name,width,height,grid_size,grid_enabled,snap_enabled,
                    unit_size,unit_label
                    from app.scenes where id=$1) saved""",
                        state.scene.id,
                    )
                )
                assert canonical == {"scene_id": scene_id, "scene": durable}
                assert canonical["scene"] == state.scene.model_dump(mode="json")
            else:
                changed = state.items[-1]
                if scenario == "event_item_duplicate":
                    assert changed.id != original.id
                durable = json.loads(
                    await connection.fetchval(
                        """select to_jsonb(saved) from (
                    select id,kind,name,asset_id,x,y,width,height,rotation,z_index,visibility,
                    is_locked,owner_participant_id,card_id from app.scene_items
                    where id=$1) saved""",
                        changed.id,
                    )
                )
                assert canonical == {"scene_id": scene_id, "item": durable}
                assert canonical["item"] == changed.model_dump(
                    mode="json", exclude={"can_transform"}
                )
                assert (canonical["item"]["x"], canonical["item"]["y"]) == expected_position
                # The canonical event is server-internal, never a substitute for role projection.
                guest_projection = await repository.get_projection(player, room)
                assert guest_projection.items == []
                assert "Secret" not in guest_projection.model_dump_json()
                assert "payload" not in guest_projection.model_dump()
            receipt_before = await connection.fetchval(
                "select result from app.scene_commands where command_id=$1", command.command_id
            )
            duplicate = await service.execute_scene_command(gm, command)
            assert duplicate == result.model_copy(update={"status": "duplicate"})
            assert await repository.get_projection(gm, room) == state
            assert (
                await connection.fetchval(
                    "select result from app.scene_commands where command_id=$1", command.command_id
                )
                == receipt_before
            )
            assert (
                await connection.fetchval(
                    "select count(*) from app.room_events where command_id=$1", command.command_id
                )
                == 1
            )
            assert (
                await connection.fetchval(
                    "select payload from app.room_events where command_id=$1", command.command_id
                )
                == event["payload"]
            )
        elif scenario == "lifecycle":
            await execute("scene.rename", {"scene_id": scene_id, "name": "Tavern"})
            await execute(
                "scene.grid",
                {"grid_size": 80, "unit_size": 1.5, "unit_label": "м", "snap_enabled": True},
            )
            _, created = await execute("item.create", {"name": "Guard", "x": 80, "y": 160})
            assert created.status == "accepted"
            item = (await repository.get_projection(gm, room)).items[0]
            _, transformed = await execute(
                "item.update",
                {
                    "item_id": str(item.id),
                    "x": 240,
                    "width": 120,
                    "height": 80,
                    "rotation": 90,
                    "z_index": 4,
                    "is_locked": True,
                },
            )
            assert transformed.status == "accepted"
            await execute("item.duplicate", {"item_id": str(item.id)})
            state = await repository.get_projection(gm, room)
            assert len(state.items) == 2 and state.items[0].id != state.items[1].id
            assert state.items[0].rotation == 90 and state.items[0].is_locked
            assert state.scene.grid_size == 80 and state.scene.unit_size == 1.5
            await execute("scene.create", {"name": "Dungeon"})
            assert (await repository.get_projection(gm, room)).scene.name == "Dungeon"
            await execute("scene.activate", {"scene_id": scene_id})
            assert (await repository.get_projection(gm, room)).scene.name == "Tavern"
            # Reopening a new repository restores durable state.
            reopened = SceneRepository(DATABASE_URL)
            assert len((await reopened.get_projection(gm, room)).items) == 2
            await reopened.engine.dispose()
        elif scenario == "authorization":
            await execute("item.create", {"name": "Mine", "owner_participant_id": str(guest)})
            await execute("item.create", {"name": "Other"})
            await execute("item.create", {"name": "Secret", "visibility": "gm_only"})
            gm_items = (await repository.get_projection(gm, room)).items
            visible = await repository.get_projection(player, room)
            assert [item.name for item in visible.items] == ["Mine", "Other"]
            assert len(visible.scenes) == 1 and visible.can_manage is False
            assert [item.can_transform for item in visible.items] == [True, False]
            for item in gm_items[1:]:
                _, denied = await execute(
                    "item.update", {"item_id": str(item.id), "x": 999}, player
                )
                assert denied.error_code == "forbidden"
            _, moved = await execute(
                "item.update", {"item_id": str(gm_items[0].id), "x": 96}, player
            )
            assert moved.status == "accepted"
            assert (await repository.get_projection(player, room)).items[0].x == 128
            for payload in (
                {"owner_participant_id": str(gm.id)},
                {"visibility": "gm_only"},
                {"is_locked": True},
                {"asset_id": str(uuid4())},
            ):
                _, denied = await execute(
                    "item.update", {"item_id": str(gm_items[0].id), **payload}, player
                )
                assert denied.error_code == "forbidden"
            await execute(
                "item.update", {"item_id": str(gm_items[0].id), "owner_participant_id": None}
            )
            _, denied = await execute(
                "item.update", {"item_id": str(gm_items[0].id), "x": 5}, player
            )
            assert denied.error_code == "forbidden"
            await connection.execute(
                "update app.participants set removed_at=now() where id=$1", guest
            )
            _, denied = await execute(
                "item.update", {"item_id": str(gm_items[0].id), "x": 5}, player
            )
            assert denied.error_code == "forbidden"
        elif scenario == "concurrency":
            command, accepted = await execute("item.create", {"name": "One"})
            duplicate = await service.execute_scene_command(gm, command)
            assert (
                duplicate.status == "duplicate" and duplicate.event_cursor == accepted.event_cursor
            )
            assert len((await repository.get_projection(gm, room)).items) == 1
            changed = command.model_copy(update={"payload": {"name": "Collision"}})
            assert (
                await service.execute_scene_command(gm, changed)
            ).error_code == "command_conflict"
            _, stale = await execute(
                "scene.rename", {"scene_id": scene_id, "name": "Wrong"}, expected=0
            )
            assert stale.error_code == "stale_version"
            first = command.model_copy(
                update={
                    "command_id": uuid4(),
                    "expected_aggregate_version": version,
                    "payload": {"name": "Concurrent A"},
                }
            )
            second = first.model_copy(
                update={"command_id": uuid4(), "payload": {"name": "Concurrent B"}}
            )
            concurrent = await asyncio.gather(
                service.execute_scene_command(gm, first), service.execute_scene_command(gm, second)
            )
            assert sorted(result.status for result in concurrent) == ["accepted", "rejected"]
            assert (
                next(result for result in concurrent if result.status == "rejected").error_code
                == "stale_version"
            )
            version += 1
            before = await connection.fetchval(
                "select count(*) from app.room_events where room_id=$1", room
            )
            _, invalid = await execute("item.create", {"asset_id": str(uuid4())})
            assert invalid.error_code == "asset_unavailable"
            assert (
                await connection.fetchval(
                    "select count(*) from app.room_events where room_id=$1", room
                )
                == before
            )
            _, invalid = await execute("item.update", {"item_id": str(uuid4()), "x": float("inf")})
            assert invalid.status == "rejected"
            _, invalid = await execute("scene.activate", {"scene_id": str(uuid4())})
            assert invalid.error_code == "scene_unavailable"
        elif scenario == "validation":
            _, created = await execute("item.create", {"name": "Validated"})
            assert created.status == "accepted"
            item = (await repository.get_projection(gm, room)).items[0]
            for kind, payload in (
                ("item.create", {"width": 0.001}),
                ("item.create", {"height": 0.001}),
                ("item.update", {"item_id": str(item.id), "width": 0.001}),
                ("item.update", {"item_id": str(item.id), "height": 0.001}),
            ):
                _, rejected = await execute(kind, payload)
                assert rejected.status == "rejected" and rejected.error_code == "invalid_command"
            state = await repository.get_projection(gm, room)
            assert state.aggregate_version == 2 and len(state.items) == 1
            assert state.items[0].width == 64 and state.items[0].height == 64
        else:
            for index in range(500):
                _, result = await execute(
                    "item.create",
                    {
                        "name": f"Token {index}",
                        "x": index * 64,
                        "z_index": index,
                        "owner_participant_id": str(guest),
                    },
                )
                assert result.status == "accepted"
            visible = await repository.get_projection(player, room)
            assert len(visible.items) == 500
            assert visible.items[-1].name == "Token 499" and visible.items[-1].x == 31936
        assert (
            await connection.fetchval("select scene_version from app.rooms where id=$1", room)
            == version
        )
        assert (
            await connection.fetchval("select count(*) from app.room_events where room_id=$1", room)
            == version
        )
        assert (
            await connection.fetchval(
                """select count(*) from app.scene_commands
            where room_id=$1 and result->>'status'='accepted'""",
                room,
            )
            == version
        )
        assert (
            await connection.fetchval(
                """select count(*) from app.room_events
            where room_id=$1 and aggregate_id=$1 and aggregate_version>0""",
                room,
            )
            == version
        )
    finally:
        await connection.execute("delete from app.campaigns where id=$1", campaign)
        await connection.execute("delete from auth.users where id=$1", owner)
        await repository.engine.dispose()
        await connection.close()
