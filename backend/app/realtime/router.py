import asyncio
import contextlib
import json
import time
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from anyio import CancelScope
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis.exceptions import RedisError

from app.campaigns.dependencies import get_campaign_service
from app.campaigns.security_journal import SecurityEventReason
from app.campaigns.service import CampaignService
from app.config import Settings, get_settings
from app.events.projection import synchronize
from app.identity.dependencies import resolve_room_actor
from app.identity.models import Participant
from app.realtime.service import Realtime, TicketRateLimitError
from app.scenes.dependencies import get_scene_service
from app.scenes.models import Command, SceneFailure
from app.scenes.service import SceneService

router = APIRouter(prefix="/api/v1/rooms/{room_id}/realtime", tags=["realtime"])


class ExpiredAuthorizationError(Exception):
    pass


def require_current_authorization(actor: Participant) -> None:
    if actor.authorization_expired:
        raise ExpiredAuthorizationError


class Subscription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = "subscribe"
    ticket: str = Field(min_length=32, max_length=128)
    cursor: int = Field(default=0, ge=0)


class DragPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["preview"]
    item_id: UUID
    x: float = Field(ge=-1000000, le=1000000, allow_inf_nan=False)
    y: float = Field(ge=-1000000, le=1000000, allow_inf_nan=False)
    clear: bool = False


