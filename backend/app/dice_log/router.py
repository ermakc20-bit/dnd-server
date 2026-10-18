from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.dice_log.journal import get_journal
from app.dice_log.models import JournalPage
from app.identity.dependencies import resolve_room_actor
from app.identity.models import Participant
from app.scenes.dependencies import get_scene_service
from app.scenes.models import SceneFailure
from app.scenes.service import SceneService

router = APIRouter(prefix="/api/v1/rooms/{room_id}", tags=["journal"])


@router.get("/journal", response_model=JournalPage)
async def journal(
    room_id: UUID,
    response: Response,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[SceneService, Depends(get_scene_service)],
    before_cursor: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 30,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await get_journal(service.repository, actor, room_id, before_cursor, limit)
    except SceneFailure as error:
        raise HTTPException(
            status_code=error.status_code, detail={"code": error.code, "message": error.message}
        ) from error
