from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.access.database import participant_is_active
from app.access.policy import Action, ObjectAccess, authorize
from app.cards.models import Card, CardPage, CardView
from app.identity.models import Participant
from app.scenes.models import SceneFailure


def card_access(card: Card) -> ObjectAccess:
    return ObjectAccess(
        kind="card",
        visibility=card.visibility,
        owner_participant_id=card.owner_participant_id,
        allow_player_export=card.allow_player_export,
    )


def card_from_row(row: Any) -> Card:
    return Card.model_validate(
        {
            **row["data"],
            **{
                key: row[key]
                for key in (
                    "id",
                    "campaign_id",
                    "room_id",
                    "owner_participant_id",
                    "image_asset_id",
                    "version",
                    "created_at",
                    "updated_at",
                )
            },
        }
    )


def project_card(card: Card, actor: Participant) -> CardView:
    access = card_access(card)
    manage = authorize(actor, Action.MANAGE_CARD, actor.room_id).allowed
    data = card.model_dump()
    if not manage:

        def visible(visibility: str) -> bool:
            return visibility == "everyone" or (
                visibility == "owner_only" and card.owner_participant_id == actor.id
            )

        for key in ("fields", "resources", "skills", "inventory", "abilities"):
            data[key] = [entry for entry in data[key] if visible(entry["visibility"])]
        for ability in data["abilities"]:
            if ability["uses"] and not visible(ability["uses"]["visibility"]):
                ability["uses"] = None
        if not visible(card.notes_visibility):
            data["notes"] = None
        data["external_key"] = None
    return CardView(
        **data,
        can_edit_structure=manage,
        can_edit_current=authorize(
            actor, Action.CHANGE_RESOURCE, actor.room_id, object_access=access
        ).allowed,
        can_export=authorize(
            actor, Action.EXPORT_CARD, actor.room_id, object_access=access
        ).allowed,
    )


async def load_card(
    connection: AsyncConnection,
    card_id: UUID,
    room_id: UUID,
    *,
    lock: bool = False,
    include_deleted: bool = False,
) -> Card:
    query = "select * from app.cards where id=:id and room_id=:room"
    if not include_deleted:
        query += " and deleted_at is null"
    row = (
        (
            await connection.execute(
                text(query + (" for update" if lock else "")), {"id": card_id, "room": room_id}
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise SceneFailure("card_unavailable", "Карточка недоступна", 404)
    return card_from_row(row)


class CardRepository:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def _check(self, connection: AsyncConnection, actor: Participant, room_id: UUID) -> None:
        if (
            not authorize(actor, Action.VIEW_ROOM, room_id).allowed
            or not await participant_is_active(connection, actor)
            or not await connection.scalar(
                text("select id from app.rooms where id=:id and not is_archived"), {"id": room_id}
            )
        ):
            raise SceneFailure("forbidden", "Нет доступа к карточкам")

    async def get_card(
        self, actor: Participant, room_id: UUID, card_id: UUID, *, export: bool = False
    ) -> CardView:
        async with self.engine.begin() as connection:
            await self._check(connection, actor, room_id)
            card = await load_card(connection, card_id, room_id)
            action = Action.EXPORT_CARD if export else Action.VIEW_CARD
            if not authorize(actor, action, room_id, object_access=card_access(card)).allowed:
                raise SceneFailure("forbidden", "Нет доступа к карточке")
            return project_card(card, actor)

    async def list_cards(
        self,
        actor: Participant,
        room_id: UUID,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str = "",
    ) -> CardPage:
        async with self.engine.begin() as connection:
            await self._check(connection, actor, room_id)
            manage = authorize(actor, Action.MANAGE_CARD, room_id).allowed
            rows = (
                (
                    await connection.execute(
                        text("""
                select * from app.cards where room_id=:room and deleted_at is null
                and (:manage or data->>'visibility'='everyone' or
                     (data->>'visibility'='owner_only' and owner_participant_id=:actor))
                and strpos(lower(data->>'name'),lower(:search)) > 0
                order by created_at,id limit :limit offset :offset
            """),
                        {
                            "room": room_id,
                            "manage": manage,
                            "actor": actor.id,
                            "search": search,
                            "limit": limit + 1,
                            "offset": offset,
                        },
                    )
                )
                .mappings()
                .all()
            )
            return CardPage(
                cards=[project_card(card_from_row(row), actor) for row in rows[:limit]],
                offset=offset,
                limit=limit,
                has_more=len(rows) > limit,
            )
