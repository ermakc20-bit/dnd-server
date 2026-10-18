import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.ability_geometry.models import ClearAbility, PresentAbility
from app.access.policy import Action, authorize
from app.cards.models import CardData, ChangeResource, DeleteCard, UpdateCard
from app.cards.repository import load_card
from app.cards.service import validate_references
from app.identity.models import Participant
from app.scene_tools.models import AnnotationData, Fog
from app.scenes.models import SceneFailure


class UndoTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_cursor: int = Field(ge=1)


async def latest_pending_event(
    connection: AsyncConnection, room: dict[str, Any], target_scene_id: UUID | None = None
) -> int | None:
    # Compensations consume forward actions. A live newer shared-scene action
    # blocks an older origin action as it did in the version-only contract.
    cursor = await connection.scalar(
        text("""
        select e.id from app.room_events e join app.rooms origin on origin.id=e.room_id
        where e.event_type<>'action.undo' and
        (e.room_id=:room or (origin.campaign_id=:campaign and
          (((e.scene_id=:scene or e.scene_id=:target) and e.event_type not like 'card.%'
            and e.event_type not in ('dice.roll','scene.activate','campaign.history'))
           or e.event_type in ('scene.create','scene.rename'))))
        and not exists(select 1 from app.room_events compensation
                       where compensation.event_type='action.undo'
                       and compensation.payload->>'undo_of'=e.id::text)
        order by e.id desc limit 1
    """),
        {
            "room": room["id"],
            "campaign": room["campaign_id"],
            "scene": room["active_scene_id"],
            "target": target_scene_id,
        },
    )
    return int(cursor) if cursor is not None else None


async def compensated_version(
    connection: AsyncConnection, cursor: int, identifier: str, expected: int, kind: str
) -> int:
    # Count real, immutable later writes. An unexplained version bump still
    # rejects; choosing a prior event never waives an object's stale guard.
    count = await connection.scalar(
        text("""
        select count(*) from app.room_events e where e.id>:cursor and
        ((:kind='item' and e.payload->'item'->>'id'=:id)
         or (:kind='card' and (e.payload->>'card_id'=:id or
             (e.event_type='action.undo' and e.payload->>'undo_type'='import.confirm'
              and e.payload->'card_ids' ? :id)))
         or (:kind='scene' and e.scene_id=cast(:id as uuid) and
              coalesce(e.payload->>'undo_type',e.event_type) in
              ('scene.rename','scene.grid','fog.fill','fog.reset','fog.reveal')))
    """),
        {"cursor": cursor, "id": identifier, "kind": kind},
    )
    return expected + int(count or 0)


