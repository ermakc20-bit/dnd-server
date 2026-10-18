import asyncio
from io import BytesIO
from uuid import uuid4

from app.assets.storage import StorageUnavailable
from app.campaign_transfer.service import TransferService
from PIL import Image

from .test_transfer import export_bytes, terminal


async def test_accepted_cancel_cannot_turn_failed_after_interrupted_upload(transfer):
    archive = await export_bytes(transfer)
    entered = asyncio.Event()
    release = asyncio.Event()
    job = uuid4()

    async def body():
        yield archive[:100]
        entered.set()
        await release.wait()
        raise RuntimeError("synthetic interrupted upload")

    upload = asyncio.create_task(
        transfer.client.put(
            f"/api/v1/campaign-transfers/{job}/import",
            content=body(),
            headers={"Content-Type": "application/zip"},
        )
    )
    await asyncio.wait_for(entered.wait(), 2)
    cancelled = await transfer.client.delete(f"/api/v1/campaign-transfers/{job}")
    assert cancelled.status_code == 200 and cancelled.json()["phase"] == "cancelled"
    release.set()
    await asyncio.gather(upload, return_exceptions=True)
    state = await terminal(transfer.client, job)
    assert state["phase"] == "cancelled", state
    assert (
        await transfer.connection.fetchval(
            "select count(*) from app.campaigns where owner_user_id=$1", transfer.gm.user_id
        )
        == 1
    )


async def test_cancel_live_put_and_failed_delete_recovery_never_loses_new_keys(transfer):
    image = BytesIO()
    Image.new("RGB", (2, 2)).save(image, format="PNG")
    prepared = await transfer.client.post(
        transfer.url + "/assets/prepare",
        json={
            "name": "Image",
            "content_type": "image/png",
            "byte_size": len(image.getvalue()),
            "kind": "map",
        },
    )
    assert prepared.status_code == 201
    uploaded = await transfer.client.put(
        prepared.json()["upload_url"],
        content=image.getvalue(),
        headers={"Content-Type": "image/png"},
    )
    assert uploaded.status_code == 200
    source_keys = set(transfer.storage.objects)
    archive = await export_bytes(transfer)
    entered, release = asyncio.Event(), asyncio.Event()
    original_put, original_delete = transfer.storage.put, transfer.storage.delete
    delete_failed = [True]

    async def blocked_put(key, data, mime):
        entered.set()
        await release.wait()
        await original_put(key, data, mime)

    async def failed_delete(key):
        if delete_failed[0]:
            raise StorageUnavailable
        await original_delete(key)

    transfer.storage.put = blocked_put
    transfer.storage.delete = failed_delete
    job = uuid4()
    response = await transfer.client.put(
        f"/api/v1/campaign-transfers/{job}/import",
        content=archive,
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 202
    await asyncio.wait_for(entered.wait(), 3)
    cancelled = await transfer.client.delete(f"/api/v1/campaign-transfers/{job}")
    assert cancelled.status_code == 200 and cancelled.json()["cancel_requested"]
    await transfer.connection.execute(
        "update app.campaign_transfer_jobs set lease_expires_at=now()-interval '1 second' "
        "where id=$1",
        job,
    )
    restarter = TransferService(transfer.service.repository.engine, transfer.storage)
    await restarter.maintain()
    release.set()
    state = await terminal(transfer.client, job)
    assert state["phase"] == "cleanup_pending", state
    keys = await transfer.connection.fetchval(
        "select reserved_blob_keys::text from app.campaign_transfer_jobs where id=$1", job
    )
    import json

    assert len(json.loads(keys)) == 1
    delete_failed[0] = False
    await restarter.maintain()
    state = await terminal(transfer.client, job)
    assert state["phase"] == "cancelled", state
    assert set(transfer.storage.objects) == source_keys
    assert (
        await transfer.connection.fetchval(
            "select count(*) from app.campaigns where owner_user_id=$1", transfer.gm.user_id
        )
        == 1
    )
