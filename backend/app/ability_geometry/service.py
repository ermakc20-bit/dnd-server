from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.ability_geometry.geometry import includes
from app.ability_geometry.models import (
    AbilityPresentation,
    ClearAbility,
    PresentAbility,
    PresentedGeometry,
    WorldPoint,
)
from app.access.policy import Action, authorize
from app.cards.repository import card_access, load_card, project_card
from app.identity.models import Participant
from app.scene_tools.geometry import object_visible
from app.scene_tools.models import Fog

if TYPE_CHECKING:
    from app.scenes.models import SceneItem


async def apply_ability_command(
    connection: AsyncConnection,
    actor: Participant,
    kind: str,
    payload: dict[str, Any],
    room: dict[str, Any],
) -> tuple[UUID, dict[str, Any]]:
    from app.scenes.models import SceneFailure

    scene_id = room["active_scene_id"]
    scene = (
        (
            await connection.execute(
                text(
                    "select id,grid_size,unit_size,unit_label,fog from app.scenes "
                    "where id=:scene and campaign_id=:campaign and deleted_at is null for share"
                ),
                {"scene": scene_id, "campaign": actor.campaign_id},
            )
        )
        .mappings()
        .first()
    )
    if scene is None:
        raise SceneFailure("scene_unavailable", "Сцена недоступна")
    manages = authorize(actor, Action.MANAGE_CARD, actor.room_id).allowed
    if kind == "ability.clear":
        clear = ClearAbility.model_validate(payload)
        saved = (
            (
                await connection.execute(
                    text(
                        "select id,owner_participant_id from app.ability_presentations "
                        "where id=:id and scene_id=:scene for update"
                    ),
                    {"id": clear.presentation_id, "scene": scene_id},
                )
            )
            .mappings()
            .first()
        )
        if saved is None or (not manages and saved["owner_participant_id"] != actor.id):
            raise SceneFailure("forbidden", "Нет прав на эту область")
        await connection.execute(
            text("delete from app.ability_presentations where id=:id"),
            {"id": clear.presentation_id},
        )
        return scene_id, {"presentation_id": str(clear.presentation_id)}
    if kind != "ability.present":
        raise SceneFailure("invalid_command", "Неизвестная команда способности")
    request = PresentAbility.model_validate(payload)
    try:
        card = await load_card(connection, request.card_id, actor.room_id, lock=True)
    except SceneFailure:
        raise SceneFailure("forbidden", "Способность недоступна") from None
    if not authorize(
        actor, Action.PRESENT_ABILITY, actor.room_id, object_access=card_access(card)
    ).allowed:
        raise SceneFailure("forbidden", "Способность недоступна")
    ability = next(
        (a for a in project_card(card, actor).abilities if a.id == request.ability_id), None
    )
    if ability is None:
        raise SceneFailure("forbidden", "Способность недоступна")
    geometry = ability.geometry
    if geometry is None or geometry.units != scene["unit_label"]:
        raise SceneFailure("invalid_geometry", "Проверьте геометрию и единицы калибровки сцены")
    if geometry.shape in {"circle", "radius"}:
        valid = geometry.radius is not None and geometry.radius > 0
    else:
        valid = geometry.length is not None and geometry.length > 0
        if geometry.shape == "line":
            valid = valid and geometry.width is not None and geometry.width > 0
        if geometry.shape == "cone":
            valid = valid and geometry.angle is not None
    if not valid:
        raise SceneFailure("invalid_geometry", "Укажите положительные размеры области")
    if geometry.origin == "token":
        if request.origin is not None or request.origin_item_id is None:
            raise SceneFailure("invalid_geometry", "Выберите токен карточки как источник")
        token = (
            (
                await connection.execute(
                    text(
                        "select id,x,y,width,height,rotation from app.scene_items "
                        "where id=:item and scene_id=:scene and card_id=:card and "
                        "kind='token' and deleted_at is null "
                        "and (:gm or visibility='everyone' or "
                        "(visibility='owner_only' and owner_participant_id=:actor))"
                    ),
                    {
                        "item": request.origin_item_id,
                        "scene": scene_id,
                        "card": card.id,
                        "gm": manages,
                        "actor": actor.id,
                    },
                )
            )
            .mappings()
            .first()
        )
        if token is None or (
            not manages
            and not object_visible(
                Fog.model_validate(scene["fog"]),
                token["x"],
                token["y"],
                token["width"],
                token["height"],
                token["rotation"],
            )
        ):
            raise SceneFailure("forbidden", "Источник недоступен")
        origin = WorldPoint(x=token["x"] + token["width"] / 2, y=token["y"] + token["height"] / 2)
    else:
        if request.origin is None or request.origin_item_id is not None:
            raise SceneFailure("invalid_geometry", "Выберите точку как источник")
        origin = WorldPoint(x=request.origin.x, y=request.origin.y)
    rotation = 0.0
    if geometry.shape in {"line", "cone", "cube"}:
        if (
            request.direction is None
            or math.hypot(request.direction.x - origin.x, request.direction.y - origin.y) <= 1e-7
        ):
            raise SceneFailure("invalid_geometry", "Задайте направление области")
        rotation = math.atan2(request.direction.y - origin.y, request.direction.x - origin.x)
    scale = scene["grid_size"] / scene["unit_size"]
    placed = PresentedGeometry(
        shape=geometry.shape,
        origin=origin,
        rotation=rotation,
        radius=(geometry.radius or 0) * scale,
        length=(geometry.length or 0) * scale,
        width=(geometry.width or 0) * scale,
        angle=geometry.angle or 360,
        color=geometry.color or "#c5a65c",
    )
    presentation_id = uuid4()
    await connection.execute(
        text(
            "insert into app.ability_presentations"
            "(id,scene_id,campaign_id,owner_participant_id,geometry) "
            "values(:id,:scene,:campaign,:actor,cast(:geometry as jsonb)) "
            "on conflict(scene_id,owner_participant_id) do update "
            "set id=excluded.id,geometry=excluded.geometry,created_at=now()"
        ),
        {
            "id": presentation_id,
            "scene": scene_id,
            "campaign": actor.campaign_id,
            "actor": actor.id,
            "geometry": placed.model_dump_json(),
        },
    )
    return scene_id, {
        "presentation_id": str(presentation_id),
        "geometry": json.loads(placed.model_dump_json()),
        "source": {
            "card_id": str(card.id),
            "ability_id": str(ability.id),
            "room_id": str(actor.room_id),
            "origin_item_id": str(request.origin_item_id) if request.origin_item_id else None,
        },
    }


async def project_presentations(
    connection: AsyncConnection,
    actor: Participant,
    scene_id: UUID | None,
    items: list[SceneItem],
    manages: bool,
) -> list[AbilityPresentation]:
    rows = (
        (
            await connection.execute(
                text(
                    "select id,owner_participant_id,geometry,created_at "
                    "from app.ability_presentations "
                    "where scene_id=:scene order by created_at,id"
                ),
                {"scene": scene_id},
            )
        )
        .mappings()
        .all()
    )
    # Only caller-authorized projected tokens reach this workload. Hidden target count
    # never changes the geometry test count, affected IDs, or response structure.
    tokens = [item for item in items if item.kind == "token"]
    presentations = []
    for row in rows:
        geometry = PresentedGeometry.model_validate(row["geometry"])
        presentations.append(
            AbilityPresentation(
                id=row["id"],
                geometry=geometry,
                created_at=row["created_at"],
                can_clear=manages or row["owner_participant_id"] == actor.id,
                affected_item_ids=[
                    item.id
                    for item in tokens
                    if includes(geometry, item.x + item.width / 2, item.y + item.height / 2)
                ],
            )
        )
    return presentations
