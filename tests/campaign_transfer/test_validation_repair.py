import hashlib
import json
from io import BytesIO
from zipfile import ZipFile

import pytest
from app.campaign_transfer.archive import validate_archive
from app.campaign_transfer.models import TransferFailure
from app.cards.models import CardData
from app.system_packages.service import get_schema
from PIL import Image


@pytest.fixture
def portable():
    rooms = [
        {
            "ref": f"room:{n}",
            "name": f"Room {n}",
            "game_system": "neutral",
            "system_config": {"bloodPoints": 3, "customResource": {"label": "Mana"}},
            "is_archived": False,
            "active_scene_ref": f"scene:{n}",
        }
        for n in (1, 2)
    ]
    actors = [
        {
            "ref": f"actor:{n}",
            "room_ref": f"room:{n}",
            "name": f"GM {n}",
            "role": "gm",
            "is_owner": True,
        }
        for n in (1, 2)
    ]
    actors.append(
        {
            "ref": "actor:3",
            "room_ref": "room:1",
            "name": "Player",
            "role": "player",
            "is_owner": False,
        }
    )
    scenes = [
        {
            "ref": f"scene:{n}",
            "room_ref": f"room:{n}",
            "name": f"Scene {n}",
            "width": 4096,
            "height": 4096,
            "grid_size": 64,
            "grid_enabled": True,
            "grid_color": "#64748b66",
            "background_color": "#111827",
            "snap_enabled": True,
            "unit_size": 5,
            "unit_label": "ft",
            "fog": {"enabled": False, "reveals": []},
        }
        for n in (1, 2)
    ]
    cards = []
    for n in (1, 2):
        data = CardData(name=f"Card {n}").model_dump(mode="json")
        data["owner_participant_id"] = f"actor:{n}"
        cards.append({"ref": f"card:{n}", "room_ref": f"room:{n}", "data": data})
    items = [
        {
            "ref": f"item:{n}",
            "scene_ref": f"scene:{n}",
            "asset_ref": "asset:1",
            "owner_ref": f"actor:{n}",
            "creator_ref": f"actor:{n}",
            "card_ref": f"card:{n}",
            "kind": "token",
            "name": "Token",
            "x": 0,
            "y": 0,
            "width": 64,
            "height": 64,
            "rotation": 0,
            "z_index": 0,
            "visibility": "everyone",
            "is_locked": False,
            "payload": {"customCounter": 7},
        }
        for n in (1, 2)
    ]
    image = BytesIO()
    Image.new("RGB", (2, 2)).save(image, format="PNG")
    docs = {
        "campaign.json": {
            "schema_version": 1,
            "name": "Portable fixture",
            "system_id": "neutral",
            "status": "draft",
            "rooms": rooms,
        },
        "actors.json": actors,
        "cards.json": cards,
        "scenes.json": scenes,
        "items.json": items,
        "assets.json": [
            {
                "ref": "asset:1",
                "name": "Image",
                "kind": "map",
                "content_type": "image/png",
                "byte_size": len(image.getvalue()),
                "width": 2,
                "height": 2,
                "path": "assets/asset-1.bin",
                "metadata": {"artistName": "User"},
            }
        ],
        "annotations.json": [
            {
                "ref": "annotation:1",
                "scene_ref": "scene:1",
                "owner_ref": "actor:1",
                "data": {
                    "kind": "label",
                    "points": [{"x": 10, "y": 10}],
                    "label": "Mark",
                    "visibility": "everyone",
                },
                "deleted_at": None,
            }
        ],
        "presentations.json": [
            {
                "ref": "presentation:1",
                "scene_ref": "scene:1",
                "owner_ref": "actor:1",
                "geometry": {
                    "schema_version": 1,
                    "shape": "circle",
                    "origin": {"x": 10, "y": 10},
                    "rotation": 0,
                    "radius": 64,
                    "length": 0,
                    "width": 0,
                    "angle": 360,
                    "color": "#ff0000",
                },
                "created_at": "2026-10-14T00:00:00Z",
            }
        ],
        "packages.json": [get_schema("neutral")],
        "journal.json": [
            {
                "room_ref": "room:1",
                "scene_ref": "scene:1",
                "actor_ref": "actor:1",
                "type": "item.create",
                "action": "Created token",
                "occurred_at": "2026-10-14T00:00:00Z",
                "visibility": "everyone",
                "owner_ref": "actor:1",
                "roll": None,
            }
        ],
    }
    return docs, image.getvalue()


