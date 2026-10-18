import json
import re
import secrets
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.access.policy import Action, authorize
from app.dice_log.models import RollEvent, RollRequest
from app.identity.models import Participant
from app.scenes.models import SceneFailure


async def roll(
    connection: AsyncConnection, actor: Participant, payload: dict[str, Any], command_id: UUID
) -> dict[str, Any]:
    request = RollRequest.model_validate(payload)
    expression = request.expression.strip().lower()
    match = re.fullmatch(r"([1-9][0-9]{0,2})d([1-9][0-9]{0,3})([+-][0-9]{1,5})?", expression)
    if match is None:
        raise SceneFailure("invalid_command", "Формат броска: NdS±K, например 2d6+3")
    count, sides, modifier = int(match[1]), int(match[2]), int(match[3] or 0)
    if count > 100 or sides > 1000 or abs(modifier) > 10000:
        raise SceneFailure("invalid_command", "До 100 кубов, 1000 граней и модификатор ±10000")
    if (
        request.visibility == "gm_only"
        and not authorize(actor, Action.MANAGE_SCENE, actor.room_id).allowed
    ):
        raise SceneFailure("forbidden", "Приватные броски доступны мастеру")
    results = tuple(secrets.randbelow(sides) + 1 for _ in range(count))
    expression = f"{count}d{sides}" + (f"{modifier:+d}" if modifier else "")
    identifier = uuid4()
    created = await connection.scalar(
        text(
            """
insert into
app.dice_rolls(id,room_id,actor_participant_id,command_id,expression,results,modifier,total,visibility)
values(:id,:room,:actor,:command,:expression,cast(:results as
jsonb),:modifier,:total,:visibility) returning created_at
"""
        ),
        {
            "id": identifier,
            "room": actor.room_id,
            "actor": actor.id,
            "command": command_id,
            "expression": expression,
            "results": json.dumps(results),
            "modifier": modifier,
            "total": sum(results) + modifier,
            "visibility": request.visibility,
        },
    )
    event = RollEvent(
        id=identifier,
        expression=expression,
        results=results,
        modifier=modifier,
        total=sum(results) + modifier,
        visibility=request.visibility,
        created_at=created,
    )
    return {"roll": event.model_dump(mode="json")}
