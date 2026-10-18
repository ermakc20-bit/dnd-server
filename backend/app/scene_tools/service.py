import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.access.policy import Action, authorize
from app.identity.models import Participant
from app.scene_tools.models import Empty, Fog, Reveal
from app.scenes.models import SceneFailure


async def apply_tool_command(
    connection: AsyncConnection,
    actor: Participant,
    kind: str,
    payload: dict[str, Any],
    room: dict[str, Any],
) -> tuple[UUID, dict[str, Any], dict[str, Any] | None]:
    if not authorize(actor, Action.MANAGE_SCENE, actor.room_id).allowed:
        raise SceneFailure("forbidden", "Нет прав на изменение тумана")
    scene_id = room["active_scene_id"]
    scene = (
        (
            await connection.execute(
                text(
                    "select fog from app.scenes where id=:id and campaign_id=:campaign for update"
                ),
                {"id": scene_id, "campaign": room["campaign_id"]},
            )
        )
        .mappings()
        .first()
    )
    if scene is None:
        raise SceneFailure("scene_unavailable", "Сцена недоступна")
    before = Fog.model_validate(scene["fog"])
    if kind == "fog.reveal":
        reveal = Reveal.model_validate(payload)
        if not before.enabled:
            raise SceneFailure("invalid_command", "Сначала закройте сцену туманом")
        if len(before.reveals) >= 100:
            raise SceneFailure("invalid_command", "Достигнут лимит: 100 областей раскрытия")
        after = Fog(enabled=True, reveals=[*before.reveals, reveal])
    elif kind in {"fog.fill", "fog.reset"}:
        Empty.model_validate(payload)
        after = Fog(enabled=kind == "fog.fill")
    else:
        raise SceneFailure("invalid_command", "Неизвестный инструмент")
    await connection.execute(
        text("update app.scenes set fog=cast(:fog as jsonb),version=version+1 where id=:id"),
        {"id": scene_id, "fog": after.model_dump_json()},
    )
    return (
        scene_id,
        {"scene_id": str(scene_id), "fog": after.model_dump(mode="json")},
        {"kind": "fog", "scene_id": str(scene_id), "state": json.loads(before.model_dump_json())},
    )
