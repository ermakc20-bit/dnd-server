from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.me import router as me_router
from app.assets.dependencies import build_asset_service
from app.assets.router import router as assets_router
from app.campaign_transfer.router import build_transfer_service
from app.campaign_transfer.router import router as transfer_router
from app.campaign_transfer.service import maintenance_loop
from app.campaigns.router import router as campaigns_router
from app.card_import.router import router as import_router
from app.card_import.service import ImportService, cleanup_loop
from app.cards.router import router as cards_router
from app.config import Settings, get_settings
from app.dice_log.router import router as journal_router
from app.identity.logging import configure_access_log_redaction
from app.realtime.router import router as realtime_router
from app.realtime.service import Realtime
from app.scenes.dependencies import build_scene_service
from app.scenes.router import router as scenes_router
from app.system_packages.router import router as packages_router


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_access_log_redaction()
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.realtime = Realtime(
            str(resolved.redis_url) if resolved.redis_url else None
        )
        cleanup = (
            asyncio.create_task(
                cleanup_loop(ImportService(build_scene_service(resolved.database_url).repository))
            )
            if resolved.database_url
            else None
        )
        transfer = (
            build_transfer_service(
                build_asset_service(
                    resolved.database_url,
                    str(resolved.supabase_url) if resolved.supabase_url else None,
                    resolved.supabase_service_role_key.get_secret_value()
                    if resolved.supabase_service_role_key
                    else None,
                )
            )
            if resolved.database_url
            else None
        )
        transfer_cleanup = asyncio.create_task(maintenance_loop(transfer)) if transfer else None
        try:
            yield
        finally:
            if transfer_cleanup:
                transfer_cleanup.cancel()
                with suppress(asyncio.CancelledError):
                    await transfer_cleanup
            if transfer:
                await transfer.close()
            if cleanup:
                cleanup.cancel()
                with suppress(asyncio.CancelledError):
                    await cleanup
            await application.state.realtime.close()

    application = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        docs_url="/docs" if resolved.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    application.include_router(health_router)
    application.include_router(me_router)
    application.include_router(campaigns_router)
    application.include_router(scenes_router)
    application.include_router(assets_router)
    application.include_router(packages_router)
    application.include_router(cards_router)
    application.include_router(realtime_router)
    application.include_router(import_router)
    application.include_router(transfer_router)
    application.include_router(journal_router)
    return application


app = create_app()