def pack(docs, image):
    entries = {name: json.dumps(value).encode() for name, value in docs.items()}
    entries["assets/asset-1.bin"] = image
    manifest = {
        "schema_version": 1,
        "created_at": "2026-10-14T00:00:00Z",
        "entries": {
            name: {
                "sha256": hashlib.sha256(value).hexdigest(),
                "byte_size": len(value),
                "content_type": "image/png" if name.startswith("assets/") else "application/json",
            }
            for name, value in entries.items()
        },
    }
    archive = BytesIO()
    with ZipFile(archive, "w") as zipped:
        zipped.writestr("manifest.json", json.dumps(manifest))
        for name, value in entries.items():
            zipped.writestr(name, value)
    return archive.getvalue()


@pytest.mark.parametrize(
    "file,index,field,value",
    [
        ("actors.json", 2, "room_ref", None),
        ("cards.json", 0, "room_ref", None),
        ("scenes.json", 0, "room_ref", None),
        ("items.json", 0, "scene_ref", None),
        ("annotations.json", 0, "scene_ref", None),
        ("presentations.json", 0, "scene_ref", None),
        ("journal.json", 0, "room_ref", None),
        ("annotations.json", 0, "owner_ref", None),
        ("presentations.json", 0, "owner_ref", None),
        ("journal.json", 0, "actor_ref", None),
        ("items.json", 0, "card_ref", "card:999"),
        ("items.json", 0, "owner_ref", "actor:999"),
        ("items.json", 0, "creator_ref", "actor:999"),
        ("items.json", 0, "scene_ref", "scene:999"),
        ("annotations.json", 0, "owner_ref", "actor:999"),
        ("annotations.json", 0, "scene_ref", "scene:999"),
        ("presentations.json", 0, "owner_ref", "actor:999"),
        ("presentations.json", 0, "scene_ref", "scene:999"),
        ("journal.json", 0, "scene_ref", "scene:999"),
        ("journal.json", 0, "owner_ref", "actor:999"),
    ],
)
def test_invalid_required_and_room_graph_is_rejected_by_public_archive_validation(
    portable, file, index, field, value
):
    docs, image = portable
    docs[file][index][field] = value
    with pytest.raises(TransferFailure):
        validate_archive(pack(docs, image))


def test_unknown_active_scene_is_rejected_by_public_archive_validation(portable):
    docs, image = portable
    docs["campaign.json"]["rooms"][0]["active_scene_ref"] = "scene:999"
    with pytest.raises(TransferFailure):
        validate_archive(pack(docs, image))


@pytest.mark.parametrize(
    "file,field,value",
    [
        ("items.json", "card_ref", "card:2"),
        ("items.json", "owner_ref", "actor:2"),
        ("items.json", "creator_ref", "actor:2"),
        ("items.json", "scene_ref", "scene:2"),
        ("annotations.json", "owner_ref", "actor:2"),
        ("annotations.json", "scene_ref", "scene:2"),
        ("presentations.json", "owner_ref", "actor:2"),
        ("presentations.json", "scene_ref", "scene:2"),
        ("journal.json", "scene_ref", "scene:2"),
        ("journal.json", "owner_ref", "actor:2"),
    ],
)
def test_same_campaign_shared_scene_graph_is_portable(portable, file, field, value):
    docs, image = portable
    docs[file][0][field] = value
    docs["campaign.json"]["rooms"][0]["active_scene_ref"] = "scene:2"
    result = validate_archive(pack(docs, image))
    assert result[file][0][field] == value
    assert result["campaign.json"]["rooms"][0]["active_scene_ref"] == "scene:2"


@pytest.mark.parametrize(
    "field",
    [
        "pinHash",
        "accessToken",
        "refreshToken",
        "ownerUserId",
        "objectKey",
        "serviceRoleKey",
        "databaseUrl",
        "redisUrl",
        "supabaseUrl",
        "serverConfig",
        "privateKey",
        "legacyObjectKey",
        "SUPABASE_SERVICE_ROLE_KEY",
        "storageProvider",
        "storageBucket",
        "PIN_HASH",
        "pin-hash",
        "pIn_HaSh",
        "access_token",
        "DATABASE_URL",
        "storage_provider",
    ],
)
@pytest.mark.parametrize("container", ["config", "metadata", "payload"])
def test_secret_field_spelling_is_rejected_in_generic_gameplay_data(portable, field, container):
    docs, image = portable
    target = {
        "config": docs["campaign.json"]["rooms"][0]["system_config"],
        "metadata": docs["assets.json"][0]["metadata"],
        "payload": docs["items.json"][0]["payload"],
    }[container]
    target["nested"] = {field: "synthetic-marker"}
    with pytest.raises(TransferFailure):
        validate_archive(pack(docs, image))


