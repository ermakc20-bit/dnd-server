from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.access.database import participant_is_active
from app.dice_log.models import RollEvent
from app.identity.models import Participant
from app.scene_tools.undo import latest_pending_event
from app.scenes.models import SceneFailure, SceneProjection
from app.scenes.repository import SceneRepository

LABELS = {
    "scene.create": "Создана сцена",
    "scene.rename": "Изменено название сцены",
    "scene.activate": "Сменена сцена",
    "scene.grid": "Изменена сетка",
    "item.create": "Создан объект",
    "item.update": "Изменён объект",
    "item.duplicate": "Создана копия объекта",
    "item.delete": "Объект удалён в корзину",
    "fog.fill": "Сцена закрыта туманом",
    "fog.reset": "Туман снят",
    "fog.reveal": "Открыта область тумана",
    "annotation.create": "Создана метка",
    "annotation.update": "Изменена метка",
    "annotation.delete": "Метка удалена в корзину",
    "dice.roll": "Бросок кубов",
    "action.undo": "Действие отменено",
    "card.create": "Создана карточка",
    "card.update": "Изменена карточка",
    "card.clone": "Создана копия карточки",
    "card.delete": "Карточка удалена в корзину",
    "card.resource": "Изменён ресурс",  # noqa: RUF001 - Russian UI label
    "import.confirm": "Подтверждён импорт",
    "ability.present": "Показана область способности",
    "ability.clear": "Область способности убрана",
}
REVERSIBLE = {
    "fog.fill",
    "fog.reset",
    "fog.reveal",
    "annotation.create",
    "annotation.update",
    "annotation.delete",
    "item.update",
    "scene.grid",
    "scene.rename",
}


def event_visible(
    row: Any,
    snapshot: SceneProjection,
    card_ids: set[str],
    annotation_ids: set[str],
    actor_id: UUID,
) -> bool:
    if snapshot.can_manage:
        return True
    payload = row["payload"]
    kind = row["event_type"]
    if kind == "campaign.history":
        history = payload.get("history", {})
        visibility = history.get("visibility")
        return bool(
            visibility == "everyone"
            or (visibility == "owner_only" and history.get("owner_participant_id") == str(actor_id))
        )
    if kind == "action.undo" and payload.get("undo_type") == "dice.roll":
        return bool(payload.get("visibility") == "everyone")
    if kind == "action.undo" and payload.get("undo_type") == "import.confirm":
        return any(
            card.get("visibility") == "everyone"
            or (
                card.get("visibility") == "owner_only"
                and card.get("owner_participant_id") == str(actor_id)
            )
            for card in payload.get("cards", [])
        )
    if kind == "dice.roll":
        return bool(payload.get("roll", {}).get("visibility") == "everyone")
    if kind.startswith("card.") or "card" in payload:
        card = payload.get("card", {})
        return payload.get("card_id") in card_ids and (
            card.get("visibility") == "everyone"
            or (
                card.get("visibility") == "owner_only"
                and card.get("owner_participant_id") == str(actor_id)
            )
        )
    if kind == "import.confirm":
        return bool(set(payload.get("card_ids", [])) & card_ids)
    if row["scene_id"] not in {scene.id for scene in snapshot.scenes}:
        return False
    if "item" in payload:
        item = payload["item"]
        return (
            item.get("id") in {str(item.id) for item in snapshot.items}
            and item.get("visibility") != "gm_only"
            and (
                item.get("visibility") != "owner_only"
                or item.get("owner_participant_id") == str(actor_id)
            )
        )
    if "annotation" in payload:
        annotation = payload["annotation"]
        return annotation.get("visibility") == "everyone" and annotation.get("id") in annotation_ids
    if kind == "action.undo":
        return bool(payload.get("visibility") == "everyone")
    return kind in LABELS


