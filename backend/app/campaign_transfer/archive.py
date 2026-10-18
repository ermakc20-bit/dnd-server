from __future__ import annotations

import hashlib
import json
import math
import re
import stat
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from urllib.parse import parse_qsl, unquote
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

from pydantic import ValidationError

from app.ability_geometry.models import PresentedGeometry
from app.assets.models import MAX_ASSET_BYTES
from app.assets.service import inspect_asset
from app.campaign_transfer.models import (
    MAX_ENTITIES,
    MAX_ENTRIES,
    MAX_EXPANDED,
    MAX_HISTORY,
    MAX_JSON,
    MAX_ZIP,
    TransferFailure,
)
from app.cards.models import CardData
from app.scene_tools.models import AnnotationData, Fog
from app.scenes.models import SceneFailure
from app.system_packages.service import get_schema, validate_card

JSON_FILES = {
    "campaign.json",
    "actors.json",
    "cards.json",
    "scenes.json",
    "items.json",
    "assets.json",
    "annotations.json",
    "presentations.json",
    "packages.json",
}
OPTIONAL_FILES = {"journal.json", "snapshot.json"}
REF = re.compile(r"^[a-z]+:[1-9][0-9]{0,5}$")
FORBIDDEN = {
    "password",
    "pin",
    "pin_hash",
    "token",
    "token_hash",
    "access_token",
    "refresh_token",
    "guest_session_id",
    "session_id",
    "user_id",
    "owner_user_id",
    "object_key",
    "signed_url",
    "signedurl",
    "authorization",
    "api_key",
    "apikey",
    "service_role_key",
    "database_url",
    "redis_url",
    "supabase_url",
    "server_config",
    "credential",
    "credentials",
    "secret",
    "private_key",
    "legacy_object_key",
    "supabase_service_role_key",
    "supabase_service_key",
    "service_key",
    "secret_key",
    "client_secret",
    "aws_access_key_id",
    "aws_secret_access_key",
    "provider_config",
    "provider_url",
    "provider_key",
    "storage_provider",
    "storage_url",
    "storage_endpoint",
    "storage_bucket",
    "storage_bucket_id",
    "storage_bucket_name",
    "storage_object_key",
    "server_configuration",
}
FORBIDDEN_NORMALIZED = {re.sub(r"[^a-z0-9]", "", key.casefold()) for key in FORBIDDEN}
SIGNED_QUERY_KEYS = {
    "xamzsignature",
    "xgoogsignature",
    "signature",
    "sig",
    "token",
    "access_token",
    "accesstoken",
}


def normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def contains_signed_url(value: str) -> bool:
    decoded = unquote(unquote(value))
    lowered = decoded.casefold()
    if "/object/sign/" in lowered or "/render/image/sign/" in lowered:
        return True
    for url in re.findall(r"(?:https?:)?//[^\s<>\"']+", decoded, flags=re.IGNORECASE):
        if any(
            normalized_key(key) in SIGNED_QUERY_KEYS
            for key, _value in parse_qsl(
                url.partition("?")[2].split("#", 1)[0], keep_blank_values=True
            )
        ):
            return True
    return False


def encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def strict_json(data: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise TransferFailure("duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_constant: str) -> None:
        raise TransferFailure("invalid_number")

    return json.loads(data, object_pairs_hook=object_pairs, parse_constant=invalid_constant)


def portable_time(value: Any) -> datetime:
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise TransferFailure("invalid_timestamp")
    return stamp


def gameplay_config(value: Any) -> None:
    if not isinstance(value, dict):
        raise TransferFailure("unsafe_config")
    count = 0

    def visit(node: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if depth > 8 or count > 2000:
            raise TransferFailure("config_limit")
        if isinstance(node, dict):
            for key, child in node.items():
                if not isinstance(key, str) or normalized_key(key) in FORBIDDEN_NORMALIZED:
                    raise TransferFailure("unsafe_config", "Настройки содержат непереносимые поля")
                visit(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                visit(child, depth + 1)
        elif isinstance(node, str):
            if contains_signed_url(node) or any(
                marker in node.lower()
                for marker in ("/object/sign/", "bearer ", "sb_secret_", "-----begin ")
            ):
                raise TransferFailure("unsafe_config")
        elif node is not None and (
            not isinstance(node, (bool, int, float))
            or (isinstance(node, float) and not math.isfinite(node))
        ):
            raise TransferFailure("unsafe_config")

    visit(value, 0)
    if len(encode(value)) > 65536:
        raise TransferFailure("config_limit")


def build_archive(documents: dict[str, Any], assets: dict[str, bytes]) -> bytes:
    entries = {name: encode(value) for name, value in documents.items()}
    entries.update(assets)
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "entries": {
            path: {
                "sha256": hashlib.sha256(data).hexdigest(),
                "byte_size": len(data),
                "content_type": "application/json"
                if path.endswith(".json")
                else next(a["content_type"] for a in documents["assets.json"] if a["path"] == path),
            }
            for path, data in entries.items()
        },
    }
    target = BytesIO()
    with ZipFile(target, "w", compression=ZIP_STORED) as zipped:
        zipped.writestr("manifest.json", encode(manifest))
        for path, data in entries.items():
            zipped.writestr(path, data)
    result = target.getvalue()
    if len(result) > MAX_ZIP:
        raise TransferFailure("archive_limit", "Кампания превышает лимит архива 256 МБ")
    validate_archive(result)
    return result


def validate_archive(data: bytes) -> dict[str, Any]:
    """Validate every member and the full relation graph before any gameplay write."""
    try:
        return _validate_archive(data)
    except TransferFailure:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        BadZipFile,
        OSError,
        ValidationError,
        SceneFailure,
        RecursionError,
        UnicodeError,
    ) as error:
        raise TransferFailure("invalid_archive") from error


def _validate_archive(data: bytes) -> dict[str, Any]:
    if not 0 < len(data) <= MAX_ZIP:
        raise TransferFailure("archive_limit")
    with ZipFile(BytesIO(data)) as zipped:
        infos = zipped.infolist()
        paths = [entry.filename for entry in infos]
        if (
            len(paths) > MAX_ENTRIES
            or len(paths) != len(set(paths))
            or "manifest.json" not in paths
        ):
            raise TransferFailure("unsafe_archive")
        total = json_size = 0
        for info in infos:
            path = info.filename
            mode = info.external_attr >> 16
            if (
                path not in JSON_FILES | OPTIONAL_FILES | {"manifest.json"}
                and not re.fullmatch(r"assets/asset-[1-9][0-9]{0,5}\.bin", path)
            ) or (
                info.flag_bits & 1
                or stat.S_ISLNK(mode)
                or info.is_dir()
                or info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
            ):
                raise TransferFailure("unsafe_archive")
            total += info.file_size
            if path.endswith(".json"):
                json_size += info.file_size
            elif info.file_size > MAX_ASSET_BYTES:
                raise TransferFailure("archive_limit")
        if total > MAX_EXPANDED or json_size > MAX_JSON:
            raise TransferFailure("archive_limit")
        manifest = strict_json(zipped.read("manifest.json"))
        if (
            set(manifest) != {"schema_version", "created_at", "entries"}
            or manifest["schema_version"] != 1
            or isinstance(manifest["schema_version"], bool)
        ):
            raise TransferFailure("archive_version")
        portable_time(manifest["created_at"])
        checksums = manifest["entries"]
        if set(checksums) != set(paths) - {"manifest.json"} or not JSON_FILES <= set(paths):
            raise TransferFailure("invalid_manifest")
        docs: dict[str, Any] = {}
        for info in infos:
            path = info.filename
            if path == "manifest.json":
                continue
            value = zipped.read(info)
            entry = checksums[path]
            if (
                set(entry) != {"sha256", "byte_size", "content_type"}
                or entry["byte_size"] != len(value)
                or entry["sha256"] != hashlib.sha256(value).hexdigest()
            ):
                raise TransferFailure("checksum")
            if path.endswith(".json"):
                if entry["content_type"] != "application/json":
                    raise TransferFailure("mime")
                docs[path] = strict_json(value)
        validate_documents(docs)
        assets = docs["assets.json"]
        if {a["path"] for a in assets} != {p for p in paths if p.startswith("assets/")}:
            raise TransferFailure("asset_reference")
        for asset in assets:
            body = zipped.read(asset["path"])
            if (
                checksums[asset["path"]]["content_type"] != asset["content_type"]
                or len(body) != asset["byte_size"]
                or inspect_asset(body, asset["content_type"]) != (asset["width"], asset["height"])
            ):
                raise TransferFailure("invalid_asset")
        return docs


def validate_documents(docs: dict[str, Any]) -> None:
    # Typed card strings are gameplay text too. Inspect every portable text
    # value, not only untyped metadata/config, without reserving ordinary keys.
    pending: list[Any] = [docs]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, str) and contains_signed_url(node):
            raise TransferFailure("unsafe_config")
    campaign = docs["campaign.json"]
    if set(campaign) != {"schema_version", "name", "system_id", "status", "rooms"}:
        raise TransferFailure("invalid_campaign")
    if (
        type(campaign["schema_version"]) is not int
        or campaign["schema_version"] != 1
        or not 1 <= len(campaign["name"]) <= 120
    ):
        raise TransferFailure("archive_version")
    get_schema(campaign["system_id"])
    if campaign["status"] not in {"draft", "active", "archived"}:
        raise TransferFailure("invalid_campaign")
    tables = {
        "room": campaign["rooms"],
        "actor": docs["actors.json"],
        "card": docs["cards.json"],
        "scene": docs["scenes.json"],
        "item": docs["items.json"],
        "asset": docs["assets.json"],
        "annotation": docs["annotations.json"],
        "presentation": docs["presentations.json"],
    }
    maps: dict[str, dict[str, Any]] = {}
    total = 0
    for kind, rows in tables.items():
        if not isinstance(rows, list):
            raise TransferFailure("invalid_entities")
        total += len(rows)
        maps[kind] = {}
        for row in rows:
            ref = row["ref"]
            if not isinstance(ref, str) or not REF.fullmatch(ref) or not ref.startswith(kind + ":"):
                raise TransferFailure("invalid_reference")
            if ref in maps[kind]:
                raise TransferFailure("duplicate_reference")
            maps[kind][ref] = row
    if not campaign["rooms"] or total > MAX_ENTITIES:
        raise TransferFailure("entity_limit")

    def reference(kind: str, ref: Any, room: str | None = None, *, required: bool = False) -> None:
        if ref is None:
            if required:
                raise TransferFailure("invalid_reference")
            return
        row = maps[kind].get(ref)
        if row is None or (room is not None and row.get("room_ref") != room):
            raise TransferFailure("invalid_reference")

    for room in campaign["rooms"]:
        if set(room) != {
            "ref",
            "name",
            "game_system",
            "system_config",
            "is_archived",
            "active_scene_ref",
        }:
            raise TransferFailure("invalid_room")
        if not 1 <= len(room["name"]) <= 120 or type(room["is_archived"]) is not bool:
            raise TransferFailure("invalid_room")
        get_schema(room["game_system"])
        gameplay_config(room["system_config"])
        reference("scene", room["active_scene_ref"])
        owners = [a for a in tables["actor"] if a["room_ref"] == room["ref"] and a["is_owner"]]
        if len(owners) != 1:
            raise TransferFailure("invalid_owner")
    for actor in tables["actor"]:
        if set(actor) != {"ref", "room_ref", "name", "role", "is_owner"}:
            raise TransferFailure("invalid_actor")
        reference("room", actor["room_ref"], required=True)
        if (
            not 1 <= len(actor["name"]) <= 80
            or actor["role"] not in {"gm", "player"}
            or type(actor["is_owner"]) is not bool
            or (actor["is_owner"] and actor["role"] != "gm")
        ):
            raise TransferFailure("invalid_actor")
    temporary = {ref: uuid4() for rows in maps.values() for ref in rows}
    nested: set[str] = set()
    for card in tables["card"]:
        if set(card) != {"ref", "room_ref", "data"}:
            raise TransferFailure("invalid_card")
        reference("room", card["room_ref"], required=True)
        value = json.loads(encode(card["data"]))
        for key, kind in (("owner_participant_id", "actor"), ("image_asset_id", "asset")):
            reference(kind, value.get(key), card["room_ref"] if kind == "actor" else None)
            value[key] = temporary[value[key]] if value.get(key) else None
        for nested_kind, entries in (
            ("inventory", value.get("inventory", [])),
            ("ability", value.get("abilities", [])),
        ):
            for entity in entries:
                ref = entity["id"]
                if (
                    not isinstance(ref, str)
                    or not REF.fullmatch(ref)
                    or not ref.startswith(nested_kind + ":")
                    or ref in nested
                ):
                    raise TransferFailure("duplicate_reference")
                nested.add(ref)
                entity["id"] = uuid4()
        if type(value["schema_version"]) is not int or any(
            type(a["schema_version"]) is not int for a in value["abilities"]
        ):
            raise TransferFailure("archive_version")
        validate_card(CardData.model_validate(value, strict=True))
    for scene in tables["scene"]:
        reference("room", scene["room_ref"], required=True)
        if set(scene) != {
            "ref",
            "room_ref",
            "name",
            "width",
            "height",
            "grid_size",
            "grid_enabled",
            "grid_color",
            "background_color",
            "snap_enabled",
            "unit_size",
            "unit_label",
            "fog",
        }:
            raise TransferFailure("invalid_scene")
        if not 1 <= len(scene["name"]) <= 120:
            raise TransferFailure("invalid_scene")
        for key, minimum, maximum in (
            ("width", 256, 32768),
            ("height", 256, 32768),
            ("grid_size", 8, 512),
        ):
            if type(scene[key]) is not int or not minimum <= scene[key] <= maximum:
                raise TransferFailure("invalid_scene")
        if (
            type(scene["grid_enabled"]) is not bool
            or type(scene["snap_enabled"]) is not bool
            or type(scene["unit_size"]) not in {int, float}
            or not 0 < scene["unit_size"] <= 10000
            or not 1 <= len(scene["unit_label"]) <= 24
            or not re.fullmatch(r"#[0-9a-fA-F]{8}", scene["grid_color"])
            or not re.fullmatch(r"#[0-9a-fA-F]{6}", scene["background_color"])
        ):
            raise TransferFailure("invalid_scene")
        if set(scene["fog"]) != {"enabled", "reveals"}:
            raise TransferFailure("invalid_fog")
        Fog.model_validate(scene["fog"], strict=True)
    for item in tables["item"]:
        reference("scene", item["scene_ref"], required=True)
        reference("asset", item["asset_ref"])
        reference("actor", item["owner_ref"])
        reference("actor", item["creator_ref"])
        reference("card", item["card_ref"])
        if set(item) != {
            "ref",
            "scene_ref",
            "asset_ref",
            "owner_ref",
            "creator_ref",
            "card_ref",
            "kind",
            "name",
            "x",
            "y",
            "width",
            "height",
            "rotation",
            "z_index",
            "visibility",
            "is_locked",
            "payload",
        }:
            raise TransferFailure("invalid_item")
        if (
            item["kind"] not in {"map", "token"}
            or len(item["name"]) > 160
            or item["visibility"] not in {"everyone", "gm_only", "owner_only"}
            or type(item["is_locked"]) is not bool
            or type(item["z_index"]) is not int
            or (item["card_ref"] and item["kind"] != "token")
        ):
            raise TransferFailure("invalid_item")
        for key, lower, upper in (
            ("x", -1000000, 1000000),
            ("y", -1000000, 1000000),
            ("width", 0.01, 1000000),
            ("height", 0.01, 1000000),
            ("rotation", -360000, 360000),
        ):
            if type(item[key]) not in {int, float} or not lower <= item[key] <= upper:
                raise TransferFailure("invalid_item")
        gameplay_config(item["payload"])
    for asset in tables["asset"]:
        if set(asset) != {
            "ref",
            "name",
            "kind",
            "content_type",
            "byte_size",
            "width",
            "height",
            "path",
            "metadata",
        }:
            raise TransferFailure("invalid_asset")
        if (
            not 1 <= len(asset["name"]) <= 160
            or asset["kind"] not in {"map", "character", "prop", "image"}
            or type(asset["byte_size"]) is not int
            or not 0 < asset["byte_size"] <= MAX_ASSET_BYTES
            or type(asset["width"]) is not int
            or type(asset["height"]) is not int
            or asset["width"] <= 0
            or asset["height"] <= 0
        ):
            raise TransferFailure("invalid_asset")
        gameplay_config(asset["metadata"])
    for annotation in tables["annotation"]:
        if set(annotation) != {"ref", "scene_ref", "owner_ref", "data", "deleted_at"}:
            raise TransferFailure("invalid_annotation")
        reference("scene", annotation["scene_ref"], required=True)
        reference(
            "actor",
            annotation["owner_ref"],
            required=True,
        )
        if annotation["owner_ref"] is None:
            raise TransferFailure("invalid_annotation")
        AnnotationData.model_validate(annotation["data"], strict=True)
        if annotation["deleted_at"] is not None:
            portable_time(annotation["deleted_at"])
    pairs = set()
    for presentation in tables["presentation"]:
        if set(presentation) != {"ref", "scene_ref", "owner_ref", "geometry", "created_at"}:
            raise TransferFailure("invalid_presentation")
        reference("scene", presentation["scene_ref"], required=True)
        reference(
            "actor",
            presentation["owner_ref"],
            required=True,
        )
        pair = (presentation["scene_ref"], presentation["owner_ref"])
        if pair in pairs:
            raise TransferFailure("duplicate_reference")
        pairs.add(pair)
        if presentation["owner_ref"] is None:
            raise TransferFailure("invalid_presentation")
        geometry = PresentedGeometry.model_validate(presentation["geometry"], strict=True)
        if (
            any(n < 0 for n in (geometry.radius, geometry.width, geometry.length))
            or not 0 < geometry.angle <= 360
        ):
            raise TransferFailure("invalid_presentation")
        portable_time(presentation["created_at"])
    if total + len(nested) > MAX_ENTITIES:
        raise TransferFailure("entity_limit")
    expected = (
        {(campaign["system_id"], 1)}
        | {(r["game_system"], 1) for r in campaign["rooms"]}
        | {(c["data"]["system_id"], c["data"]["system_version"]) for c in tables["card"]}
    )
    packages = docs["packages.json"]
    if (
        len(packages) != len(expected)
        or {(p["system_id"], p["version"]) for p in packages} != expected
    ):
        raise TransferFailure("invalid_package")
    for package in packages:
        if package != get_schema(package["system_id"], package["version"]):
            raise TransferFailure("invalid_package")
    history = docs.get("journal.json", [])
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise TransferFailure("history_limit")
    for entry in history:
        if set(entry) != {
            "room_ref",
            "scene_ref",
            "actor_ref",
            "type",
            "action",
            "occurred_at",
            "visibility",
            "owner_ref",
            "roll",
        }:
            raise TransferFailure("invalid_history")
        reference("room", entry["room_ref"], required=True)
        reference("scene", entry["scene_ref"])
        reference("actor", entry["actor_ref"], entry["room_ref"], required=True)
        if entry["actor_ref"] is None:
            raise TransferFailure("invalid_history")
        reference("actor", entry["owner_ref"])
        if (
            not re.fullmatch(r"[a-z][a-z0-9_.-]{1,63}", entry["type"])
            or not 1 <= len(entry["action"]) <= 160
            or entry["visibility"] not in {"everyone", "gm_only", "owner_only"}
        ):
            raise TransferFailure("invalid_history")
        portable_time(entry["occurred_at"])
        roll = entry["roll"]
        if roll is not None:
            if entry["visibility"] not in {"everyone", "gm_only"}:
                raise TransferFailure("invalid_history")
            if set(roll) != {"expression", "results", "modifier", "total"} or not re.fullmatch(
                r"[0-9]{1,3}d[0-9]{1,4}([+-][0-9]{1,5})?", roll["expression"]
            ):
                raise TransferFailure("invalid_history")
            if not 1 <= len(roll["results"]) <= 100 or any(
                type(n) is not int or not 1 <= n <= 1000 for n in roll["results"]
            ):
                raise TransferFailure("invalid_history")
            if (
                type(roll["modifier"]) is not int
                or abs(roll["modifier"]) > 10000
                or type(roll["total"]) is not int
                or roll["total"] != sum(roll["results"]) + roll["modifier"]
            ):
                raise TransferFailure("invalid_history")
    if "snapshot.json" in docs:
        snapshot = docs["snapshot.json"]
        if snapshot != {
            "schema_version": 1,
            "rooms": [
                {"room_ref": r["ref"], "active_scene_ref": r["active_scene_ref"]}
                for r in campaign["rooms"]
            ],
        }:
            raise TransferFailure("invalid_snapshot")


def asset_bytes(archive: bytes, path: str) -> bytes:
    with ZipFile(BytesIO(archive)) as zipped:
        return zipped.read(path)