@pytest.mark.parametrize(
    "url",
    [
        "https://bucket.example.invalid/image?X-Amz-Signature=synthetic",
        "https://bucket.example.invalid/image?X-Goog-Signature=synthetic",
        "https://bucket.example.invalid/image?sv=2026&sp=r&sig=synthetic",
        "https://bucket.example.invalid/image?Signature=synthetic&Key-Pair-Id=fixture",
        "https://bucket.example.invalid/storage/v1/render/image/sign/image?token=synthetic",
        "//bucket.example.invalid/image?X-Amz-Signature=synthetic",
        "//bucket.example.invalid/image?sv=2026&sp=r&sig=synthetic",
    ],
)
@pytest.mark.parametrize("container", ["config", "metadata", "payload"])
def test_signed_provider_urls_are_rejected_in_gameplay_values(portable, url, container):
    docs, image = portable
    target = {
        "config": docs["campaign.json"]["rooms"][0]["system_config"],
        "metadata": docs["assets.json"][0]["metadata"],
        "payload": docs["items.json"][0]["payload"],
    }[container]
    target["imageUrl"] = url
    with pytest.raises(TransferFailure):
        validate_archive(pack(docs, image))


def test_valid_room_graph_and_ordinary_gameplay_fields_survive_unchanged(portable):
    docs, image = portable
    docs["campaign.json"]["rooms"][0]["system_config"]["spellKey"] = "level_one"
    docs["assets.json"][0]["metadata"]["publicImageUrl"] = (
        "https://images.example.invalid/map.png?width=64"
    )
    docs["assets.json"][0]["metadata"]["publicRelativeImageUrl"] = (
        "//images.example.invalid/map.png?width=64"
    )
    docs["campaign.json"]["rooms"][0]["system_config"]["referenceUrl"] = (
        "//rules.example.invalid/manual?chapter=3"
    )
    docs["items.json"][0]["payload"]["iconUrl"] = "//images.example.invalid/token.png?width=32"
    assert validate_archive(pack(docs, image)) == docs
    # Nullable links remain valid without a selected scene and for a standalone token.
    docs["campaign.json"]["rooms"][0]["active_scene_ref"] = None
    item = docs["items.json"][0]
    for optional in ("asset_ref", "card_ref", "owner_ref", "creator_ref"):
        item[optional] = None
    docs["cards.json"][0]["data"]["owner_participant_id"] = None
    docs["journal.json"][0]["scene_ref"] = None
    docs["journal.json"][0]["owner_ref"] = None
    assert validate_archive(pack(docs, image)) == docs


@pytest.mark.parametrize(
    "case", ["missing_scene", "missing_card", "cross_room_card_owner", "credential"]
)
async def test_invalid_graph_or_config_causes_zero_storage_puts_and_no_gameplay_write(
    transfer, portable, case
):
    from uuid import uuid4

    from .test_transfer import terminal

    docs, image = portable
    if case == "missing_scene":
        docs["items.json"][0]["scene_ref"] = None
    elif case == "missing_card":
        docs["items.json"][0]["card_ref"] = "card:999"
    elif case == "cross_room_card_owner":
        docs["cards.json"][0]["data"]["owner_participant_id"] = "actor:2"
    else:
        docs["assets.json"][0]["metadata"]["accessToken"] = "synthetic-marker"
    before = await transfer.connection.fetchval(
        "select count(*) from app.campaigns where owner_user_id=$1", transfer.gm.user_id
    )
    job = uuid4()
    response = await transfer.client.put(
        f"/api/v1/campaign-transfers/{job}/import",
        content=pack(docs, image),
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 202
    state = await terminal(transfer.client, job)
    assert transfer.storage.put_count == 0
    assert state["phase"] == "failed", state
    assert (
        await transfer.connection.fetchval(
            "select count(*) from app.campaigns where owner_user_id=$1", transfer.gm.user_id
        )
        == before
    )
