import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.access.policy import Action, ObjectAccess, authorize
from app.identity.models import Participant
from app.scene_tools.geometry import path_visible
from app.scene_tools.models import (
    Annotation,
    AnnotationData,
    AnnotationTarget,
    AnnotationUpdate,
    Fog,
)
from app.scenes.models import SceneFailure


async def project_annotations(
    connection: AsyncConnection, actor: Participant, scene_id: UUID | None, fog: Fog, gm: bool
) -> list[Annotation]:
    rows = (
        (
            await connection.execute(
                text(
                    """
select id,owner_participant_id,kind,points,label,visibility from app.scene_annotations
where scene_id=:scene and deleted_at is null order by created_at,id
"""
                ),
                {"scene": scene_id},
            )
        )
        .mappings()
        .all()
    )
    annotations = []
    for row in rows:
        access = ObjectAccess(
            kind="annotation",
            visibility=row["visibility"],
            owner_participant_id=row["owner_participant_id"],
        )
        if authorize(actor, Action.VIEW_ITEM, actor.room_id, object_access=access).allowed and (
            gm
            or path_visible(
                fog,
                AnnotationData.model_validate(
                    {key: row[key] for key in AnnotationData.model_fields}
                ).points,
            )
        ):
            annotations.append(
                Annotation.model_validate(
                    {
                        **dict(row),
                        "can_edit": authorize(
                            actor, Action.MANAGE_ANNOTATION, actor.room_id, object_access=access
                        ).allowed,
                    }
                )
            )
    return annotations


async def apply_annotation(
    connection: AsyncConnection,
    actor: Participant,
    kind: str,
    payload: dict[str, Any],
    room: dict[str, Any],
) -> tuple[UUID, dict[str, Any], dict[str, Any]]:
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
    gm = authorize(actor, Action.MANAGE_SCENE, actor.room_id).allowed
    before = None
    identifier = uuid4()
    owner = actor.id
    if kind == "annotation.create":
        data = AnnotationData.model_validate(payload)
        count = await connection.scalar(
            text(
                """select count(*) from app.scene_annotations
                    where scene_id=:scene and deleted_at is null"""
            ),
            {"scene": scene_id},
        )
        if int(count or 0) >= 500:
            raise SceneFailure("invalid_command", "Достигнут лимит: 500 меток на сцене")
    elif kind in {"annotation.update", "annotation.delete"}:
        target = (
            AnnotationUpdate.model_validate(payload)
            if kind == "annotation.update"
            else AnnotationTarget.model_validate(payload)
        )
        identifier = target.annotation_id
        saved = (
            (
                await connection.execute(
                    text(
                        """
select id,owner_participant_id,kind,points,label,visibility,deleted_at from
app.scene_annotations where id=:id and scene_id=:scene for update
"""
                    ),
                    {"id": identifier, "scene": scene_id},
                )
            )
            .mappings()
            .first()
        )
        if saved is None or saved["deleted_at"] is not None:
            raise SceneFailure("forbidden", "Метка недоступна")
        data = AnnotationData.model_validate(
            {key: saved[key] for key in AnnotationData.model_fields}
        )
        owner = saved["owner_participant_id"]
        access = ObjectAccess(
            kind="annotation", visibility=data.visibility, owner_participant_id=owner
        )
        if not authorize(
            actor, Action.MANAGE_ANNOTATION, actor.room_id, object_access=access
        ).allowed or (not gm and not path_visible(Fog.model_validate(scene["fog"]), data.points)):
            raise SceneFailure("forbidden", "Нет прав на эту метку")
        before = {
            **data.model_dump(mode="json"),
            "id": str(identifier),
            "owner_participant_id": str(owner),
            "deleted_at": None,
        }
        if isinstance(target, AnnotationUpdate):
            data = target.annotation
    else:
        raise SceneFailure("invalid_command", "Неизвестная команда метки")
    if not gm and (
        data.visibility != "everyone"
        or not path_visible(Fog.model_validate(scene["fog"]), data.points)
    ):
        raise SceneFailure("forbidden", "Область метки недоступна")
    parameters = {
        "id": identifier,
        "scene": scene_id,
        "campaign": room["campaign_id"],
        "actor": owner,
        "kind": data.kind,
        "points": data.model_dump_json(include={"points"}),
        "label": data.label,
        "visibility": data.visibility,
    }
    # Points are serialized separately; no interpolated SQL names or values.
    parameters["points"] = json.dumps(data.model_dump(mode="json")["points"])
    if kind == "annotation.create":
        await connection.execute(
            text(
                """
insert into
app.scene_annotations(id,scene_id,campaign_id,owner_participant_id,kind,points,label,visibility)
values(:id,:scene,:campaign,:actor,:kind,cast(:points as jsonb),:label,:visibility)
"""
            ),
            parameters,
        )
    elif kind == "annotation.update":
        await connection.execute(
            text(
                """
update app.scene_annotations set kind=:kind,points=cast(:points as
jsonb),label=:label,visibility=:visibility where id=:id
"""
            ),
            parameters,
        )
    else:
        await connection.execute(
            text("update app.scene_annotations set deleted_at=now() where id=:id"),
            {"id": identifier},
        )
    canonical = {
        **data.model_dump(mode="json"),
        "id": str(identifier),
        "owner_participant_id": str(owner),
        "deleted": kind == "annotation.delete",
    }
    return (
        scene_id,
        {"scene_id": str(scene_id), "annotation": canonical},
        {"kind": "annotation", "scene_id": str(scene_id), "id": str(identifier), "state": before},
    )
