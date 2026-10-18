from __future__ import annotations

import hashlib
import json
import math
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.ability_geometry.service import apply_ability_command
from app.access.database import participant_is_active
from app.access.policy import Action, ObjectAccess, authorize
from app.card_import.service import apply_import_command
from app.cards.repository import load_card
from app.cards.service import apply_card_command, duplicate_card_for_token
from app.dice_log.service import roll
from app.identity.models import Participant
from app.scene_tools.annotations import apply_annotation
from app.scene_tools.geometry import object_visible
from app.scene_tools.models import Fog
from app.scene_tools.service import apply_tool_command
from app.scene_tools.undo import apply_undo, capture_inverse, finish_inverse
from app.scenes.models import Command, CommandResult, Scene, SceneFailure, SceneItem
from app.scenes.payloads import PAYLOAD_TYPES, CreateItem
from app.scenes.repository import SceneRepository


class SceneService:
    def __init__(self, repository: SceneRepository) -> None:
        self.repository = repository

    async def execute_scene_command(self, actor: Participant, command: Command) -> CommandResult:
        fingerprint = hashlib.sha256(
            json.dumps(
                command.model_dump(mode="json"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        async with self.repository.engine.begin() as connection:
            await connection.execute(
                text("select pg_advisory_xact_lock(hashtextextended(:command_id,0))"),
                {"command_id": str(command.command_id)},
            )
            campaign = await connection.scalar(
                text("select campaign_id from app.rooms where id=:room and not is_archived"),
                {"room": command.room_id},
            )
            # Shared scenes can be changed through any room. Acquire the same
            # ordered room locks before reading versions or mutating scene state.
            rooms = (
                (
                    await connection.execute(
                        text("""
                    select id,campaign_id,active_scene_id,scene_version from app.rooms
                    where campaign_id=:campaign and not is_archived order by id for update
                """),
                        {"campaign": campaign},
                    )
                )
                .mappings()
                .all()
            )
            room = next((row for row in rooms if row["id"] == command.room_id), None)
            if (
                room is None
                or not authorize(actor, Action.VIEW_ROOM, command.room_id).allowed
                or (actor.authorization_expires_at is not None and actor.authorization_expired)
                or not await participant_is_active(connection, actor)
                or command.actor_session_id != (actor.guest_session_id or actor.id)
            ):
                return self._rejected(command, "forbidden", "Нет доступа к сцене")
            previous = (
                (
                    await connection.execute(
                        text("""
                select room_id,actor_participant_id,payload_hash,result from app.scene_commands
                where command_id=:id
            """),
                        {"id": command.command_id},
                    )
                )
                .mappings()
                .first()
            )
            if previous is not None:
                if (
                    previous["room_id"] != command.room_id
                    or previous["actor_participant_id"] != actor.id
                    or previous["payload_hash"] != fingerprint
                ):
                    return self._rejected(
                        command, "command_conflict", "Идентификатор команды занят"
                    )
                result = CommandResult.model_validate(previous["result"])
                return result.model_copy(update={"status": "duplicate"})
            undo_state = None
            try:
                if command.expected_aggregate_version != room["scene_version"]:
                    raise SceneFailure("stale_version", "Сцена обновилась. Обновите состояние")
                async with connection.begin_nested():
                    scene_id: UUID | None
                    if command.type.startswith(
                        ("fog.", "annotation.", "ability.")
                    ) and not await connection.scalar(
                        text(
                            "select id from app.scenes where id=:scene and campaign_id=:campaign "
                            "and deleted_at is null"
                        ),
                        {"scene": room["active_scene_id"], "campaign": actor.campaign_id},
                    ):
                        raise SceneFailure("scene_unavailable", "Сцена недоступна")
                    if command.type.startswith(("card.", "ability.")) or command.type in {
                        "dice.roll",
                        "import.confirm",
                    }:
                        undo_state = await capture_inverse(
                            connection, command.type, command.payload, dict(room), actor
                        )
                    if command.type.startswith("ability."):
                        scene_id, event_payload = await apply_ability_command(
                            connection, actor, command.type, command.payload, dict(room)
                        )
                    elif command.type.startswith("fog."):
                        scene_id, event_payload, undo_state = await apply_tool_command(
                            connection, actor, command.type, command.payload, dict(room)
                        )
                    elif command.type.startswith("annotation."):
                        scene_id, event_payload, undo_state = await apply_annotation(
                            connection, actor, command.type, command.payload, dict(room)
                        )
                    elif command.type == "action.undo":
                        scene_id, event_payload = await apply_undo(
                            connection, actor, command.payload, dict(room)
                        )
                    elif command.type == "dice.roll":
                        scene_id = room["active_scene_id"]
                        event_payload = await roll(
                            connection, actor, command.payload, command.command_id
                        )
                    elif command.type == "import.confirm":
                        scene_id = room["active_scene_id"]
                        event_payload = await apply_import_command(
                            connection, actor, command.payload, dict(room)
                        )
                    elif command.type.startswith("card."):
                        scene_id = room["active_scene_id"]
                        event_payload = await apply_card_command(
                            connection, actor, command.type, command.payload
                        )
                    else:
                        model = PAYLOAD_TYPES.get(command.type)
                        if model is None:
                            raise SceneFailure("invalid_command", "Неизвестная команда")
                        payload_model = model.model_validate(command.payload)
                        payload = payload_model.model_dump(exclude_unset=True)
                        if command.type == "item.create":
                            payload = payload_model.model_dump()
                        if any(
                            value is None
                            for key, value in payload.items()
                            if key not in {"owner_participant_id", "asset_id", "card_id"}
                        ):
                            raise SceneFailure("invalid_command", "Недопустимое значение поля")
                        undo_state = await capture_inverse(
                            connection, command.type, payload, dict(room), actor
                        )
                        scene_id, event_payload = await self._apply(
                            connection, actor, command, dict(room), payload
                        )
                    undo_state = await finish_inverse(
                        connection, undo_state, command.type, event_payload, scene_id
                    )
                version = int(room["scene_version"]) + 1
                effective_type = event_payload.get("undo_type", command.type)
                shared_change = (
                    effective_type
                    not in {
                        "scene.activate",
                        "dice.roll",
                    }
                    and not effective_type.startswith("card.")
                    and "card_id" not in event_payload
                )
                affected = [
                    row["id"]
                    for row in rooms
                    if row["id"] == command.room_id
                    or (
                        shared_change
                        and (
                            row["active_scene_id"] == scene_id
                            or effective_type in {"scene.create", "scene.rename"}
                        )
                    )
                ]
                await connection.execute(
                    text("""
                    update app.rooms set scene_version=scene_version+1
                    where id=any(cast(:rooms as uuid[]))
                """),
                    {"rooms": affected},
                )
                result = CommandResult(
                    command_id=command.command_id, status="accepted", aggregate_version=version
                )
            except ValidationError:
                result = self._rejected(command, "invalid_command", "Проверьте параметры команды")
            except SceneFailure as error:
                result = self._rejected(command, error.code, error.message)
            await connection.execute(
                text("""
                insert into app.scene_commands
                  (command_id,room_id,actor_participant_id,payload_hash,result)
                values(:id,:room,:actor,:hash,cast(:result as jsonb))
            """),
                {
                    "id": command.command_id,
                    "room": command.room_id,
                    "actor": actor.id,
                    "hash": fingerprint,
                    "result": result.model_dump_json(),
                },
            )
            if result.status == "accepted":
                cursor = await connection.scalar(
                    text("""
                    insert into app.room_events(room_id,scene_id,actor_user_id,actor_participant_id,
                        event_type,aggregate_id,aggregate_version,payload,command_id,undo_state)
                    values(:room,:scene,:user,:actor,:type,:room,:version,
                           cast(:payload as jsonb),:id,cast(:undo_state as jsonb))
                    returning id
                """),
                    {
                        "room": command.room_id,
                        "scene": scene_id,
                        "user": actor.user_id,
                        "actor": actor.id,
                        "type": command.type,
                        "version": result.aggregate_version,
                        "payload": json.dumps(event_payload),
                        "undo_state": json.dumps(undo_state) if undo_state else None,
                        "id": command.command_id,
                    },
                )
                result.event_cursor = int(cursor or 0)
                await connection.execute(
                    text("""
                    update app.scene_commands set result=cast(:result as jsonb) where command_id=:id
                """),
                    {"result": result.model_dump_json(), "id": command.command_id},
                )
            if actor.authorization_expires_at is not None and actor.authorization_expired:
                await connection.rollback()
                return self._rejected(command, "forbidden", "Сессия недействительна")
            return result

    async def notification_rooms(self, actor: Participant) -> list[UUID]:
        # A wakeup is payload-free; the recipient's PG projection remains the
        # authority. Include the campaign's rooms to cover scene-list changes.
        async with self.repository.engine.connect() as connection:
            return list(
                (
                    await connection.scalars(
                        text(
                            "select id from app.rooms where campaign_id=:campaign "
                            "and not is_archived"
                        ),
                        {"campaign": actor.campaign_id},
                    )
                ).all()
            )

    @staticmethod
    def _rejected(command: Command, code: str, message: str) -> CommandResult:
        return CommandResult(
            command_id=command.command_id, status="rejected", error_code=code, message=message
        )

    async def _apply(
        self,
        connection: AsyncConnection,
        actor: Participant,
        command: Command,
        room: dict[str, Any],
        payload: dict[str, Any],
    ) -> tuple[UUID, dict[str, Any]]:
        manages = authorize(actor, Action.MANAGE_SCENE, command.room_id).allowed
        if command.type != "item.update" and not manages:
            raise SceneFailure("forbidden", "Нет прав на изменение сцены")
        campaign_id = room["campaign_id"]
        scene_id: UUID | None = room["active_scene_id"]
        item_id: UUID | None = None
        if command.type == "scene.create":
            scene_id = uuid4()
            await connection.execute(
                text("""
                insert into app.scenes(id,room_id,campaign_id,name)
                values(:id,:room,:campaign,:name)
            """),
                {
                    "id": scene_id,
                    "room": command.room_id,
                    "campaign": campaign_id,
                    "name": payload["name"],
                },
            )
            await connection.execute(
                text("update app.rooms set active_scene_id=:id where id=:room"),
                {"id": scene_id, "room": command.room_id},
            )
            return scene_id, await self._event_payload(connection, scene_id)
        if command.type in {"scene.rename", "scene.activate"}:
            scene_id = payload.pop("scene_id")
        scene = (
            (
                await connection.execute(
                    text("""
            select id,grid_size,snap_enabled,fog from app.scenes
            where id=:id and campaign_id=:campaign and deleted_at is null
            for update
        """),
                    {"id": scene_id, "campaign": campaign_id},
                )
            )
            .mappings()
            .first()
        )
        if scene is None or scene_id is None:
            raise SceneFailure("scene_unavailable", "Сцена недоступна")
        if command.type == "scene.activate":
            await connection.execute(
                text("update app.rooms set active_scene_id=:id where id=:room"),
                {"id": scene_id, "room": command.room_id},
            )
        elif command.type in {"scene.rename", "scene.grid"}:
            await self._update(connection, "scenes", scene_id, payload)
        else:
            item_kind = payload.get("kind", "token")
            if command.type in {"item.update", "item.duplicate", "item.delete"}:
                item_id = payload.pop("item_id")
                item = (
                    (
                        await connection.execute(
                            text("""
                    select id,kind,name,asset_id,x,y,width,height,rotation,z_index,visibility,
                      is_locked,owner_participant_id,card_id from app.scene_items
                    where id=:item and scene_id=:scene and deleted_at is null and kind in
('map','token') for update
                """),
                            {"item": item_id, "scene": scene_id},
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    item is None
                    or not authorize(
                        actor,
                        Action.TRANSFORM_ITEM,
                        command.room_id,
                        object_access=ObjectAccess.model_validate(item),
                    ).allowed
                ):
                    raise SceneFailure("forbidden", "Нет прав на этот токен")
                if not manages and not object_visible(
                    Fog.model_validate(scene["fog"]),
                    item["x"],
                    item["y"],
                    item["width"],
                    item["height"],
                    item["rotation"],
                ):
                    raise SceneFailure("forbidden", "Токен скрыт туманом")
                if command.type == "item.delete":
                    await connection.execute(
                        text(
                            "update app.scene_items set "
                            "deleted_at=now(),version=version+1,updated_at=now() where id=:id"
                        ),
                        {"id": item_id},
                    )
                    deleted = await self._event_payload(connection, scene_id, item_id)
                    deleted["deleted"] = True
                    return scene_id, deleted
                if command.type == "item.duplicate":
                    payload = dict(item)
                    payload.pop("id")
                    payload["x"] += scene["grid_size"]
                    payload["y"] += scene["grid_size"]
                    if payload["card_id"] is not None:
                        payload["card_id"] = await duplicate_card_for_token(
                            connection, actor, payload["card_id"], payload["owner_participant_id"]
                        )
                elif not manages and set(payload) - {"x", "y", "width", "height", "rotation"}:
                    raise SceneFailure("forbidden", "Разрешено только перемещение своего токена")
                item_kind = item["kind"]
            owner = payload.get("owner_participant_id")
            card = payload.get("card_id")
            if card is not None and (
                item_kind != "token"
                or not await connection.scalar(
                    text(
                        "select id from app.cards where id=:card "
                        "and room_id=:room and campaign_id=:campaign and deleted_at is null"
                    ),
                    {"card": card, "room": command.room_id, "campaign": campaign_id},
                )
            ):
                raise SceneFailure("card_unavailable", "Карточка недоступна")
            if (
                card is not None
                and command.type == "item.create"
                and "visibility" not in command.payload
            ):
                linked = await load_card(connection, card, command.room_id)
                payload["visibility"] = linked.visibility
            if owner is not None and not await connection.scalar(
                text("""
                select id from app.participants where id=:owner and room_id=:room
                  and campaign_id=:campaign and removed_at is null
            """),
                {"owner": owner, "room": command.room_id, "campaign": campaign_id},
            ):
                raise SceneFailure("forbidden", "Участник недоступен")
            asset = payload.get("asset_id")
            if asset is not None and not await connection.scalar(
                text("""
                select id from app.assets
                where id=:asset and campaign_id=:campaign and status='ready'
            """),
                {"asset": asset, "campaign": campaign_id},
            ):
                raise SceneFailure("asset_unavailable", "Изображение недоступно")
            if command.type == "item.create" and payload["kind"] == "map" and asset is None:
                raise SceneFailure("asset_unavailable", "Выберите изображение карты")
            if scene["snap_enabled"]:
                for key in ("x", "y"):
                    if key in payload:
                        payload[key] = (
                            math.floor(payload[key] / scene["grid_size"] + 0.5) * scene["grid_size"]
                        )
                        if not -1000000 <= payload[key] <= 1000000:
                            raise SceneFailure("invalid_command", "Токен выходит за границы сцены")
            if command.type == "item.update":
                assert item_id is not None
                await self._update(connection, "scene_items", item_id, payload)
            else:
                values = CreateItem.model_validate(payload).model_dump()
                item_id = uuid4()
                values.update(
                    id=item_id,
                    scene_id=scene_id,
                    campaign_id=campaign_id,
                    created_by=actor.user_id,
                    created_by_participant_id=actor.id,
                )
                columns = ",".join(values)
                parameters = ",".join(f":{key}" for key in values)
                # Column names only come from the validated model and constants above.
                await connection.execute(
                    text(f"insert into app.scene_items({columns}) values({parameters})"), values
                )
        return scene_id, await self._event_payload(connection, scene_id, item_id)

    @staticmethod
    async def _event_payload(
        connection: AsyncConnection, scene_id: UUID, item_id: UUID | None = None
    ) -> dict[str, Any]:
        # Snapshot the saved values, not the client's pre-validation/pre-snap command.
        # This internal event must still pass through role projection before fan-out.
        if item_id is not None:
            item = (
                (
                    await connection.execute(
                        text("""
                    select id,kind,name,asset_id,x,y,width,height,rotation,z_index,visibility,
                           is_locked,owner_participant_id,card_id from app.scene_items
                    where id=:item and scene_id=:scene
                """),
                        {"item": item_id, "scene": scene_id},
                    )
                )
                .mappings()
                .one()
            )
            return {
                "scene_id": str(scene_id),
                "item": SceneItem.model_validate(dict(item)).model_dump(
                    mode="json", exclude={"can_transform"}
                ),
            }
        scene = (
            (
                await connection.execute(
                    text("""
                select id,name,width,height,grid_size,grid_enabled,snap_enabled,unit_size,unit_label
                from app.scenes where id=:scene
            """),
                    {"scene": scene_id},
                )
            )
            .mappings()
            .one()
        )
        return {
            "scene_id": str(scene_id),
            "scene": Scene.model_validate(dict(scene)).model_dump(mode="json"),
        }

    @staticmethod
    async def _update(
        connection: AsyncConnection,
        table: str,
        identifier: UUID,
        values: dict[str, Any],
    ) -> None:
        if not values:
            raise SceneFailure("invalid_command", "Нет изменений")
        assignments = ",".join(f"{key}=:{key}" for key in values)
        await connection.execute(
            # Table/columns are constants or fields of an extra-forbid validated model.
            text(f"update app.{table} set {assignments},version=version+1 where id=:id"),  # noqa: S608
            {**values, "id": identifier},
        )
