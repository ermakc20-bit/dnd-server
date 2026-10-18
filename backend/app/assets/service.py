from __future__ import annotations

import asyncio
import warnings
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.access.database import participant_is_active
from app.access.policy import Action, ObjectAccess, authorize
from app.assets.models import MAX_ASSET_BYTES, AssetMetadata, DownloadGrant, UploadRequest
from app.assets.storage import PrivateStorage, StorageUnavailable
from app.campaigns.repository import _async_database_url
from app.identity.models import Participant
from app.scene_tools.geometry import object_visible
from app.scene_tools.models import Fog
from app.scenes.models import SceneFailure

FORMAT_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "AVIF": "image/avif"}


def inspect_asset(data: bytes, content_type: str) -> tuple[int, int]:
    if not 0 < len(data) <= MAX_ASSET_BYTES:
        raise SceneFailure(
            "invalid_asset", "Размер изображения должен быть от 1 байта до 50 МБ", 400
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if FORMAT_MIME.get(image.format or "") != content_type:
                    raise SceneFailure(
                        "invalid_asset", "Тип файла не соответствует изображению", 400
                    )
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
                return image.size
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as error:
        raise SceneFailure(
            "invalid_asset", "Изображение повреждено или слишком велико", 400
        ) from error


class AssetService:
    def __init__(self, database_url: str, storage: PrivateStorage) -> None:
        self.engine = create_async_engine(_async_database_url(database_url), pool_pre_ping=True)
        self.storage = storage

    async def _authorized(
        self, connection: AsyncConnection, actor: Participant, action: Action
    ) -> None:
        if not authorize(actor, action, actor.room_id).allowed or not await participant_is_active(
            connection, actor
        ):
            raise SceneFailure("forbidden", "Нет доступа к изображению")

    @staticmethod
    def _metadata(row: dict[str, Any], room_id: UUID) -> AssetMetadata:
        return AssetMetadata.model_validate(
            {
                **row,
                "upload_url": f"/api/v1/rooms/{room_id}/assets/{row['id']}/content",
            }
        )

    async def prepare_upload(self, actor: Participant, request: UploadRequest) -> AssetMetadata:
        async with self.engine.begin() as connection:
            await self._authorized(connection, actor, Action.UPLOAD_ASSET)
            asset_id = uuid4()
            key = f"{actor.campaign_id}/{asset_id}"
            row = (
                (
                    await connection.execute(
                        text("""
                insert into app.assets(id,owner_user_id,campaign_id,uploaded_by,name,kind,
                                       object_key,content_type,byte_size)
                values(:id,:user,:campaign,:actor,:name,:kind,:key,:mime,:size)
                returning id,name,content_type,byte_size,width,height,status
            """),
                        {
                            "id": asset_id,
                            "user": actor.user_id,
                            "campaign": actor.campaign_id,
                            "actor": actor.id,
                            "name": request.name,
                            "kind": request.kind,
                            "key": key,
                            "mime": request.content_type,
                            "size": request.byte_size,
                        },
                    )
                )
                .mappings()
                .one()
            )
            return self._metadata(dict(row), actor.room_id)

    async def upload(
        self,
        actor: Participant,
        asset_id: UUID,
        content_type: str,
        data: bytes,
    ) -> AssetMetadata:
        async with self.engine.begin() as connection:
            await self._authorized(connection, actor, Action.UPLOAD_ASSET)
            row = (
                (
                    await connection.execute(
                        text("""
                select * from app.assets where id=:id and campaign_id=:campaign
                and uploaded_by=:actor for update
            """),
                        {"id": asset_id, "campaign": actor.campaign_id, "actor": actor.id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise SceneFailure("forbidden", "Нет доступа к изображению")
            if content_type != row["content_type"] or len(data) != row["byte_size"]:
                raise SceneFailure("invalid_asset", "Размер или тип файла не совпадает", 400)
            width, height = await asyncio.to_thread(inspect_asset, data, content_type)
            if row["status"] == "ready":
                return self._metadata(dict(row), actor.room_id)
            try:
                await self.storage.put(row["object_key"], data, content_type)
            except StorageUnavailable as error:
                raise SceneFailure(
                    "asset_unavailable", "Изображение временно недоступно", 503
                ) from error
            await connection.execute(
                text("""
                update app.assets set status='ready',width=:width,height=:height where id=:id
            """),
                {"id": asset_id, "width": width, "height": height},
            )
            return self._metadata(
                {**row, "status": "ready", "width": width, "height": height}, actor.room_id
            )

    async def authorize_download(self, actor: Participant, asset_id: UUID) -> DownloadGrant:
        async with self.engine.begin() as connection:
            await self._authorized(connection, actor, Action.VIEW_ROOM)
            room = (
                (
                    await connection.execute(
                        text("""
                select r.active_scene_id,s.fog from app.rooms r left join app.scenes s
                  on s.id=r.active_scene_id and s.deleted_at is null
                where r.id=:room and not r.is_archived for share of r
            """),
                        {"room": actor.room_id},
                    )
                )
                .mappings()
                .first()
            )
            asset = (
                (
                    await connection.execute(
                        text("""
                select object_key from app.assets where id=:id and campaign_id=:campaign
                  and status='ready'
            """),
                        {"id": asset_id, "campaign": actor.campaign_id},
                    )
                )
                .mappings()
                .first()
            )
            allowed = authorize(actor, Action.MANAGE_SCENE, actor.room_id).allowed
            if not allowed and room:
                items = (
                    (
                        await connection.execute(
                            text("""
                    select kind,visibility,owner_participant_id,is_locked,
                           x,y,width,height,rotation from app.scene_items
                    where scene_id=:scene and asset_id=:asset and deleted_at is null

                """),
                            {"scene": room["active_scene_id"], "asset": asset_id},
                        )
                    )
                    .mappings()
                    .all()
                )
                allowed = any(
                    authorize(
                        actor,
                        Action.VIEW_ITEM,
                        actor.room_id,
                        object_access=ObjectAccess.model_validate(item),
                    ).allowed
                    and (
                        item["kind"] == "map"
                        or object_visible(
                            Fog.model_validate(room["fog"]),
                            item["x"],
                            item["y"],
                            item["width"],
                            item["height"],
                            item["rotation"],
                        )
                    )
                    for item in items
                )
            if asset is None or not allowed:
                raise SceneFailure("forbidden", "Нет доступа к изображению")
            try:
                url = await self.storage.sign_download(asset["object_key"], 60)
            except StorageUnavailable as error:
                raise SceneFailure(
                    "asset_unavailable", "Изображение временно недоступно", 503
                ) from error
            return DownloadGrant(url=url)