async def capture_inverse(
    connection: AsyncConnection,
    kind: str,
    payload: dict[str, Any],
    room: dict[str, Any],
    actor: Participant,
) -> dict[str, Any] | None:
    if kind in {"card.create", "card.clone", "item.duplicate"}:
        return {"kind": "card" if kind.startswith("card.") else "item", "state": None}
    if kind == "item.create":
        return {"kind": "item", "state": None}
    if kind in {"scene.create", "scene.activate"}:
        return {
            "kind": "scene_lifecycle",
            "state": {
                "previous_active_scene_id": str(room["active_scene_id"])
                if room["active_scene_id"]
                else None
            },
        }
    if kind == "dice.roll":
        return {"kind": "dice", "state": None}
    if kind == "import.confirm":
        return {"kind": "import", "state": None}
    if kind in {"card.update", "card.resource", "card.delete"}:
        if (
            kind != "card.resource"
            and not authorize(actor, Action.MANAGE_CARD, actor.room_id).allowed
        ):
            raise SceneFailure("forbidden", "Структуру карточки меняет мастер")
        card_models: dict[str, type[UpdateCard | ChangeResource | DeleteCard]] = {
            "card.update": UpdateCard,
            "card.resource": ChangeResource,
            "card.delete": DeleteCard,
        }
        request = card_models[kind].model_validate(payload)
        card = await load_card(connection, request.card_id, actor.room_id)
        return {
            "kind": "card",
            "id": str(card.id),
            "scene_id": None,
            "state": card.model_dump(mode="json"),
        }
    if kind in {"ability.present", "ability.clear"}:
        if kind == "ability.present":
            PresentAbility.model_validate(payload)
        else:
            ClearAbility.model_validate(payload)
        scene_id = room["active_scene_id"]
        row = (
            (
                await connection.execute(
                    text("""
            select * from app.ability_presentations where scene_id=:scene and
            ((:present and owner_participant_id=:actor) or id=:id)
        """),
                    {
                        "scene": scene_id,
                        "present": kind == "ability.present",
                        "actor": actor.id,
                        "id": UUID(str(payload["presentation_id"]))
                        if kind == "ability.clear"
                        else None,
                    },
                )
            )
            .mappings()
            .first()
        )
        saved = None
        if row:
            saved = {**dict(row), "created_at": row["created_at"].isoformat()}
            saved = {
                key: str(value) if isinstance(value, UUID) else value
                for key, value in saved.items()
            }
            source = await connection.scalar(
                text("""
                select payload from app.room_events where event_type='ability.present'
                and scene_id=:scene and payload->>'presentation_id'=:id order by id desc limit 1
            """),
                {"scene": scene_id, "id": str(row["id"])},
            )
            saved["source"] = (source or {}).get("source")
        return {
            "kind": "presentation",
            "owner_participant_id": str(
                row["owner_participant_id"] if row is not None else actor.id
            ),
            "scene_id": str(scene_id) if scene_id else None,
            "state": saved,
        }
    if kind not in {"item.update", "item.delete", "scene.rename", "scene.grid"}:
        return None
    scene_id = payload.get("scene_id", room["active_scene_id"])
    if kind in {"item.update", "item.delete"}:
        row = (
            (
                await connection.execute(
                    text(
                        """
select
id,kind,name,asset_id,x,y,width,height,rotation,z_index,visibility,is_locked,owner_participant_id,card_id
from app.scene_items where id=:id and scene_id=:scene and deleted_at is null
"""
                    ),
                    {"id": payload.get("item_id"), "scene": scene_id},
                )
            )
            .mappings()
            .first()
        )
    else:
        row = (
            (
                await connection.execute(
                    text(
                        """
select id,name,width,height,grid_size,grid_enabled,snap_enabled,unit_size,unit_label
from app.scenes where id=:scene and campaign_id=:campaign and deleted_at is null
"""
                    ),
                    {"scene": scene_id, "campaign": room["campaign_id"]},
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        return None
    saved = {key: str(value) if isinstance(value, UUID) else value for key, value in row.items()}
    return {
        "kind": "item" if kind in {"item.update", "item.delete"} else "scene",
        "scene_id": str(scene_id),
        "id": saved["id"],
        "state": saved,
    }


async def finish_inverse(
    connection: AsyncConnection,
    inverse: dict[str, Any] | None,
    kind: str,
    event: dict[str, Any],
    scene_id: UUID | None,
) -> dict[str, Any] | None:
    if inverse is None:
        return None
    if inverse["kind"] in {"card", "item"}:
        identifier = event["card_id"] if inverse["kind"] == "card" else event["item"]["id"]
        inverse["id"] = identifier
        inverse["scene_id"] = str(scene_id) if scene_id else None
        table = "cards" if inverse["kind"] == "card" else "scene_items"
        inverse["expected_version"] = await connection.scalar(
            text(f"select version from app.{table} where id=:id"),  # noqa: S608 - fixed allowlist
            {"id": UUID(identifier)},
        )
        if kind == "item.duplicate" and event["item"].get("card_id"):
            inverse["created_card_id"] = event["item"]["card_id"]
            inverse["created_card_version"] = await connection.scalar(
                text("select version from app.cards where id=:id"),
                {"id": UUID(inverse["created_card_id"])},
            )
    elif inverse["kind"] == "scene_lifecycle":
        inverse["id"] = str(scene_id)
        inverse["scene_id"] = str(scene_id)
        inverse["expected_version"] = await connection.scalar(
            text("select version from app.scenes where id=:id"), {"id": scene_id}
        )
    elif inverse["kind"] == "dice":
        inverse["id"] = event["roll"]["id"]
    elif inverse["kind"] == "import":
        inverse["scene_id"] = str(scene_id) if scene_id else None
        inverse["cards"] = [
            {"id": card["id"], "version": card["version"]} for card in event["cards"]
        ]
        inverse["items"] = []
        for item in event["items"]:
            version = await connection.scalar(
                text("select version from app.scene_items where id=:id"), {"id": UUID(item["id"])}
            )
            inverse["items"].append({"id": item["id"], "version": version})
    elif inverse["kind"] == "presentation":
        inverse["id"] = event["presentation_id"]
    return inverse


async def validate_item_references(
    connection: AsyncConnection,
    actor: Participant,
    state: dict[str, Any],
) -> None:
    # The inverse holds server-saved IDs, whose room ownership is immutable in
    # gameplay commands. A shared-scene GM can retain those original scopes.
    for key, sql, code in (
        (
            "owner_participant_id",
            "select p.id from app.participants p join app.rooms r on r.id=p.room_id "
            "where p.id=:id and p.campaign_id=:campaign "
            "and p.removed_at is null and not r.is_archived",
            "forbidden",
        ),
        (
            "asset_id",
            "select id from app.assets where id=:id and campaign_id=:campaign and status='ready'",
            "asset_unavailable",
        ),
        (
            "card_id",
            "select c.id from app.cards c join app.rooms r on r.id=c.room_id "
            "where c.id=:id and c.campaign_id=:campaign "
            "and c.deleted_at is null and not r.is_archived",
            "card_unavailable",
        ),
    ):
        if state.get(key) and not await connection.scalar(
            text(sql),
            {"id": UUID(state[key]), "campaign": actor.campaign_id},
        ):
            raise SceneFailure(code, "Ссылка для восстановления недоступна")


async def apply_undo(
    connection: AsyncConnection, actor: Participant, payload: dict[str, Any], room: dict[str, Any]
) -> tuple[UUID | None, dict[str, Any]]:
    if not authorize(actor, Action.MANAGE_SCENE, actor.room_id).allowed:
        raise SceneFailure("forbidden", "Отмена доступна мастеру")
    target = UndoTarget.model_validate(payload)
    if target.event_cursor != await latest_pending_event(connection, {**room, "id": actor.room_id}):
        raise SceneFailure(
            "not_reversible", "Можно отменить только последнее неотменённое действие"
        )
    event = (
        (
            await connection.execute(
                text(
                    """
select id,scene_id,event_type,payload,undo_state from app.room_events where
room_id=:room and id=:id
"""
                ),
                {
                    "room": actor.room_id,
                    "version": room["scene_version"],
                    "id": target.event_cursor,
                },
            )
        )
        .mappings()
        .first()
    )
    if event is None:
        raise SceneFailure("not_reversible", "Можно отменить только последнее обратимое действие")
    inverse = event["undo_state"]
    if inverse is None:
        raise SceneFailure("not_reversible", "Это действие необратимо")
    scene_id = UUID(inverse["scene_id"]) if inverse.get("scene_id") else None
    if (
        inverse["kind"] not in {"card", "scene_lifecycle", "dice", "import"}
        and event["event_type"] != "scene.rename"
        and scene_id != room["active_scene_id"]
    ):
        raise SceneFailure("not_reversible", "Сначала откройте сцену действия")
    if event["event_type"] == "scene.rename":
        if not await connection.scalar(
            text(
                "select id from app.scenes where id=:scene and campaign_id=:campaign "
                "and deleted_at is null for update"
            ),
            {"scene": scene_id, "campaign": actor.campaign_id},
        ):
            raise SceneFailure("scene_unavailable", "Сцена для восстановления недоступна")
        # Inactive rename still targets that scene. A newer live command from a
        # room displaying it must block restoration of the saved scene fields.
        if target.event_cursor != await latest_pending_event(
            connection, {**room, "id": actor.room_id}, scene_id
        ):
            raise SceneFailure("not_reversible", "Есть более новое действие этой сцены")
    state = inverse["state"]
    result = {
        "scene_id": str(scene_id) if scene_id else None,
        "undo_of": event["id"],
        "undo_type": event["event_type"],
        "visibility": "everyone",
    }
    if inverse["kind"] in {"card", "item"}:
        table = "cards" if inverse["kind"] == "card" else "scene_items"
        current = (
            (
                await connection.execute(
                    text(f"select version,deleted_at from app.{table} where id=:id for update"),  # noqa: S608 - fixed allowlist
                    {"id": UUID(inverse["id"])},
                )
            )
            .mappings()
            .first()
        )
        expected = await compensated_version(
            connection, event["id"], inverse["id"], inverse["expected_version"], inverse["kind"]
        )
        if current is None or current["version"] != expected:
            raise SceneFailure("stale_version", "Объект изменился после действия")
    if inverse["kind"] == "scene_lifecycle":
        identifier = UUID(inverse["id"])
        if room["active_scene_id"] != identifier:
            raise SceneFailure("stale_version", "Активная сцена изменилась")
        prior = state["previous_active_scene_id"]
        previous = UUID(prior) if prior else None
        if previous is not None and not await connection.scalar(
            text(
                "select id from app.scenes where id=:id and campaign_id=:campaign "
                "and deleted_at is null"
            ),
            {"id": previous, "campaign": actor.campaign_id},
        ):
            raise SceneFailure("scene_unavailable", "Предыдущая сцена недоступна")
        if event["event_type"] == "scene.create":
            current = await connection.scalar(
                text(
                    "select version from app.scenes where id=:id and deleted_at is null for update"
                ),
                {"id": identifier},
            )
            expected = await compensated_version(
                connection, event["id"], inverse["id"], inverse["expected_version"], "scene"
            )
            if current != expected:
                raise SceneFailure("stale_version", "Сцена изменилась после создания")
            in_use = await connection.scalar(
                text("""
                select exists(select 1 from app.rooms where active_scene_id=:id and id<>:room)
                or exists(select 1 from app.scene_items where scene_id=:id and deleted_at is null)
                or exists(select 1 from app.scene_annotations
                          where scene_id=:id and deleted_at is null)
                or exists(select 1 from app.ability_presentations where scene_id=:id)
                or exists(select 1 from app.room_events where scene_id=:id and id>:cursor
                          and event_type not in ('dice.roll','scene.activate','action.undo')
                          and not exists(select 1 from app.room_events compensation
                              where compensation.event_type='action.undo'
                              and compensation.payload->>'undo_of'=app.room_events.id::text))

            """),
                {"id": identifier, "room": actor.room_id, "cursor": event["id"]},
            )
            if in_use:
                raise SceneFailure("scene_in_use", "Созданная сцена уже используется")
        await connection.execute(
            text("update app.rooms set active_scene_id=:previous where id=:room"),
            {"previous": previous, "room": actor.room_id},
        )
        if event["event_type"] == "scene.create":
            await connection.execute(
                text("update app.scenes set deleted_at=now(),version=version+1 where id=:id"),
                {"id": identifier},
            )
            result["removed_scene_id"] = str(identifier)
        result["scene_id"] = str(previous) if previous else None
        return previous, result
    if inverse["kind"] == "dice":
        # The roll and its original event remain immutable; this is only a revocation.
        result.update(roll_id=inverse["id"], visibility=event["payload"]["roll"]["visibility"])
    elif inverse["kind"] == "import":
        if inverse["items"] and scene_id != room["active_scene_id"]:
            raise SceneFailure("not_reversible", "Сначала откройте сцену импорта")
        for table, entries in (("scene_items", inverse["items"]), ("cards", inverse["cards"])):
            for entry in entries:
                current = (
                    (
                        await connection.execute(
                            text(
                                f"select version,deleted_at from app.{table} "  # noqa: S608 - fixed allowlist
                                "where id=:id for update"
                            ),
                            {"id": UUID(entry["id"])},
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    current is None
                    or current["deleted_at"] is not None
                    or current["version"]
                    != await compensated_version(
                        connection,
                        event["id"],
                        entry["id"],
                        entry["version"],
                        "item" if table == "scene_items" else "card",
                    )
                ):
                    raise SceneFailure("stale_version", "Объект импорта изменился")
        item_ids = [UUID(entry["id"]) for entry in inverse["items"]]
        card_ids = [UUID(entry["id"]) for entry in inverse["cards"]]
        if await connection.scalar(
            text(
                "select id from app.scene_items where card_id=any(cast(:cards as uuid[])) "
                "and deleted_at is null and not(id=any(cast(:items as uuid[]))) limit 1"
            ),
            {"cards": card_ids, "items": item_ids},
        ):
            raise SceneFailure("card_in_use", "Карточка импорта используется другим токеном")
        await connection.execute(
            text(
                "update app.scene_items set deleted_at=now(),version=version+1 "
                "where id=any(cast(:ids as uuid[]))"
            ),
            {"ids": item_ids},
        )
        await connection.execute(
            text(
                "update app.cards set deleted_at=now(),version=version+1 "
                "where id=any(cast(:ids as uuid[]))"
            ),
            {"ids": card_ids},
        )
        result.update(
            card_ids=event["payload"]["card_ids"],
            cards=event["payload"]["cards"],
            deleted=True,
            visibility="gm_only",
        )
    elif inverse["kind"] == "card":
        identifier = UUID(inverse["id"])
        if state is None:
            if await connection.scalar(
                text(
                    "select id from app.scene_items where card_id=:id and "
                    "deleted_at is null limit 1"
                ),
                {"id": identifier},
            ):
                raise SceneFailure("card_in_use", "Сначала удалите все токены этой карточки")
            await connection.execute(
                text(
                    "update app.cards set "
                    "deleted_at=now(),version=version+1,updated_at=now() "
                    "where id=:id and room_id=:room"
                ),
                {"id": identifier, "room": actor.room_id},
            )
            deleted_card = await load_card(
                connection, identifier, actor.room_id, include_deleted=True
            )
            result.update(
                card_id=str(identifier), card=deleted_card.model_dump(mode="json"), deleted=True
            )
        else:
            card_data = CardData.model_validate({key: state[key] for key in CardData.model_fields})
            await validate_references(connection, card_data, actor)
            await connection.execute(
                text("""
                update app.cards set data=cast(:data as jsonb),owner_participant_id=:owner,
                image_asset_id=:image,deleted_at=null,version=version+1,updated_at=now()
                where id=:id and room_id=:room
            """),
                {
                    "data": card_data.model_dump_json(),
                    "owner": card_data.owner_participant_id,
                    "image": card_data.image_asset_id,
                    "id": identifier,
                    "room": actor.room_id,
                },
            )
            restored = await load_card(connection, identifier, actor.room_id)
            result.update(card_id=str(identifier), card=restored.model_dump(mode="json"))
        result["visibility"] = result["card"]["visibility"]
    elif inverse["kind"] == "presentation":
        current_presentation = (
            (
                await connection.execute(
                    text(
                        "select id,geometry from app.ability_presentations where scene_id=:scene "
                        "and owner_participant_id=:owner for update"
                    ),
                    {"scene": scene_id, "owner": UUID(inverse["owner_participant_id"])},
                )
            )
            .mappings()
            .first()
        )
        if event["event_type"] == "ability.present":
            if (
                current_presentation is None
                or str(current_presentation["id"]) != inverse["id"]
                or current_presentation["geometry"] != event["payload"]["geometry"]
            ):
                raise SceneFailure("stale_version", "Область изменилась после действия")
        elif current_presentation is not None:
            raise SceneFailure("stale_version", "Область изменилась после действия")
        if state is not None:
            owner = UUID(state["owner_participant_id"])
            if not await connection.scalar(
                text(
                    "select id from app.participants where id=:id and "
                    "campaign_id=:campaign and removed_at is null"
                ),
                {"id": owner, "campaign": actor.campaign_id},
            ):
                raise SceneFailure("forbidden", "Владелец области недоступен")
            source = state.get("source")
            if source:
                card = await load_card(connection, UUID(source["card_id"]), UUID(source["room_id"]))
                if not any(str(ability.id) == source["ability_id"] for ability in card.abilities):
                    raise SceneFailure(
                        "card_unavailable", "Способность для восстановления недоступна"
                    )
                if source.get("origin_item_id") and not await connection.scalar(
                    text(
                        "select id from app.scene_items where id=:id and "
                        "scene_id=:scene and card_id=:card and deleted_at is null"
                    ),
                    {"id": UUID(source["origin_item_id"]), "scene": scene_id, "card": card.id},
                ):
                    raise SceneFailure("item_unavailable", "Источник области недоступен")
        # Replacement and clear restore the same prior identity and geometry.
        await connection.execute(
            text("delete from app.ability_presentations where id=:id and scene_id=:scene"),
            {"id": UUID(inverse["id"]), "scene": scene_id},
        )
        if state is not None:
            await connection.execute(
                text("""
                insert into
app.ability_presentations(id,scene_id,campaign_id,owner_participant_id,geometry,created_at)
                values(:id,:scene,:campaign,:owner,cast(:geometry as jsonb),cast(:created
as timestamptz))
            """),
                {
                    "id": UUID(state["id"]),
                    "scene": scene_id,
                    "campaign": actor.campaign_id,
                    "owner": UUID(state["owner_participant_id"]),
                    "geometry": json.dumps(state["geometry"]),
                    "created": datetime.fromisoformat(state["created_at"]),
                },
            )
        result["presentation_id"] = inverse["id"]
    elif inverse["kind"] == "fog":
        fog = Fog.model_validate(state)
        await connection.execute(
            text(
                """
update app.scenes set fog=cast(:fog as jsonb),version=version+1 where id=:scene and
campaign_id=:campaign
"""
            ),
            {"fog": fog.model_dump_json(), "scene": scene_id, "campaign": room["campaign_id"]},
        )
        result["fog"] = fog.model_dump(mode="json")
    elif inverse["kind"] == "annotation":
        identifier = UUID(inverse["id"])
        if state is None:
            await connection.execute(
                text(
                    """update app.scene_annotations set deleted_at=now()
                    where id=:id and scene_id=:scene"""
                ),
                {"id": identifier, "scene": scene_id},
            )
            result["annotation"] = {**event["payload"]["annotation"], "deleted": True}
        else:
            data = AnnotationData.model_validate(
                {key: state[key] for key in AnnotationData.model_fields}
            )
            await connection.execute(
                text(
                    """
update app.scene_annotations set kind=:kind,points=cast(:points as
jsonb),label=:label,visibility=:visibility,deleted_at=null where id=:id and
scene_id=:scene
"""
                ),
                {
                    "id": identifier,
                    "scene": scene_id,
                    "kind": data.kind,
                    "points": json.dumps(data.model_dump(mode="json")["points"]),
                    "label": data.label,
                    "visibility": data.visibility,
                },
            )
            result["annotation"] = {**state, "deleted": False}
        result["visibility"] = result["annotation"]["visibility"]
    elif inverse["kind"] == "item":
        identifier = UUID(inverse["id"])
        if state is None:
            await connection.execute(
                text(
                    "update app.scene_items set "
                    "deleted_at=now(),version=version+1,updated_at=now() "
                    "where id=:id and scene_id=:scene"
                ),
                {"id": identifier, "scene": scene_id},
            )
            if inverse.get("created_card_id"):
                card_id = UUID(inverse["created_card_id"])
                if await connection.scalar(
                    text(
                        "select id from app.scene_items where card_id=:id and "
                        "deleted_at is null limit 1"
                    ),
                    {"id": card_id},
                ):
                    raise SceneFailure("card_in_use", "Карточка копии используется другим токеном")
                version = await connection.scalar(
                    text("select version from app.cards where id=:id"), {"id": card_id}
                )
                if version != await compensated_version(
                    connection, event["id"], str(card_id), inverse["created_card_version"], "card"
                ):
                    raise SceneFailure("stale_version", "Карточка копии изменилась")
                await connection.execute(
                    text(
                        "update app.cards set "
                        "deleted_at=now(),version=version+1,updated_at=now() where id=:id"
                    ),
                    {"id": card_id},
                )
            result["item"] = event["payload"]["item"]
            result["deleted"] = True
            result["visibility"] = result["item"]["visibility"]
            return scene_id, result
        await validate_item_references(connection, actor, state)
        values = {
            key: state[key]
            for key in (
                "name",
                "asset_id",
                "x",
                "y",
                "width",
                "height",
                "rotation",
                "z_index",
                "visibility",
                "is_locked",
                "owner_participant_id",
                "card_id",
            )
        }
        for key in ("asset_id", "owner_participant_id", "card_id"):
            values[key] = UUID(values[key]) if values[key] else None
        await connection.execute(
            text(
                """
update app.scene_items set
name=:name,asset_id=:asset_id,x=:x,y=:y,width=:width,height=:height,
rotation=:rotation,z_index=:z_index,visibility=:visibility,is_locked=:is_locked,
owner_participant_id=:owner_participant_id,card_id=:card_id,deleted_at=null,
version=version+1,updated_at=now()
where id=:id and scene_id=:scene
"""
            ),
            {**values, "id": identifier, "scene": scene_id},
        )
        result["item"] = state
        result["visibility"] = state["visibility"]
    elif inverse["kind"] == "scene":
        await connection.execute(
            text(
                """
update app.scenes set
name=:name,grid_size=:grid_size,grid_enabled=:grid_enabled,snap_enabled=:snap_enabled,
unit_size=:unit_size,unit_label=:unit_label,version=version+1,updated_at=now()
where id=:id and campaign_id=:campaign
"""
            ),
            {**state, "id": scene_id, "campaign": room["campaign_id"]},
        )
        result["scene"] = state
    return scene_id, result
