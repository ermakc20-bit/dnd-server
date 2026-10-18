from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.assets.storage import PrivateStorage, StorageUnavailable
from app.campaign_transfer.archive import asset_bytes, build_archive, encode, validate_documents
from app.campaign_transfer.bounded import validate_bounded
from app.campaign_transfer.models import (
    MAX_EXPANDED,
    TERMINAL,
    TransferFailure,
    TransferJob,
)
from app.campaign_transfer.state import (
    authorize_export,
    read_campaign,
    remap,
    restore_campaign,
    rows,
)


class TransferService:
    def __init__(self, engine: AsyncEngine, storage: PrivateStorage):
        self.engine, self.storage = engine, storage
        self.tasks: dict[UUID, asyncio.Task[None]] = {}

    @staticmethod
    def dto(row: dict[str, Any]) -> TransferJob:
        return TransferJob.model_validate(
            {
                **row,
                "archive_available": row["kind"] == "export"
                and row["phase"] == "completed"
                and row.get("archive_size", 0) > 0,
            }
        )

    async def get_job(self, user: UUID, job: UUID) -> TransferJob:
        async with self.engine.begin() as connection:
            found = await rows(
                connection,
                """
select id,owner_user_id,kind,phase,progress,cancel_requested,
result_campaign_id,error_code,expires_at,
case when expires_at>now() then coalesce(octet_length(archive),0) else 0 end as
archive_size
from app.campaign_transfer_jobs where id=:job and owner_user_id=:user
""",
                job=job,
                user=user,
            )
            if not found:
                raise TransferFailure("forbidden", "Задание недоступно", 403)
            return self.dto(found[0])

    async def begin(
        self, user: UUID, job: UUID, kind: str, options: dict[str, Any]
    ) -> tuple[TransferJob, bool]:
        async with self.engine.begin() as connection:
            await connection.execute(text("select pg_advisory_xact_lock(840080)"))
            existing = await rows(
                connection,
                "select * from app.campaign_transfer_jobs where id=:job for update",
                job=job,
            )
            if existing:
                found = existing[0]
                if found["owner_user_id"] != user:
                    raise TransferFailure("forbidden", "Задание недоступно", 403)
                if found["kind"] != kind or (kind == "export" and found["options"] != options):
                    raise TransferFailure(
                        "request_conflict", "ID уже использован для другого задания", 409
                    )
                return self.dto({**found, "archive_size": len(found["archive"] or b"")}), False
            if not await connection.scalar(
                text("select user_id from app.profiles where user_id=:user"), {"user": user}
            ):
                raise TransferFailure("forbidden", "Требуется аккаунт мастера", 403)
            active = await connection.scalar(
                text("""
select count(*) from app.campaign_transfer_jobs
where phase not in ('completed','failed','cancelled','expired')
""")
            )
            if int(active or 0) >= 2:
                raise TransferFailure(
                    "transfer_busy", "Уже выполняются два переноса. Повторите позже", 429
                )
            campaign = UUID(options["campaign_id"]) if kind == "export" else None
            if campaign:
                await authorize_export(connection, user, campaign)
            await connection.execute(
                text("""
insert into app.campaign_transfer_jobs(id,owner_user_id,kind,
source_campaign_id,options,lease_id,lease_expires_at)
values(:job,:user,:kind,:campaign,cast(:options as jsonb),:lease,now()+interval
'1 hour')
"""),
                {
                    "job": job,
                    "user": user,
                    "kind": kind,
                    "campaign": campaign,
                    "options": encode(options).decode(),
                    "lease": uuid4(),
                },
            )
        return await self.get_job(user, job), True

    async def start(self, user: UUID, job: UUID, archive: bytes | None = None) -> TransferJob:
        async with self.engine.begin() as connection:
            record = (
                await rows(
                    connection,
                    "select * from app.campaign_transfer_jobs "
                    "where id=:job and owner_user_id=:user for update",
                    job=job,
                    user=user,
                )
            )[0]
            if record["cancel_requested"] or record["phase"] in TERMINAL:
                return self.dto(record)
            await connection.execute(
                text("""
update app.campaign_transfer_jobs set archive=:archive,
phase=:phase,updated_at=now(),lease_expires_at=now()+interval '120 seconds'
where id=:job
"""),
                {
                    "job": job,
                    "archive": archive,
                    "phase": "building" if record["kind"] == "export" else "validating",
                },
            )
        task = asyncio.create_task(self.run_job(user, job))
        self.tasks[job] = task
        task.add_done_callback(lambda _task: self.tasks.pop(job, None))
        return await self.get_job(user, job)

    async def checkpoint(self, job: UUID, phase: str, progress: int) -> None:
        async with self.engine.begin() as connection:
            records = await rows(
                connection,
                "select cancel_requested,phase,lease_expires_at>now() as alive "
                "from app.campaign_transfer_jobs where id=:job for update",
                job=job,
            )
            if not records or records[0]["cancel_requested"]:
                raise TransferFailure("cancelled", "Перенос отменён")
            if not records[0]["alive"] or records[0]["phase"] in TERMINAL:
                raise TransferFailure("interrupted")
            await connection.execute(
                text("""
update app.campaign_transfer_jobs set phase=:phase,progress=:progress,
updated_at=now(),lease_expires_at=now()+interval '120 seconds' where id=:job
"""),
                {"job": job, "phase": phase, "progress": progress},
            )

    async def run_job(self, user: UUID, job: UUID) -> None:
        # A live worker retains this session lock through any provider write. Recovery
        # cannot discard its reserved keys while that write may still complete.
        async with self.engine.connect() as connection:
            key = job.int % (2**63)
            acquired = await connection.scalar(
                text("select pg_try_advisory_lock(:key)"), {"key": key}
            )
            if not acquired:
                return
            try:
                await self._run_job(user, job)
            finally:
                await connection.execute(text("select pg_advisory_unlock(:key)"), {"key": key})

    async def _run_job(self, user: UUID, job: UUID) -> None:
        try:
            async with self.engine.begin() as connection:
                record = (
                    await rows(
                        connection,
                        "select * from app.campaign_transfer_jobs where id=:job",
                        job=job,
                    )
                )[0]
            if record["kind"] == "export":
                await self.export_campaign(user, job, record)
            else:
                await self.import_campaign(user, job, record["archive"])
        except TransferFailure as error:
            await self.fail_job(job, error.code)
        except StorageUnavailable:
            await self.fail_job(job, "asset_unavailable", defer_cleanup=True)
        except asyncio.CancelledError:
            await asyncio.shield(self.fail_job(job, "interrupted", defer_cleanup=True))
        except Exception:
            # SQL/provider exceptions and user content never become API messages/logs.
            await self.fail_job(job, "transfer_failed")

    async def export_campaign(self, user: UUID, job: UUID, record: dict[str, Any]) -> None:
        await self.checkpoint(job, "building", 10)
        async with self.engine.connect() as raw:
            connection = await raw.execution_options(isolation_level="REPEATABLE READ")
            async with connection.begin():
                documents, keys = await read_campaign(
                    connection, user, record["source_campaign_id"], record["options"]
                )
        validate_documents(documents)
        data = {}
        total = 0
        for index, asset in enumerate(documents["assets.json"]):
            await self.checkpoint(job, "building", 10 + int(70 * index / max(1, len(keys))))
            body = await self.storage.get(keys[asset["path"]], asset["byte_size"])
            total += len(body)
            if total > MAX_EXPANDED:
                raise TransferFailure("archive_limit")
            data[asset["path"]] = body
        archive = await asyncio.to_thread(build_archive, documents, data)
        await self.checkpoint(job, "committing", 95)
        async with self.engine.begin() as connection:
            await self.check_final(connection, job)
            await authorize_export(connection, user, record["source_campaign_id"])
            await connection.execute(
                text("""
update app.campaign_transfer_jobs set phase='completed',progress=100,
archive=:archive,lease_id=null,lease_expires_at=null,updated_at=now() where id=:job
"""),
                {"job": job, "archive": archive},
            )

    async def check_final(self, connection: Any, job: UUID) -> None:
        record = (
            await rows(
                connection,
                "select cancel_requested,phase,lease_expires_at>now() as alive "
                "from app.campaign_transfer_jobs where id=:job for update",
                job=job,
            )
        )[0]
        if record["cancel_requested"]:
            raise TransferFailure("cancelled")
        if record["phase"] in TERMINAL or not record["alive"]:
            raise TransferFailure("interrupted")

    async def import_campaign(self, user: UUID, job: UUID, archive: bytes) -> None:
        documents = await validate_bounded(archive)
        await self.checkpoint(job, "storing", 30)
        ids = remap(documents)
        campaign = uuid4()
        keys = [f"{campaign}/{ids[a['ref']]}" for a in documents["assets.json"]]
        async with self.engine.begin() as connection:
            await self.check_final(connection, job)
            await connection.execute(
                text(
                    "update app.campaign_transfer_jobs set reserved_blob_keys=cast(:keys as jsonb) "
                    "where id=:job"
                ),
                {"job": job, "keys": json.dumps(keys)},
            )
        for index, asset in enumerate(documents["assets.json"]):
            await self.checkpoint(job, "storing", 30 + int(60 * index / max(1, len(keys))))
            await self.storage.put(
                keys[index],
                await asyncio.to_thread(asset_bytes, archive, asset["path"]),
                asset["content_type"],
            )
        await self.checkpoint(job, "committing", 95)
        async with self.engine.begin() as connection:
            await self.check_final(connection, job)
            await restore_campaign(connection, user, campaign, documents, ids)
            await connection.execute(
                text("""
update app.campaign_transfer_jobs set phase='completed',progress=100,
result_campaign_id=:campaign,archive=null,reserved_blob_keys='[]',lease_id=null,
lease_expires_at=null,updated_at=now() where id=:job
"""),
                {"job": job, "campaign": campaign},
            )

    async def fail_job(self, job: UUID, code: str, *, defer_cleanup: bool = False) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                text("""
update app.campaign_transfer_jobs set phase='cleanup_pending',
terminal_phase=:terminal,error_code=:code,archive=null,lease_id=null,
lease_expires_at=case when :defer and jsonb_array_length(reserved_blob_keys)>0
then now()+interval '120 seconds' else null end,
updated_at=now() where id=:job and phase not in
('completed','failed','cancelled','expired','cleanup_pending')
"""),
                {
                    "job": job,
                    "defer": defer_cleanup,
                    "code": code,
                    "terminal": "cancelled"
                    if code == "cancelled"
                    else "expired"
                    if code == "expired"
                    else "failed",
                },
            )
        await self.cleanup(job)

    async def cleanup(self, job: UUID) -> None:
        # Locked cleanup serializes maintenance/cancel/recovery and never touches completed assets.
        async with self.engine.begin() as connection:
            records = await rows(
                connection,
                """
select * from app.campaign_transfer_jobs where id=:job and phase='cleanup_pending'
and (lease_expires_at is null or lease_expires_at<=now()) for update
""",
                job=job,
            )
            if not records:
                return
            record = records[0]
            remaining = []
            for key in record["reserved_blob_keys"]:
                try:
                    await self.storage.delete(key)
                except StorageUnavailable:
                    remaining.append(key)
            await connection.execute(
                text("""
update app.campaign_transfer_jobs set reserved_blob_keys=cast(:keys as jsonb),
phase=:phase,updated_at=now() where id=:job
"""),
                {
                    "job": job,
                    "keys": json.dumps(remaining),
                    "phase": "cleanup_pending" if remaining else record["terminal_phase"],
                },
            )

    async def cancel(self, user: UUID, job: UUID) -> TransferJob:
        await self.get_job(user, job)
        async with self.engine.begin() as connection:
            await connection.execute(
                text("""
update app.campaign_transfer_jobs set cancel_requested=true,
updated_at=now() where id=:job and owner_user_id=:user and phase not in
('completed','failed','cancelled','expired','cleanup_pending')
"""),
                {"job": job, "user": user},
            )
        state = await self.get_job(user, job)
        if state.phase == "receiving":
            await self.fail_job(job, "cancelled")
        return await self.get_job(user, job)

    async def download(self, user: UUID, job: UUID) -> bytes:
        async with self.engine.begin() as connection:
            records = await rows(
                connection,
                """
select * from app.campaign_transfer_jobs where id=:job
and owner_user_id=:user and kind='export' and phase='completed' and expires_at>now()
""",
                job=job,
                user=user,
            )
            if (
                not records
                or records[0]["archive"] is None
                or records[0]["source_campaign_id"] is None
            ):
                raise TransferFailure(
                    "archive_unavailable", "Архив недоступен или срок хранения истёк", 410
                )
            await authorize_export(connection, user, records[0]["source_campaign_id"])
            return bytes(records[0]["archive"])

    async def maintain(self) -> None:
        async with self.engine.begin() as connection:
            stale = await rows(
                connection,
                """
select id,expires_at<=now() as expired from app.campaign_transfer_jobs
where phase not in ('completed','failed','cancelled','expired','cleanup_pending')
and (expires_at<=now() or lease_expires_at<=now())
""",
            )
            await connection.execute(
                text(
                    "update app.campaign_transfer_jobs set archive=null where expires_at<=now() "
                    "and kind='export' and phase='completed'"
                )
            )
        for record in stale:
            async with self.engine.begin() as connection:
                acquired = await connection.scalar(
                    text("select pg_try_advisory_xact_lock(:key)"),
                    {"key": record["id"].int % (2**63)},
                )
                if acquired:
                    await self.fail_job(
                        record["id"], "expired" if record["expired"] else "interrupted"
                    )
        async with self.engine.begin() as connection:
            pending = await rows(
                connection,
                "select id from app.campaign_transfer_jobs where phase='cleanup_pending'",
            )
        for record in pending:
            await self.cleanup(record["id"])

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def maintenance_loop(service: TransferService) -> None:
    while True:
        with suppress(Exception):
            await service.maintain()
        await asyncio.sleep(60)
