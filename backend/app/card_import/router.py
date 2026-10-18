from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from app.card_import.bounded import parse_bounded
from app.card_import.models import MAX_BYTES, EditJob, ImportJob, ParseFailure
from app.card_import.service import ImportService
from app.card_import.templates import download_template
from app.identity.dependencies import resolve_room_actor
from app.identity.models import Participant
from app.scenes.dependencies import get_scene_service
from app.scenes.models import SceneFailure
from app.scenes.service import SceneService

router = APIRouter(prefix="/api/v1/rooms/{room_id}/imports", tags=["card-import"])
FORMATS = Literal["json", "xlsx", "docx", "txt", "pdf", "html"]
MIME = {
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "pdf": "application/pdf",
    "html": "text/html",
}


def get_import_service(scene: Annotated[SceneService, Depends(get_scene_service)]) -> ImportService:
    return ImportService(scene.repository)


Actor = Annotated[Participant, Depends(resolve_room_actor)]
Service = Annotated[ImportService, Depends(get_import_service)]


def error_response(error: SceneFailure) -> HTTPException:
    return HTTPException(error.status_code, detail={"code": error.code, "message": error.message})


@router.get("/templates/{format}")
async def template(
    format: Literal["xlsx", "docx", "txt"], actor: Actor, service: Service
) -> Response:
    try:
        await service.authorize(actor)
        return Response(
            download_template(format),
            media_type=MIME[format],
            headers={
                "Content-Disposition": f'attachment; filename="cards-v1.{format}"',
                "Cache-Control": "no-store",
            },
        )
    except SceneFailure as error:
        raise error_response(error) from None


@router.get("", response_model=list[ImportJob])
async def list_jobs(actor: Actor, service: Service, response: Response) -> list[ImportJob]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.list_jobs(actor)
    except SceneFailure as error:
        raise error_response(error) from None


@router.post("", response_model=ImportJob, status_code=201)
async def upload(
    actor: Actor,
    service: Service,
    request: Request,
    response: Response,
    format: FORMATS,
    mode: Literal["update_drafts", "new_instances"] | None = None,
) -> ImportJob:
    response.headers["Cache-Control"] = "no-store"
    try:
        await service.authorize(actor)
        if request.headers.get("content-type", "").split(";")[0] not in {
            MIME[format],
            "application/octet-stream",
        }:
            raise HTTPException(
                415, detail={"code": "mime", "message": "Тип содержимого не соответствует формату"}
            )
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise HTTPException(
                    413, detail={"code": "file_size", "message": "Файл превышает 5 МБ"}
                )
        parsed = await parse_bounded(bytes(content), format)
        return await service.upload(actor, bytes(content), parsed, mode)
    except ParseFailure as error:
        raise HTTPException(
            422,
            detail={
                "code": "parse_error",
                "message": "Проверьте документ",
                "diagnostics": [d.model_dump() for d in error.diagnostics],
            },
        ) from None
    except SceneFailure as error:
        raise error_response(error) from None


@router.get("/{job_id}", response_model=ImportJob)
async def get_job(job_id: UUID, actor: Actor, service: Service, response: Response) -> ImportJob:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.get(actor, job_id)
    except SceneFailure as error:
        raise error_response(error) from None


@router.patch("/{job_id}", response_model=ImportJob)
async def edit_job(job_id: UUID, request: Request, actor: Actor, service: Service) -> ImportJob:
    try:
        # Do not echo raw card values in framework validation errors.
        await service.authorize(actor)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise HTTPException(
                    413, detail={"code": "file_size", "message": "Черновик слишком большой"}
                )
        parsed = EditJob.model_validate_json(body)
        return await service.edit(actor, job_id, parsed)
    except ValidationError:
        raise HTTPException(
            422, detail={"code": "invalid_drafts", "message": "Проверьте поля черновиков"}
        ) from None
    except SceneFailure as error:
        raise error_response(error) from None


@router.delete("/{job_id}", response_model=ImportJob)
async def cancel_job(
    job_id: UUID, actor: Actor, service: Service, expected_version: Annotated[int, Query(ge=1)]
) -> ImportJob:
    try:
        return await service.cancel(actor, job_id, expected_version)
    except SceneFailure as error:
        raise error_response(error) from None
