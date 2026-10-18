from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.access.policy import Action, authorize
from app.cards.models import (
    Card,
    CardData,
    ChangeResource,
    CloneCard,
    CreateCard,
    DeleteCard,
    UpdateCard,
)
from app.cards.repository import card_access, load_card, project_card
from app.identity.models import Participant
from app.scenes.models import SceneFailure
from app.system_packages.service import validate_card


async def validate_references(
    connection: AsyncConnection,
    data: CardData,
    actor: Participant,
    *,
    retained_owner_id: UUID | None = None,
) -> None:
    validate_card(data)
    if data.owner_participant_id and not await connection.scalar(
        text("""
        select p.id from app.participants p where p.id=:id and p.room_id=:room
        and p.campaign_id=:campaign and (p.removed_at is null or p.id=:retained)
    """),
        {
            "id": data.owner_participant_id,
            "room": actor.room_id,
            "campaign": actor.campaign_id,
            "retained": retained_owner_id,
        },
    ):
        raise SceneFailure("forbidden", "Участник недоступен")
    if data.image_asset_id and not await connection.scalar(
        text("""
        select id from app.assets where id=:id and campaign_id=:campaign and status='ready'
    """),
        {"id": data.image_asset_id, "campaign": actor.campaign_id},
    ):
        raise SceneFailure("asset_unavailable", "Изображение недоступно")


async def duplicate_card_for_token(
    connection: AsyncConnection, actor: Participant, card_id: UUID, owner_id: UUID | None
) -> UUID:
    original = await load_card(connection, card_id, actor.room_id, lock=True)
    if original.owner_participant_id != owner_id:
        raise SceneFailure("forbidden", "Владельцы карточки и токена не согласованы")
    data = CardData.model_validate(original.model_dump(include=set(CardData.model_fields)))
    data.external_key = None
    for entry in data.inventory:
        entry.id = uuid4()
    for ability in data.abilities:
        ability.id = uuid4()
    await validate_references(connection, data, actor)
    identifier = uuid4()
    await connection.execute(
        text("""
        insert into app.cards(id,campaign_id,room_id,owner_participant_id,image_asset_id,data)
        values(:id,:campaign,:room,:owner,:image,cast(:data as jsonb))
        """),
        {
            "id": identifier,
            "campaign": actor.campaign_id,
            "room": actor.room_id,
            "owner": data.owner_participant_id,
            "image": data.image_asset_id,
            "data": data.model_dump_json(),
        },
    )
    return identifier


async def apply_card_command(
    connection: AsyncConnection, actor: Participant, kind: str, payload: dict[str, Any]
) -> dict[str, Any]:
    models: dict[str, type[CreateCard | CloneCard | ChangeResource | DeleteCard]] = {
        "card.create": CreateCard,
        "card.update": UpdateCard,
        "card.clone": CloneCard,
        "card.resource": ChangeResource,
        "card.delete": DeleteCard,
    }
    if kind not in models:
        raise SceneFailure("invalid_command", "Неизвестная команда карточки")
    if kind != "card.resource" and not authorize(actor, Action.MANAGE_CARD, actor.room_id).allowed:
        raise SceneFailure("forbidden", "Структуру карточки меняет мастер")
    request = models[kind].model_validate(payload)
    if isinstance(request, DeleteCard):
        await load_card(connection, request.card_id, actor.room_id, lock=True)
        if await connection.scalar(
            text(
                "select id from app.scene_items where card_id=:card and deleted_at is null limit 1"
            ),
            {"card": request.card_id},
        ):
            raise SceneFailure("card_in_use", "Сначала удалите все токены этой карточки")
        await connection.execute(
            text(
                "update app.cards set "
                "deleted_at=now(),version=version+1,updated_at=now() where id=:id"
            ),
            {"id": request.card_id},
        )
        deleted_card = await load_card(
            connection, request.card_id, actor.room_id, include_deleted=True
        )
        return {
            "card_id": str(request.card_id),
            "card": deleted_card.model_dump(mode="json"),
            "deleted": True,
        }
    card_id = uuid4()
    original: Card | None = None
    if isinstance(request, CreateCard):
        data = request.card
        if isinstance(request, UpdateCard):
            card_id = request.card_id
            original = await load_card(connection, card_id, actor.room_id, lock=True)
    else:
        original = await load_card(connection, request.card_id, actor.room_id, lock=True)
        data = CardData.model_validate(original.model_dump(include=set(CardData.model_fields)))
        if isinstance(request, CloneCard):
            data.name = request.name or f"{data.name[:150]} · копия"
            data.owner_participant_id = None
            data.external_key = None
            data.allow_player_export = False
            for entry in data.inventory:
                entry.id = uuid4()
            for ability in data.abilities:
                ability.id = uuid4()
        else:
            card_id = request.card_id
            allowed = authorize(
                actor, Action.CHANGE_RESOURCE, actor.room_id, object_access=card_access(original)
            ).allowed
            visible = project_card(original, actor)
            if not allowed or request.resource_key not in {r.key for r in visible.resources}:
                raise SceneFailure("forbidden", "Изменение запрещено")
            resource = next(r for r in data.resources if r.key == request.resource_key)
            resource.current = request.current
            data = CardData.model_validate(data.model_dump())
    retained_owner = (
        original.owner_participant_id
        if original is not None
        and data.owner_participant_id == original.owner_participant_id
        and kind in {"card.update", "card.resource"}
        and authorize(actor, Action.MANAGE_CARD, actor.room_id).allowed
        else None
    )
    await validate_references(connection, data, actor, retained_owner_id=retained_owner)
    values = {
        "id": card_id,
        "campaign": actor.campaign_id,
        "room": actor.room_id,
        "owner": data.owner_participant_id,
        "image": data.image_asset_id,
        "data": data.model_dump_json(),
    }
    if kind in {"card.create", "card.clone"}:
        await connection.execute(
            text("""
        insert into app.cards(id,campaign_id,room_id,owner_participant_id,image_asset_id,data)
        values(:id,:campaign,:room,:owner,:image,cast(:data as jsonb))
        """),
            values,
        )
    else:
        await connection.execute(
            text("""
        update app.cards set data=cast(:data as jsonb),owner_participant_id=:owner,
          image_asset_id=:image,version=version+1,updated_at=now() where id=:id and room_id=:room
        """),
            values,
        )
    saved = await load_card(connection, card_id, actor.room_id)
    return {"card_id": str(card_id), "card": saved.model_dump(mode="json")}
