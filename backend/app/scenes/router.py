from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.identity.dependencies import resolve_room_actor
from app.identity.models import Participant
from app.scenes.dependencies import get_scene_service
from app.scenes.models import Command, CommandResult, SceneFailure, SceneProjection
from app.scenes.service import SceneService

router = APIRouter(prefix="/api/v1/rooms/{room_id}/scene", tags=["scenes"])


@router.get("", response_model=SceneProjection)
async def get_projection(
    room_id: UUID,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[SceneService, Depends(get_scene_service)],
    cursor: Annotated[int, Query(ge=0)] = 0,
) -> SceneProjection:
    try:
        return await service.repository.get_projection(actor, room_id, cursor)
    except SceneFailure as error:
        raise HTTPException(
            status_code=error.status_code, detail={"code": error.code, "message": error.message}
        ) from error


@router.post("/commands", response_model=CommandResult)
async def execute_scene_command(
    room_id: UUID,
    command: Command,
    request: Request,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[SceneService, Depends(get_scene_service)],
) -> CommandResult:
    if command.room_id != room_id:
        return CommandResult(
            command_id=command.command_id,
            status="rejected",
            error_code="forbidden",
            message="Комната команды не совпадает",
        )
    result = await service.execute_scene_command(actor, command)
    realtime = getattr(request.app.state, "realtime", None)
    if realtime is not None and result.status == "accepted":
        for affected in await service.notification_rooms(actor):
            await realtime.notify(affected)
    return result