async def get_journal(
    repository: SceneRepository, actor: Participant, room_id: UUID, before_cursor: int, limit: int
) -> dict[str, Any]:
    snapshot = await repository.get_projection(actor, room_id)
    async with repository.engine.begin() as connection:
        version = await connection.scalar(
            text(
                "select scene_version from app.rooms where id=:room and not is_archived for share"
            ),
            {"room": room_id},
        )
        if version != snapshot.aggregate_version:
            raise SceneFailure("resync_busy", "Журнал обновляется. Повторите загрузку", 503)
        if not await participant_is_active(connection, actor):
            raise SceneFailure("forbidden", "Доступ к комнате отозван")
        cards = set(
            (
                await connection.scalars(
                    text(
                        """
select id::text from app.cards where room_id=:room and deleted_at is null and (:gm or
data->>'visibility'='everyone' or (data->>'visibility'='owner_only' and
owner_participant_id=:actor))
"""
                    ),
                    {"room": room_id, "gm": snapshot.can_manage, "actor": actor.id},
                )
            ).all()
        )
        # Tombstones permit a safe delete summary, but never restore hidden geometry to the DTO.
        annotations = (
            set(
                (
                    await connection.scalars(
                        text(
                            """select id::text from app.scene_annotations
                        where scene_id=:scene and visibility='everyone'"""
                        ),
                        {"scene": snapshot.scene.id if snapshot.scene else None},
                    )
                ).all()
            )
            if not snapshot.fog.enabled
            else {str(mark.id) for mark in snapshot.annotations}
        )
        rows = (
            (
                await connection.execute(
                    text(
                        """
select
e.id,e.event_id,e.scene_id,e.aggregate_version,e.event_type,e.payload,e.undo_state,e.created_at,p.display_name,
exists(select 1 from app.room_events compensation where compensation.room_id=e.room_id
       and compensation.event_type='action.undo' and compensation.payload->>'undo_type'='dice.roll'
       and compensation.payload->>'undo_of'=e.id::text) as revoked
from app.room_events e join app.participants p on p.id=e.actor_participant_id where
e.room_id=:room and e.id<=:last and (:before=0 or e.id<:before) order by e.id desc
limit 1001
"""
                    ),
                    {"room": room_id, "last": snapshot.event_cursor, "before": before_cursor},
                )
            )
            .mappings()
            .all()
        )
        pending_cursor = await latest_pending_event(
            connection,
            {
                "id": room_id,
                "campaign_id": actor.campaign_id,
                "active_scene_id": snapshot.scene.id if snapshot.scene else None,
            },
        )
        entries = []
        scanned = 0
        for row in rows[:1000]:
            scanned = row["id"]
            if not event_visible(row, snapshot, cards, annotations, actor.id):
                continue
            history = (
                row["payload"].get("history") if row["event_type"] == "campaign.history" else None
            )
            roll_event = (
                RollEvent.model_validate(row["payload"]["roll"]).model_dump(mode="json")
                if row["event_type"] == "dice.roll"
                else None
            )
            if history and history.get("roll"):
                roll_event = RollEvent.model_validate(
                    {
                        **history["roll"],
                        "id": row["event_id"],
                        "visibility": history["visibility"],
                        "created_at": row["created_at"],
                    }
                ).model_dump(mode="json")
            visibility = (
                roll_event["visibility"]
                if roll_event
                else row["payload"]
                .get("annotation", row["payload"].get("item", row["payload"].get("card", {})))
                .get("visibility", "everyone")
            )
            if (
                row["event_type"] == "action.undo"
                and row["payload"].get("undo_type") == "dice.roll"
            ):
                visibility = row["payload"]["visibility"]
            if history:
                visibility = history["visibility"]
            can_undo = (
                snapshot.can_manage
                and not history
                and row["id"] == pending_cursor
                and row["undo_state"] is not None
            )
            if can_undo and row["event_type"] == "scene.rename":
                can_undo = row["scene_id"] in {scene.id for scene in snapshot.scenes} and row[
                    "id"
                ] == await latest_pending_event(
                    connection,
                    {
                        "id": room_id,
                        "campaign_id": actor.campaign_id,
                        "active_scene_id": snapshot.scene.id if snapshot.scene else None,
                    },
                    row["scene_id"],
                )
            entries.append(
                {
                    "cursor": row["id"],
                    "aggregate_version": row["aggregate_version"],
                    "actor_name": row["display_name"],
                    "occurred_at": row["created_at"].isoformat(),
                    "action": history["action"]
                    if history
                    else LABELS.get(row["event_type"], "Изменение стола"),
                    "type": history["type"] if history else row["event_type"],
                    "result": "accepted",
                    "visibility": visibility,
                    "roll": roll_event,
                    "revoked": bool(
                        row["revoked"]
                        or (
                            history
                            and history.get("roll")
                            and "отменён мастером" in history["action"]
                        )
                    ),
                    "can_undo": can_undo,
                }
            )
            if len(entries) >= limit:
                break
        return {
            "entries": entries,
            "next_cursor": scanned if len(entries) == limit or len(rows) > 1000 else None,
        }
