from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.assets.dependencies import get_asset_service
from app.assets.models import MAX_ASSET_BYTES, AssetMetadata, DownloadGrant, UploadRequest
from app.assets.service import AssetService
from app.identity.dependencies import resolve_room_actor
from app.identity.models import Participant
from app.scenes.models import SceneFailure

router = APIRouter(prefix="/api/v1/rooms/{room_id}/assets", tags=["assets"])
Actor = Annotated[Participant, Depends(resolve_room_actor)]
Service = Annotated[AssetService, Depends(get_asset_service)]


def http_error(error: SceneFailure) -> HTTPException:
    return HTTPException(
        status_code=error.status_code, detail={"code": error.code, "message": error.message}
    )


@router.post("/prepare", response_model=AssetMetadata, status_code=201)
async def prepare_upload(
    room_id: UUID, request: UploadRequest, actor: Actor, service: Service
) -> AssetMetadata:
    try:
        return await service.prepare_upload(actor, request)
    except SceneFailure as error:
        raise http_error(error) from error


@router.put("/{asset_id}/content", response_model=AssetMetadata)
async def upload(
    room_id: UUID, asset_id: UUID, request: Request, actor: Actor, service: Service
) -> AssetMetadata:
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_ASSET_BYTES:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_asset", "message": "Изображение больше 50 МБ"},
            )
        content.extend(chunk)
    try:
        return await service.upload(
            actor, asset_id, request.headers.get("content-type", ""), bytes(content)
        )
    except SceneFailure as error:
        raise http_error(error) from error


@router.get("/{asset_id}/download", response_model=DownloadGrant)
async def authorize_download(
    room_id: UUID, asset_id: UUID, actor: Actor, service: Service
) -> DownloadGrant:
    try:
        return await service.authorize_download(actor, asset_id)
    except SceneFailure as error:
        raise http_error(error) from error
