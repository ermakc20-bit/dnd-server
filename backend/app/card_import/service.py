from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.access.database import participant_is_active
from app.access.policy import Action, authorize
from app.card_import.models import MAX_INSTANCES, ConfirmImport, DraftSet, EditJob, ImportJob
from app.cards.service import apply_card_command, validate_references
from app.identity.models import Participant
from app.scenes.models import SceneFailure, SceneItem
from app.scenes.payloads import CreateItem
from app.scenes.repository import SceneRepository


async def require_gm(connection: AsyncConnection, actor: Participant) -> None:
    if not authorize(
        actor, Action.MANAGE_CARD, actor.room_id
    ).allowed or not await participant_is_active(connection, actor):
        raise SceneFailure("forbidden", "Импорт доступен только мастеру", 403)


async def load_job(connection: AsyncConnection, actor: Participant, job_id: UUID) -> ImportJob:
    await require_gm(connection, actor)
    row = (
        (
            await connection.execute(
                text("""
        select id,status,version,expires_at,draftset,card_ids from app.import_jobs
        where id=:id and room_id=:room and campaign_id=:campaign and creator_participant_id=:actor
        for update
    """),
                {
                    "id": job_id,
                    "room": actor.room_id,
                    "campaign": actor.campaign_id,
                    "actor": actor.id,
                },
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise SceneFailure("import_unavailable", "Черновик недоступен", 404)
    return ImportJob.model_validate(dict(row))


async def ensure_draft(connection: AsyncConnection, job: ImportJob, expected: int) -> None:
    expired = await connection.scalar(
        text("select expires_at<=now() from app.import_jobs where id=:id"), {"id": job.id}
    )
    if job.status != "draft" or expired:
        raise SceneFailure("import_closed", "Импорт завершён, отменён или срок истёк", 409)
    if job.version != expected:
        raise SceneFailure(
            "stale_import", "Черновик изменился. Обновите импорт перед сохранением", 409
        )


def check_size(draftset: DraftSet) -> None:
    included = [draft for draft in draftset.drafts if draft.included]
    count = sum(draft.count for draft in included)
    if (
        count > MAX_INSTANCES
        or sum(len(d.card.model_dump_json().encode()) * d.count for d in included) > 5 * 1024 * 1024
    ):
        raise SceneFailure("import_limit", "Не более 200 экземпляров и 5 МБ итоговых карточек", 422)


class ImportService:
    def __init__(self, repository: SceneRepository):
        self.repository = repository

    async def expire(self) -> None:
        async with self.repository.engine.begin() as connection:
            await connection.execute(
                text("""
                update app.import_jobs set status='expired',source_bytes=null,version=version+1,
                    draftset=jsonb_set(draftset,'{fragments}','[]'::jsonb)
                where status='draft' and expires_at<=now()
            """)
            )

    async def authorize(self, actor: Participant) -> None:
        async with self.repository.engine.begin() as connection:
            await require_gm(connection, actor)

    async def list_jobs(self, actor: Participant) -> list[ImportJob]:
        await self.expire()
        async with self.repository.engine.begin() as connection:
            await require_gm(connection, actor)
            rows = (
                (
                    await connection.execute(
                        text("""
                select id,status,version,expires_at,draftset,card_ids from app.import_jobs
                where room_id=:room and creator_participant_id=:actor and status='draft'
                order by created_at desc limit 10
            """),
                        {"room": actor.room_id, "actor": actor.id},
                    )
                )
                .mappings()
                .all()
            )
            return [ImportJob.model_validate(dict(row)) for row in rows]

    async def get(self, actor: Participant, job_id: UUID) -> ImportJob:
        await self.expire()
        async with self.repository.engine.begin() as connection:
            return await load_job(connection, actor, job_id)

    async def upload(
        self, actor: Participant, source: bytes, draftset: DraftSet, mode: str | None
    ) -> ImportJob:
        await self.expire()
        check_size(draftset)
        digest = hashlib.sha256(source).hexdigest()
        async with self.repository.engine.begin() as connection:
            await require_gm(connection, actor)
            # Serialize uploads for this authority; hashes are never global across users.
            await connection.execute(
                text("select id from app.rooms where id=:room for update"), {"room": actor.room_id}
            )
            duplicate = (
                (
                    await connection.execute(
                        text("""
                select id,status from app.import_jobs
                where room_id=:room and creator_participant_id=:actor
                and source_hash=:hash order by created_at desc limit 1 for update
            """),
                        {"room": actor.room_id, "actor": actor.id, "hash": digest},
                    )
                )
                .mappings()
                .first()
            )
            if duplicate and mode is None:
                raise SceneFailure(
                    "duplicate_file",
                    "Файл уже загружен. Выберите: обновить черновики или создать новые экземпляры",
                    409,
                )
            if mode == "update_drafts":
                if duplicate is None or duplicate["status"] != "draft":
                    raise SceneFailure(
                        "import_closed",
                        "Нет открытого импорта этого файла. Выберите новые экземпляры",
                        409,
                    )
                previous = await load_job(connection, actor, duplicate["id"])
                by_key = {d.external_key: d for d in previous.draftset.drafts}
                for draft in draftset.drafts:
                    if draft.external_key in by_key:
                        old = by_key[draft.external_key]
                        draft.count, draft.included, draft.create_token = (
                            old.count,
                            old.included,
                            old.create_token,
                        )
                check_size(draftset)
                await connection.execute(
                    text("""
                    update app.import_jobs set draftset=cast(:data as jsonb),version=version+1
                    where id=:id
                """),
                    {"id": previous.id, "data": draftset.model_dump_json()},
                )
                return await load_job(connection, actor, previous.id)
            count = await connection.scalar(
                text(
                    "select count(*) from app.import_jobs where room_id=:room "
                    "and creator_participant_id=:actor and status='draft'"
                ),
                {"room": actor.room_id, "actor": actor.id},
            )
            if int(count or 0) >= 10:
                raise SceneFailure(
                    "import_limit", "Закройте лишние импорты: не более 10 открытых черновиков", 409
                )
            identifier = uuid4()
            await connection.execute(
                text("""
                insert into app.import_jobs(id,campaign_id,room_id,creator_participant_id,
                    source_hash,source_bytes,draftset)
                values(:id,:campaign,:room,:actor,:hash,:source,cast(:data as jsonb))
            """),
                {
                    "id": identifier,
                    "campaign": actor.campaign_id,
                    "room": actor.room_id,
                    "actor": actor.id,
                    "hash": digest,
                    "source": source,
                    "data": draftset.model_dump_json(),
                },
            )
            return await load_job(connection, actor, identifier)

    async def edit(self, actor: Participant, job_id: UUID, request: EditJob) -> ImportJob:
        await self.expire()
        async with self.repository.engine.begin() as connection:
            job = await load_job(connection, actor, job_id)
            await ensure_draft(connection, job, request.expected_version)
            old = {draft.external_key: draft for draft in job.draftset.drafts}
            if len(request.drafts) != len(old) or {d.external_key for d in request.drafts} != set(
                old
            ):
                raise SceneFailure(
                    "invalid_drafts",
                    "Состав черновиков изменять нельзя; используйте исключение",
                    422,
                )
            for draft in request.drafts:
                draft.source = old[draft.external_key].source
                draft.card.external_key = draft.external_key
                await validate_references(connection, draft.card, actor)
            job.draftset.drafts = request.drafts
            check_size(job.draftset)
            await connection.execute(
                text(
                    "update app.import_jobs set draftset=cast(:data as jsonb),version=version+1 "
                    "where id=:id"
                ),
                {"id": job_id, "data": job.draftset.model_dump_json()},
            )
            return await load_job(connection, actor, job_id)

    async def cancel(self, actor: Participant, job_id: UUID, expected: int) -> ImportJob:
        async with self.repository.engine.begin() as connection:
            job = await load_job(connection, actor, job_id)
            if job.status == "cancelled":
                return job
            await ensure_draft(connection, job, expected)
            await connection.execute(
                text(
                    "update app.import_jobs set status='cancelled',source_bytes=null,"
                    "draftset=jsonb_set(draftset,'{fragments}','[]'::jsonb),"
                    "version=version+1 "
                    "where id=:id"
                ),
                {"id": job_id},
            )
            return await load_job(connection, actor, job_id)


async def apply_import_command(
    connection: AsyncConnection, actor: Participant, payload: dict[str, Any], room: dict[str, Any]
) -> dict[str, Any]:
    request = ConfirmImport.model_validate(payload)
    job = await load_job(connection, actor, request.job_id)
    await ensure_draft(connection, job, request.expected_job_version)
    check_size(job.draftset)
    drafts = [d for d in job.draftset.drafts if d.included]
    if not drafts:
        raise SceneFailure("empty_import", "Выберите хотя бы одну карточку")
    scene = None
    if any(d.create_token for d in drafts):
        scene = (
            (
                await connection.execute(
                    text(
                        "select id,grid_size from app.scenes where id=:id "
                        "and campaign_id=:campaign and deleted_at is null for update"
                    ),
                    {"id": room["active_scene_id"], "campaign": actor.campaign_id},
                )
            )
            .mappings()
            .first()
        )
        if scene is None:
            raise SceneFailure("scene_unavailable", "Для токенов нужна активная сцена")
    cards: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for draft in drafts:
        for _ in range(draft.count):
            data = draft.card.model_copy(deep=True)
            for entry in data.inventory:
                entry.id = uuid4()
            for ability in data.abilities:
                ability.id = uuid4()
            result = await apply_card_command(
                connection, actor, "card.create", {"card": data.model_dump(mode="json")}
            )
            cards.append(result["card"])
            if draft.create_token and scene is not None:
                token = CreateItem(
                    name=data.name,
                    card_id=UUID(result["card_id"]),
                    asset_id=data.image_asset_id,
                    owner_participant_id=data.owner_participant_id,
                    visibility=data.visibility,
                    width=scene["grid_size"],
                    height=scene["grid_size"],
                    x=len(items) % 10 * scene["grid_size"],
                    y=len(items) // 10 * scene["grid_size"],
                )
                identifier = uuid4()
                values = token.model_dump()
                values.update(
                    id=identifier,
                    scene_id=scene["id"],
                    campaign_id=actor.campaign_id,
                    created_by=actor.user_id,
                    created_by_participant_id=actor.id,
                )
                columns = ",".join(values)
                params = ",".join(f":{key}" for key in values)
                await connection.execute(
                    text(f"insert into app.scene_items({columns}) values({params})"), values
                )
                items.append(
                    SceneItem.model_validate(values).model_dump(
                        mode="json", exclude={"can_transform"}
                    )
                )
    ids = [UUID(card["id"]) for card in cards]
    await connection.execute(
        text("""
        update app.import_jobs set status='confirmed',source_bytes=null,version=version+1,
            draftset=jsonb_set(draftset,'{fragments}','[]'::jsonb),card_ids=:ids where id=:id
    """),
        {"id": job.id, "ids": ids},
    )
    return {
        "job_id": str(job.id),
        "card_ids": [str(id) for id in ids],
        "cards": cards,
        "items": items,
    }


async def cleanup_loop(service: ImportService) -> None:
    while True:
        try:
            await service.expire()
        except Exception:
            logging.getLogger(__name__).warning("Import expiration temporarily unavailable")
        await asyncio.sleep(60)
