from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.ability_geometry.service import project_presentations
from app.access.database import participant_is_active
from app.access.policy import Action, ObjectAccess, authorize
from app.campaigns.repository import _async_database_url
from app.identity.models import Participant
from app.scene_tools.annotations import project_annotations
from app.scene_tools.geometry import object_visible
from app.scene_tools.models import Fog
from app.scenes.models import Scene, SceneFailure, SceneItem, SceneProjection, SceneSummary


class SceneRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_async_engine(_async_database_url(database_url), pool_pre_ping=True)

    async def get_projection(
        self,
        actor: Participant,
        room_id: UUID,
        cursor: int = 0,
    ) -> SceneProjection:
        async with self.engine.begin() as connection:
            if not authorize(
                actor, Action.VIEW_ROOM, room_id
            ).allowed or not await participant_is_active(connection, actor):
                raise SceneFailure("forbidden", "Нет доступа к сцене")
            room = (
                (
                    await connection.execute(
                        text("""
                select campaign_id, active_scene_id, scene_version from app.rooms
                where id=:room and not is_archived for share
            """),
                        {"room": room_id},
                    )
                )
                .mappings()
                .first()
            )
            if room is None:
                raise SceneFailure("scene_unavailable", "Сцена недоступна", 404)
            can_manage = authorize(actor, Action.MANAGE_SCENE, room_id).allowed
            scenes = (
                (
                    await connection.execute(
                        text("""
                select id,name from app.scenes where campaign_id=:campaign and deleted_at is null
                  and (:manage or id=:active) order by created_at,id
            """),
                        {
                            "campaign": room["campaign_id"],
                            "manage": can_manage,
                            "active": room["active_scene_id"],
                        },
                    )
                )
                .mappings()
                .all()
            )
            scene_row = (
                (
                    await connection.execute(
                        text("""
                select id,name,width,height,grid_size,grid_enabled,
                       snap_enabled,unit_size,unit_label,fog
                from app.scenes where id=:id and campaign_id=:campaign
                and deleted_at is null for share
            """),
                        {"id": room["active_scene_id"], "campaign": room["campaign_id"]},
                    )
                )
                .mappings()
                .first()
            )
            rows = (
                (
                    await connection.execute(
                        text("""
                select id,kind,name,asset_id,x,y,width,height,rotation,z_index,visibility,
                       is_locked,owner_participant_id,card_id from app.scene_items
                where scene_id=:scene and deleted_at is null and kind in ('map','token')
order by z_index,created_at,id
            """),
                        {"scene": room["active_scene_id"]},
                    )
                )
                .mappings()
                .all()
            )
            fog = Fog.model_validate(scene_row["fog"]) if scene_row else Fog()
            items: list[SceneItem] = []
            linked_ids = list({row["card_id"] for row in rows if row["card_id"] is not None})
            visible_ids: set[UUID] = set()
            if linked_ids:
                visible_ids = set(
                    (
                        await connection.scalars(
                            text("""
                    select id from app.cards where id=any(cast(:ids as uuid[]))
                    and deleted_at is null and room_id=:room and (:manage or
data->>'visibility'='everyone' or
                     (data->>'visibility'='owner_only' and owner_participant_id=:actor))
                """),
                            {
                                "ids": linked_ids,
                                "room": room_id,
                                "manage": can_manage,
                                "actor": actor.id,
                            },
                        )
                    ).all()
                )
            for saved_row in rows:
                row = dict(saved_row)
                if row["card_id"] not in visible_ids:
                    row["card_id"] = None
                access = ObjectAccess.model_validate(dict(row))
                if authorize(actor, Action.VIEW_ITEM, room_id, object_access=access).allowed and (
                    can_manage
                    or row["kind"] == "map"
                    or object_visible(
                        fog, row["x"], row["y"], row["width"], row["height"], row["rotation"]
                    )
                ):
                    items.append(
                        SceneItem.model_validate(
                            {
                                **row,
                                "can_transform": authorize(
                                    actor,
                                    Action.TRANSFORM_ITEM,
                                    room_id,
                                    object_access=access,
                                ).allowed,
                            }
                        )
                    )
            event_cursor = await connection.scalar(
                text("""select coalesce(max(e.id),0) from app.room_events e
                    join app.rooms origin on origin.id=e.room_id where
                    e.room_id=:room or (origin.campaign_id=:campaign and
                    ((e.scene_id=:scene and e.event_type not like 'card.%'
                      and not (e.event_type='action.undo' and (e.payload ? 'card' or
                           coalesce(e.payload->>'undo_type','') in ('dice.roll','scene.activate')))
                      and e.event_type not in ('dice.roll','scene.activate','campaign.history'))
                     or (:manage and (e.event_type in ('scene.create','scene.rename') or
                      (e.event_type='action.undo' and e.payload->>'undo_type'='scene.create')))))
                """),
                {
                    "room": room_id,
                    "campaign": room["campaign_id"],
                    "scene": room["active_scene_id"],
                    "manage": can_manage,
                },
            )
            return SceneProjection(
                room_id=room_id,
                aggregate_version=room["scene_version"],
                event_cursor=int(event_cursor or 0),
                actor_session_id=actor.guest_session_id or actor.id,
                can_manage=can_manage,
                scenes=[SceneSummary.model_validate(dict(row)) for row in scenes],
                scene=Scene.model_validate(dict(scene_row)) if scene_row else None,
                items=items,
                ability_presentations=await project_presentations(
                    connection, actor, room["active_scene_id"], items, can_manage
                ),
                fog=fog,
                annotations=await project_annotations(
                    connection, actor, room["active_scene_id"], fog, can_manage
                ),
            )
