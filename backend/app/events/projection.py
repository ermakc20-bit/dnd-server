from typing import Any

from sqlalchemy import text

from app.access.database import participant_is_active
from app.dice_log.journal import event_visible
from app.identity.models import Participant
from app.scenes.models import SceneFailure
from app.scenes.repository import SceneRepository


async def synchronize(
    repository: SceneRepository, actor: Participant, cursor: int
) -> dict[str, Any]:
    # Reuse the authority's visibility rules and ensure the snapshot remains current.
    for _ in range(5):
        snapshot = await repository.get_projection(actor, actor.room_id)
        async with repository.engine.begin() as connection:
            version = await connection.scalar(
                text(
                    "select scene_version from app.rooms "
                    "where id=:room and not is_archived for share"
                ),
                {"room": actor.room_id},
            )
            if not await participant_is_active(connection, actor):
                raise SceneFailure("forbidden", "Доступ к комнате отозван")
            if version != snapshot.aggregate_version:
                continue
            rows = (
                (
                    await connection.execute(
                        text("""
                select e.id,e.room_id,e.aggregate_version,e.event_type,e.scene_id,
                       payload->>'card_id' as card_id,payload->'item'->>'id' as item_id,
                       payload->'card_ids' as card_ids,payload
                from app.room_events e join app.rooms origin on origin.id=e.room_id
                where e.id>:cursor and e.id<=:last and (e.room_id=:room or
                  (origin.campaign_id=:campaign and
                   ((e.scene_id=:scene and e.event_type not like 'card.%'
                      and not (e.event_type='action.undo' and (e.payload ? 'card' or
                           coalesce(e.payload->>'undo_type','') in
                           ('dice.roll','scene.activate'))) and
                     e.event_type not in ('dice.roll','scene.activate','campaign.history'))
                    or (:gm and (e.event_type in ('scene.create','scene.rename') or
                      (e.event_type='action.undo' and e.payload->>'undo_type'='scene.create'))))))
                order by e.id limit 1001
            """),
                        {
                            "room": actor.room_id,
                            "cursor": cursor,
                            "last": snapshot.event_cursor,
                            "campaign": actor.campaign_id,
                            "scene": snapshot.scene.id if snapshot.scene else None,
                            "gm": snapshot.can_manage,
                        },
                    )
                )
                .mappings()
                .all()
            )
            cards = set(
                (
                    await connection.scalars(
                        text("""
                select id::text from app.cards where room_id=:room and deleted_at is null and
                (:gm or data->>'visibility'='everyone' or
                (data->>'visibility'='owner_only' and owner_participant_id=:actor))
            """),
                        {"room": actor.room_id, "gm": snapshot.can_manage, "actor": actor.id},
                    )
                ).all()
            )
            events = []
            for row in rows[:1000]:
                shared = row["room_id"] != actor.room_id
                batch_import = (
                    row["event_type"] == "import.confirm"
                    or row["payload"].get("undo_type") == "import.confirm"
                )
                card_event = (
                    row["event_type"].startswith("card.")
                    or batch_import
                    or "card" in row["payload"]
                )
                visible = event_visible(
                    row, snapshot, cards, {str(mark.id) for mark in snapshot.annotations}, actor.id
                )
                if visible:
                    events.append(
                        {
                            "cursor": row["id"],
                            "aggregate_version": snapshot.aggregate_version
                            if shared
                            else row["aggregate_version"],
                            "type": "scene.changed"
                            if shared
                            else "cards.changed"
                            if card_event
                            else "journal.changed"
                            if row["event_type"] == "dice.roll"
                            or row["payload"].get("undo_type") == "dice.roll"
                            else "scene.changed",
                        }
                    )
            return {
                "type": "sync",
                "snapshot": snapshot.model_dump(mode="json"),
                "events": events,
                "events_compacted": len(rows) > 1000,
            }
    raise SceneFailure("resync_busy", "Сцена обновляется. Повторяем синхронизацию", 503)
