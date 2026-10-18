import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest_asyncio
from app.assets.dependencies import get_asset_service
from app.assets.service import AssetService
from app.assets.storage import MemoryStorage
from app.auth.dependencies import get_current_identity
from app.auth.jwt import AuthIdentity
from app.campaign_transfer.router import get_transfer_service
from app.campaign_transfer.service import TransferService

spec = importlib.util.spec_from_file_location(
    "transfer_shared_fixture", Path(__file__).parents[1] / "cards" / "conftest.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
table = module.table


@pytest_asyncio.fixture
async def transfer(table):
    application = table.client._transport.app
    application.dependency_overrides[get_current_identity] = lambda: AuthIdentity(
        user_id=table.gm.user_id,
        email="transfer@example.invalid",
        audience="authenticated",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    table.application = application
    table.storage = MemoryStorage()
    table.transfer_service = TransferService(table.service.repository.engine, table.storage)
    application.dependency_overrides[get_transfer_service] = lambda: table.transfer_service
    table.asset_service = AssetService(
        table.service.repository.engine.url.render_as_string(hide_password=False), table.storage
    )
    application.dependency_overrides[get_asset_service] = lambda: table.asset_service
    try:
        yield table
    finally:
        await table.transfer_service.close()
        await table.asset_service.engine.dispose()
        await table.connection.execute(
            "delete from app.campaign_transfer_jobs where owner_user_id=$1", table.gm.user_id
        )
        await table.connection.execute(
            "delete from app.campaigns where owner_user_id=$1 and id<>$2",
            table.gm.user_id,
            table.campaign,
        )
