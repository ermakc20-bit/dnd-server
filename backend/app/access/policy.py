from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from app.identity.models import Participant, ParticipantRole


class Action(StrEnum):
    MANAGE_ROOM = "manage_room"
    REMOVE_PARTICIPANT = "remove_participant"
    VIEW_ROOM = "view_room"
    JOIN_ROOM = "join_room"
    MANAGE_SCENE = "manage_scene"
    VIEW_ITEM = "view_item"
    TRANSFORM_ITEM = "transform_item"
    UPLOAD_ASSET = "upload_asset"
    MANAGE_CARD = "manage_card"
    MANAGE_ANNOTATION = "manage_annotation"
    VIEW_CARD = "view_card"
    CHANGE_RESOURCE = "change_resource"
    EXPORT_CARD = "export_card"
    PRESENT_ABILITY = "present_ability"


class ObjectAccess(BaseModel):
    kind: str
    visibility: str = "everyone"
    owner_participant_id: UUID | None = None
    is_locked: bool = False
    allow_player_export: bool = False


class Decision(BaseModel):
    allowed: bool
    reason: str | None = None


def authorize(
    actor: Participant,
    action: Action,
    resource_id: UUID,
    subject: Participant | None = None,
    *,
    object_access: ObjectAccess | None = None,
) -> Decision:
    if actor.removed_at is not None:
        return Decision(allowed=False, reason="participant_removed")
    if actor.room_id != resource_id:
        return Decision(allowed=False, reason="wrong_room")
    is_gm = actor.role is ParticipantRole.GM and actor.user_id is not None
    if action in {
        Action.MANAGE_ROOM,
        Action.REMOVE_PARTICIPANT,
        Action.MANAGE_SCENE,
        Action.UPLOAD_ASSET,
        Action.MANAGE_CARD,
    }:
        if actor.role is not ParticipantRole.GM or actor.user_id is None:
            return Decision(allowed=False, reason="registered_gm_required")
    if action is Action.REMOVE_PARTICIPANT:
        if subject is None:
            return Decision(allowed=False, reason="participant_target_required")
        if subject.room_id != resource_id:
            return Decision(allowed=False, reason="wrong_target_room")
        if subject.role is ParticipantRole.GM:
            return Decision(allowed=False, reason="cannot_remove_gm")
    if action in {
        Action.MANAGE_ANNOTATION,
        Action.VIEW_ITEM,
        Action.TRANSFORM_ITEM,
        Action.VIEW_CARD,
        Action.CHANGE_RESOURCE,
        Action.EXPORT_CARD,
        Action.PRESENT_ABILITY,
    }:
        if object_access is None:
            return Decision(allowed=False, reason="object_required")
        if not is_gm:
            if object_access.visibility == "gm_only" or (
                object_access.visibility == "owner_only"
                and object_access.owner_participant_id != actor.id
            ):
                return Decision(allowed=False, reason="hidden_item")
            if action is Action.MANAGE_ANNOTATION and (
                object_access.kind != "annotation" or object_access.owner_participant_id != actor.id
            ):
                return Decision(allowed=False, reason="annotation_not_owned")
            if action is Action.TRANSFORM_ITEM and (
                object_access.kind != "token"
                or object_access.is_locked
                or object_access.owner_participant_id != actor.id
            ):
                return Decision(allowed=False, reason="token_not_controlled")
            if action in {Action.CHANGE_RESOURCE, Action.EXPORT_CARD, Action.PRESENT_ABILITY} and (
                object_access.kind != "card"
                or object_access.owner_participant_id != actor.id
                or (action is Action.EXPORT_CARD and not object_access.allow_player_export)
            ):
                return Decision(allowed=False, reason="card_not_controlled")
    return Decision(allowed=True)
