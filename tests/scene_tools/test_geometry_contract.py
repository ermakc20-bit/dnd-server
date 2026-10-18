import os
from uuid import uuid4

import pytest
from app.assets.dependencies import get_asset_service
from app.assets.service import AssetService
from app.assets.storage import MemoryStorage
from app.events.projection import synchronize


async def asset_fixture(table):
    identifier = uuid4()
    key = str(identifier)
    storage = MemoryStorage()
    await storage.put(key, b"isolated test image", "image/png")
    service = AssetService(os.environ["VTT_TEST_DATABASE_URL"], storage)
    table.app.dependency_overrides[get_asset_service] = lambda: service
    await table.connection.execute(
        """insert into app.assets(id,owner_user_id,campaign_id,uploaded_by,name,kind,
          object_key,content_type,byte_size,status)
        values($1,$2,$3,$4,'Geometry token','image',$5,'image/png',19,'ready')""",
        identifier,
        table.gm.user_id,
        table.campaign,
        table.gm.id,
        key,
    )
    return identifier, service


@pytest.mark.asyncio
async def test_vertex_and_collinear_fog_exits_deny_footprint_path_and_asset(table):
    await table.execute("scene.create", {"name": "Boundary privacy"})
    await table.execute("scene.grid", {"snap_enabled": False})
    asset, service = await asset_fixture(table)
    try:
        _, created = await table.execute(
            "item.create",
            {
                "name": "Covered footprint",
                "x": 0,
                "y": 0,
                "width": 64,
                "height": 64,
                "asset_id": str(asset),
                "owner_participant_id": str(table.player.id),
            },
        )
        assert created.status == "accepted"
        await table.execute(
            "item.create",
            {
                "name": "Visible control",
                "x": -24,
                "y": -24,
                "width": 8,
                "height": 8,
            },
        )
        _, filled = await table.execute("fog.fill", {})
        assert filled.status == "accepted"
        polygon = [
            (-32, -32),
            (96, -32),
            (96, 96),
            (64, 96),
            (64, 0),
            (32, 32),
            (0, 0),
            (0, 96),
            (-32, 96),
        ]
        _, revealed = await table.execute(
            "fog.reveal",
            {
                "points": [{"x": x, "y": y} for x, y in polygon],
            },
        )
        assert revealed.status == "accepted"
        for kind, points, label in [
            ("line", [{"x": 0, "y": 64}, {"x": 64, "y": 64}], "Covered line"),
            ("arrow", [{"x": 0, "y": 96}, {"x": 64, "y": 96}], "Covered arrow"),
            ("label", [{"x": 32, "y": 48}], "Covered point"),
            ("label", [{"x": -16, "y": 32}], "Visible point"),
        ]:
            _, mark = await table.execute(
                "annotation.create",
                {
                    "kind": kind,
                    "points": points,
                    "label": label,
                },
            )
            assert mark.status == "accepted"
        table.actor = table.player
        scene = await table.client.get(table.url + "/scene")
        assert scene.status_code == 200
        projection = scene.json()
        assert [item["name"] for item in projection["items"]] == ["Visible control"]
        assert [mark["label"] for mark in projection["annotations"]] == ["Visible point"]
        grant = await table.client.get(table.url + f"/assets/{asset}/download")
        assert grant.status_code == 403
        sync = await synchronize(table.service.repository, table.player, 0)
        assert [item["name"] for item in sync["snapshot"]["items"]] == ["Visible control"]
        assert "Covered" not in str(sync)
        journal = await table.client.get(table.url + "/journal")
        assert journal.status_code == 200 and "Covered" not in journal.text
    finally:
        await service.engine.dispose()


@pytest.mark.asyncio
async def test_accepted_extreme_item_geometry_keeps_public_read_paths_available(table):
    await table.execute("scene.create", {"name": "Derived geometry"})
    await table.execute("scene.grid", {"snap_enabled": False})
    asset, service = await asset_fixture(table)
    try:
        _, reset = await table.execute("fog.reset", {})
        assert reset.status == "accepted"
        for name, width, height, rotation in [
            ("Edge token", 64, 64, 0),
            ("Rotated edge token", 1000000, 1000000, 135),
        ]:
            _, created = await table.execute(
                "item.create",
                {
                    "name": name,
                    "x": 1000000,
                    "y": 0,
                    "width": width,
                    "height": height,
                    "rotation": rotation,
                    "asset_id": str(asset),
                },
            )
            assert created.status == "accepted"
        table.actor = table.player
        scene = await table.client.get(table.url + "/scene")
        assert scene.status_code == 200
        assert [item["name"] for item in scene.json()["items"]] == [
            "Edge token",
            "Rotated edge token",
        ]
        assert (await table.client.get(table.url + "/journal")).status_code == 200
        sync = await synchronize(table.service.repository, table.player, 0)
        assert len(sync["snapshot"]["items"]) == 2
        assert (await table.client.get(table.url + f"/assets/{asset}/download")).status_code == 200
        table.actor = table.gm
        await table.execute("fog.fill", {})
        _, reveal = await table.execute(
            "fog.reveal",
            {
                "points": [
                    {"x": 999936, "y": -64},
                    {"x": 1000000, "y": -64},
                    {"x": 1000000, "y": 128},
                    {"x": 999936, "y": 128},
                ]
            },
        )
        assert reveal.status == "accepted"
        table.actor = table.player
        scene = await table.client.get(table.url + "/scene")
        assert scene.status_code == 200 and scene.json()["items"] == []
        assert (await table.client.get(table.url + "/journal")).status_code == 200
        sync = await synchronize(table.service.repository, table.player, 0)
        assert sync["snapshot"]["items"] == []
        assert (await table.client.get(table.url + f"/assets/{asset}/download")).status_code == 403
    finally:
        await service.engine.dispose()
