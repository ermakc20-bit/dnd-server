from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.assets.dependencies import get_asset_service
from app.assets.service import AssetService
from app.auth.dependencies import get_current_identity
from app.auth.jwt import AuthIdentity
from app.campaign_transfer.models import MAX_ZIP, ExportRequest, TransferFailure, TransferJob
from app.campaign_transfer.service import TransferService

router = APIRouter(prefix="/api/v1/campaign-transfers", tags=["campaign-transfer"])


@lru_cache
def build_transfer_service(assets: AssetService) -> TransferService:
    return TransferService(assets.engine, assets.storage)


def get_transfer_service(
    assets: Annotated[AssetService, Depends(get_asset_service)],
) -> TransferService:
    return build_transfer_service(assets)


Identity = Annotated[AuthIdentity, Depends(get_current_identity)]
Service = Annotated[TransferService, Depends(get_transfer_service)]


def http_error(error: TransferFailure) -> HTTPException:
    return HTTPException(error.status, detail={"code": error.code, "message": error.message})


@router.post("/{job_id}/export", response_model=TransferJob, status_code=202)
async def export_campaign(
    job_id: UUID, request: ExportRequest, actor: Identity, service: Service, response: Response
) -> TransferJob:
    response.headers["Cache-Control"] = "no-store"
    try:
        state, created = await service.begin(
            actor.user_id, job_id, "export", request.model_dump(mode="json")
        )
        return await service.start(actor.user_id, job_id) if created else state
    except TransferFailure as error:
        raise http_error(error) from None


@router.put("/{job_id}/import", response_model=TransferJob, status_code=202)
async def import_campaign(
    job_id: UUID, actor: Identity, service: Service, request: Request, response: Response
) -> TransferJob:
    response.headers["Cache-Control"] = "no-store"
    try:
        if request.headers.get("content-type", "").split(";")[0] not in {
            "application/zip",
            "application/octet-stream",
        }:
            raise TransferFailure("mime", "Выберите ZIP кампании", 415)
        state, created = await service.begin(actor.user_id, job_id, "import", {})
        if not created:
            return state
        data = bytearray()
        try:
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_ZIP:
                    raise TransferFailure("archive_limit", "ZIP превышает 256 МБ", 413)
                data.extend(chunk)
            if not data:
                raise TransferFailure("invalid_archive")
            return await service.start(actor.user_id, job_id, bytes(data))
        except TransferFailure:
            await service.fail_job(job_id, "upload_interrupted")
            raise
        except Exception:
            await service.fail_job(job_id, "upload_interrupted")
            raise TransferFailure("upload_interrupted", "Загрузка прервана", 400) from None
    except TransferFailure as error:
        raise http_error(error) from None


@router.get("/{job_id}", response_model=TransferJob)
async def status(
    job_id: UUID, actor: Identity, service: Service, response: Response
) -> TransferJob:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.get_job(actor.user_id, job_id)
    except TransferFailure as error:
        raise http_error(error) from None


@router.delete("/{job_id}", response_model=TransferJob)
async def cancel(
    job_id: UUID, actor: Identity, service: Service, response: Response
) -> TransferJob:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.cancel(actor.user_id, job_id)
    except TransferFailure as error:
        raise http_error(error) from None


@router.get("/{job_id}/archive")
async def download(job_id: UUID, actor: Identity, service: Service) -> Response:
    try:
        return Response(
            await service.download(actor.user_id, job_id),
            media_type="application/zip",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'attachment; filename="campaign-v1.zip"',
            },
        )
    except TransferFailure as error:
        raise http_error(error) from None
