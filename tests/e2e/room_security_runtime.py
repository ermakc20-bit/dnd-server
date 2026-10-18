"""Owned F3 fixture; existing real JWT/JWKS, Storage and native application primitives."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import asyncpg
import jwt
import runtime as existing
from fastapi import FastAPI
from PIL import Image

app = existing.app


@asynccontextmanager
async def lifespan(application: FastAPI):
    connection = await asyncpg.connect(existing.DB)
    user = uuid4()
    owned_campaigns = []
    owned_actors = []
    # Persist exact fixture ownership before the first SQL write; no token values.
    (existing.OUTPUT / "fixture-ownership.json").write_text(json.dumps({"user_id": str(user)}))
    try:
        now = datetime.now(UTC)
        existing.fixture["token"] = jwt.encode(
            {
                "sub": str(user),
                "email": "fixture@example.invalid",
                "iss": existing.ISSUER,
                "aud": "authenticated",
                "iat": now,
                "exp": now + timedelta(hours=2),
            },
            existing.KEY,
            algorithm="RS256",
            headers={"kid": "local-acceptance"},
        )
        await connection.execute(
            "insert into auth.users(id,email) values($1,$2)",
            user,
            f"f3-native-{user}@example.invalid",
        )
        image = BytesIO()
        Image.new("RGB", (512, 512), (34, 54, 65)).save(image, format="PNG")
        (existing.OUTPUT / "ready-map.png").write_bytes(image.getvalue())
        async with existing.prior(application):
            yield
    finally:
        # Every foreign key scope comes from the one predeclared synthetic identity.
        owned_campaigns = await connection.fetch(
            "select id from app.campaigns where owner_user_id=$1", user
        )
        owned_rooms = await connection.fetch(
            "select r.id from app.rooms r join app.campaigns c on c.id=r.campaign_id "
            "where c.owner_user_id=$1",
            user,
        )
        owned_actors = await connection.fetch(
            "select id from app.participants where campaign_id in "
            "(select id from app.campaigns where owner_user_id=$1)",
            user,
        )
        await existing.build_transfer_service(existing.assets).close()
        await existing.service.repository.engine.dispose()
        await existing.repository._engine.dispose()
        await existing.assets.engine.dispose()
        await existing.build_scene_service(existing.DB).repository.engine.dispose()
        from redis.asyncio import Redis

        redis = Redis.from_url(existing.REDIS, decode_responses=True)
        try:
            for room in owned_rooms:
                for prefix in ("vtt:presence:", "vtt:preview:"):
                    keys = [key async for key in redis.scan_iter(f"{prefix}{room['id']}:*")]
                    if keys:
                        await redis.delete(*keys)
            for actor in owned_actors:
                await redis.delete(
                    f"vtt:rate:{actor['id']}:tickets", f"vtt:rate:{actor['id']}:frames"
                )
        finally:
            await redis.aclose()
        await connection.execute(
            "delete from app.campaign_transfer_jobs where owner_user_id=$1", user
        )
        await connection.execute("delete from app.campaigns where owner_user_id=$1", user)
        await connection.execute("delete from auth.users where id=$1", user)
        counts = {
            "fixture_users_remaining": await connection.fetchval(
                "select count(*) from auth.users where id=$1", user
            ),
            "fixture_campaigns_remaining": await connection.fetchval(
                "select count(*) from app.campaigns where owner_user_id=$1", user
            ),
            "fixture_jobs_remaining": await connection.fetchval(
                "select count(*) from app.campaign_transfer_jobs where owner_user_id=$1", user
            ),
            "fixture_security_events_remaining": await connection.fetchval(
                "select count(*) from app.room_security_events where room_id=any($1)",
                [row["id"] for row in owned_rooms],
            ),
            "exact_owned_campaign_ids": [str(row["id"]) for row in owned_campaigns],
            "exact_owned_user_id": str(user),
        }
        (existing.OUTPUT / "cleanup.json").write_text(json.dumps(counts))
        await connection.close()


app.router.lifespan_context = lifespan
