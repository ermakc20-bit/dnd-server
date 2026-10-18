from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

DATABASE_URL = os.getenv("VTT_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="local PostgreSQL not configured")


@pytest.mark.asyncio
async def test_forward_migration_preserves_a_map_shared_by_foundation_rooms() -> None:
    assert DATABASE_URL is not None
    connection = await asyncpg.connect(DATABASE_URL)
    transaction = connection.transaction()
    await transaction.start()
    namespaces = {
        name: f"scene_rehearsal_{name}_{uuid4().hex}" for name in ("app", "auth", "storage")
    }

    def isolated(source: str) -> str:
        for old, new in namespaces.items():
            source = re.sub(rf"\b{old}\b", new, source)
        return source

    try:
        await connection.execute(
            isolated("""
          create schema auth; create schema storage;
          create table auth.users(id uuid primary key,email text,
            raw_user_meta_data jsonb default '{}');
          create table storage.buckets(id text primary key,name text,public boolean,
            file_size_limit bigint,
            allowed_mime_types text[]);
        """)
        )
        await connection.execute(
            isolated(
                (ROOT / "supabase/migrations/20260804123229_initial_app_schema.sql").read_text()
            )
        )
        owner, asset = uuid4(), uuid4()
        await connection.execute(
            isolated("insert into auth.users(id,email) values($1,'legacy-scene@example.invalid')"),
            owner,
        )
        rooms, scenes = [uuid4(), uuid4()], [uuid4(), uuid4()]
        await connection.execute(
            isolated("""insert into app.assets
          (id,owner_user_id,name,kind,object_key,content_type,byte_size,width,height)
          values($1,$2,'Shared map','map','original/shared-map','image/png',100,800,600)
        """),
            asset,
            owner,
        )
        for room, scene in zip(rooms, scenes, strict=True):
            await connection.execute(
                isolated("insert into app.rooms(id,owner_user_id,name) values($1,$2,'Legacy')"),
                room,
                owner,
            )
            await connection.execute(
                isolated("insert into app.scenes(id,room_id,name) values($1,$2,'Legacy scene')"),
                scene,
                room,
            )
            await connection.execute(
                isolated("""insert into app.scene_items(scene_id,created_by,asset_id,kind)
              values($1,$2,$3,'map')"""),
                scene,
                owner,
                asset,
            )
        await connection.execute(
            isolated((ROOT / "supabase/migrations/20260903174327_campaigns_guests.sql").read_text())
        )
        await connection.execute(
            isolated((ROOT / "supabase/migrations/20261011125943_scene_core.sql").read_text())
        )
        rows = await connection.fetch(
            isolated("""select i.asset_id,i.campaign_id,a.campaign_id as asset_campaign,
            a.name,a.width,a.height,a.status from app.scene_items i
            join app.assets a on a.id=i.asset_id""")
        )
        assert len(rows) == 2
        assert rows[0]["asset_id"] != rows[1]["asset_id"]
        assert all(row["campaign_id"] == row["asset_campaign"] for row in rows)
        assert all(
            row["name"] == "Shared map" and row["width"] == 800 and row["height"] == 600
            for row in rows
        )
        assert all(row["status"] == "pending" for row in rows)
    finally:
        await transaction.rollback()
        await connection.close()