@router.post("/ticket")
async def issue_ws_ticket(
    room_id: UUID,
    request: Request,
    response: Response,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
) -> dict[str, object]:
    realtime: Realtime = request.app.state.realtime
    try:
        ticket = await realtime.issue(actor)
    except TicketRateLimitError as error:
        raise HTTPException(
            429, detail={"code": "rate_limited", "message": "Подождите перед повтором"}
        ) from error
    except RedisError as error:
        raise HTTPException(
            503,
            detail={
                "code": "realtime_unavailable",
                "message": "Связь временно недоступна. Подтверждённое состояние сохранено.",
            },
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return {"ticket": ticket, "expires_in": 30}


@router.websocket("/ws")
async def subscribe(
    websocket: WebSocket,
    room_id: UUID,
    service: Annotated[SceneService, Depends(get_scene_service)],
    campaign_service: Annotated[CampaignService, Depends(get_campaign_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    origin = websocket.headers.get("origin")
    if websocket.query_params or (origin and origin not in settings.frontend_origins):
        await websocket.close(4403)
        return
    await websocket.accept()
    realtime: Realtime = websocket.app.state.realtime
    try:
        data = await asyncio.wait_for(websocket.receive_json(), 5)
        subscription = Subscription.model_validate(data)
        if subscription.type != "subscribe":
            raise ValueError("invalid frame")
        actor = await realtime.consume(subscription.ticket, room_id)
        if actor is None:
            await websocket.close(4401)
            return
        sync = await synchronize(service.repository, actor, subscription.cursor)
        require_current_authorization(actor)
        await serve(
            websocket, realtime, service, campaign_service, actor, sync, subscription.cursor
        )
    except ExpiredAuthorizationError:
        await websocket.close(4401)
    except SceneFailure as error:
        await websocket.close(4403 if error.code == "forbidden" else 1013)
    except (RedisError, TimeoutError):
        await websocket.close(1013)
    except (ValidationError, ValueError):
        await websocket.close(4400)
    except WebSocketDisconnect:
        pass


async def serve(
    websocket: WebSocket,
    realtime: Realtime,
    service: SceneService,
    campaign_service: CampaignService,
    actor: Participant,
    sync: dict[str, Any],
    requested_cursor: int,
) -> None:
    assert realtime.redis is not None
    redis = realtime.redis
    channel = f"vtt:room:{actor.room_id}"
    presence = f"vtt:presence:{actor.room_id}:{uuid4().hex}"
    receiver = asyncio.create_task(websocket.receive_json())
    cursor = 0
    checked = 0.0
    heartbeat = time.monotonic()
    opened = False
    async with redis.pubsub() as pubsub:
        await pubsub.subscribe(channel)
        await redis.set(presence, str(actor.id), ex=15)
        try:
            # Subscribe before the snapshot send; periodic PG reconciliation also
            # covers a commit racing the first snapshot or a lost Redis wakeup.
            require_current_authorization(actor)
            await campaign_service.connection_event(actor, "connection.opened", "authorized_socket")
            opened = True
            require_current_authorization(actor)
            # The journal append yielded after the first authorization. Obtain
            # a current membership/session-filtered projection before delivery.
            sync = await synchronize(service.repository, actor, requested_cursor)
            require_current_authorization(actor)
            await websocket.send_json(sync)
            cursor = sync["snapshot"]["event_cursor"]
            while True:
                done, _ = await asyncio.wait({receiver}, timeout=0.2)
                require_current_authorization(actor)
                refresh = False
                force = False
                if done:
                    frame = receiver.result()
                    receiver = asyncio.create_task(websocket.receive_json())
                    count = await redis.incr(f"vtt:rate:{actor.id}:frames")
                    if count == 1:
                        await redis.expire(f"vtt:rate:{actor.id}:frames", 1)
                    if count > 40:
                        await websocket.close(4429)
                        return
                    if not isinstance(frame, dict):
                        raise ValueError("invalid frame")
                    kind = frame.get("type")
                    if kind == "command":
                        command = Command.model_validate(frame.get("command"))
                        if command.room_id != actor.room_id:
                            raise ValueError("wrong room")
                        result = await service.execute_scene_command(actor, command)
                        require_current_authorization(actor)
                        await websocket.send_json(
                            {"type": "command_result", "result": result.model_dump(mode="json")}
                        )
                        if result.error_code == "forbidden":
                            # Distinguish lost room access from a forbidden object action.
                            await synchronize(service.repository, actor, cursor)
                        if result.status in {"accepted", "duplicate"}:
                            for affected in await service.notification_rooms(actor):
                                await realtime.notify(affected)
                            refresh = force = True
                    elif kind == "resync":
                        refresh = force = True
                    elif kind == "ping":
                        refresh = True
                        heartbeat = 0
                    elif kind == "preview":
                        preview = DragPreview.model_validate(frame)
                        projection = await service.repository.get_projection(actor, actor.room_id)
                        item = next(
                            (item for item in projection.items if item.id == preview.item_id), None
                        )
                        if item is not None and item.can_transform:
                            payload = {
                                **preview.model_dump(mode="json"),
                                "scene_id": str(projection.scene.id) if projection.scene else None,
                                "actor_id": str(actor.id),
                                "source": presence,
                            }
                            key = f"vtt:preview:{actor.room_id}:{actor.id}"
                            if preview.clear:
                                await redis.delete(key)
                            else:
                                await redis.set(key, json.dumps(payload), ex=2)
                            await redis.publish(channel, json.dumps(payload))
                    else:
                        raise ValueError("unknown frame")
                notification = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.01
                )
                if notification:
                    notice = json.loads(notification["data"])
                    refresh = refresh or notice["type"] == "changed"
                    if notice["type"] == "preview" and notice["source"] != presence:
                        projection = await service.repository.get_projection(actor, actor.room_id)
                        if (
                            projection.scene
                            and str(projection.scene.id) == notice["scene_id"]
                            and any(str(item.id) == notice["item_id"] for item in projection.items)
                        ):
                            require_current_authorization(actor)
                            await websocket.send_json(
                                {key: notice[key] for key in ("type", "item_id", "x", "y", "clear")}
                            )
                now = time.monotonic()
                if refresh or now - checked >= 1:
                    current = await synchronize(service.repository, actor, cursor)
                    checked = now
                    next_cursor = current["snapshot"]["event_cursor"]
                    if (
                        force
                        or next_cursor != cursor
                        or current["snapshot"]["aggregate_version"]
                        != sync["snapshot"]["aggregate_version"]
                    ):
                        require_current_authorization(actor)
                        await websocket.send_json(current)
                        cursor = next_cursor
                        sync = current
                if now - heartbeat >= 5:
                    await redis.set(presence, str(actor.id), ex=15)
                    members = await realtime.connected_actors(actor.room_id)
                    require_current_authorization(actor)
                    await websocket.send_json(
                        {
                            "type": "heartbeat",
                            "presence_count": len(members) if members is not None else None,
                        }
                    )
                    heartbeat = now
        finally:
            # A canceled ASGI task must finish the observed close append as well
            # as releasing its own lease. No browser acknowledgement fabricates it.
            with CancelScope(shield=True):
                receiver.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await receiver
                with contextlib.suppress(RedisError):
                    await redis.delete(presence)
                if opened:
                    connected = await realtime.connected_actors(actor.room_id)
                    reason: SecurityEventReason = (
                        "socket_closed_actor_unknown"
                        if connected is None
                        else (
                            "socket_closed_actor_connected"
                            if str(actor.id) in connected
                            else "socket_closed_actor_disconnected"
                        )
                    )
                    await campaign_service.connection_event(actor, "connection.closed", reason)
