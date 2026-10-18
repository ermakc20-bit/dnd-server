from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.cards.export import export_html
from app.cards.models import Card, CardPage, CardView
from app.cards.repository import CardRepository
from app.identity.dependencies import resolve_room_actor
from app.identity.models import Participant
from app.scenes.dependencies import get_scene_service
from app.scenes.models import SceneFailure
from app.scenes.service import SceneService

router = APIRouter(prefix="/api/v1/rooms/{room_id}/cards", tags=["cards"])
Actor = Annotated[Participant, Depends(resolve_room_actor)]
Service = Annotated[SceneService, Depends(get_scene_service)]


def failure(error: SceneFailure) -> HTTPException:
    return HTTPException(
        status_code=error.status_code, detail={"code": error.code, "message": error.message}
    )


@router.get("", response_model=CardPage)
async def list_cards(
    room_id: UUID,
    actor: Actor,
    service: Service,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    search: Annotated[str, Query(max_length=160)] = "",
) -> CardPage:
    try:
        return await CardRepository(service.repository.engine).list_cards(
            actor, room_id, offset=offset, limit=limit, search=search
        )
    except SceneFailure as error:
        raise failure(error) from error


@router.get("/{card_id}/export")
async def export_card(
    room_id: UUID,
    card_id: UUID,
    actor: Actor,
    service: Service,
    format: Literal["json", "html"] = "json",
) -> Response:
    try:
        view = await CardRepository(service.repository.engine).get_card(
            actor, room_id, card_id, export=True
        )
        card = Card.model_validate(view.model_dump(include=set(Card.model_fields)))
        content = export_html(card) if format == "html" else card.model_dump_json()
        return Response(
            content=content,
            media_type="text/html" if format == "html" else "application/json",
            headers={
                "Content-Disposition": f'attachment; filename="card-{card_id}.{format}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except SceneFailure as error:
        raise failure(error) from error


@router.get("/{card_id}", response_model=CardView)
async def get_card(room_id: UUID, card_id: UUID, actor: Actor, service: Service) -> CardView:
    try:
        return await CardRepository(service.repository.engine).get_card(actor, room_id, card_id)
    except SceneFailure as error:
        raise failure(error) from error
