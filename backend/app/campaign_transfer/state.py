from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.campaign_transfer.archive import encode
from app.campaign_transfer.models import (
    MAX_ENTITIES,
    MAX_HISTORY,
    MAX_JSON,
    MAX_ZIP,
    TransferFailure,
)
from app.dice_log.journal import LABELS
from app.system_packages.service import get_schema


async def rows(connection: AsyncConnection, sql: str, **parameters: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in (await connection.execute(text(sql), parameters)).mappings()]


async def authorize_export(connection: AsyncConnection, user: UUID, campaign: UUID) -> None:
    found = await connection.scalar(
        text("""
select c.id from app.campaigns c
where c.id=:campaign and c.owner_user_id=:user and exists(select 1 from
app.participants p
join app.rooms r on r.id=p.room_id where p.campaign_id=c.id and p.user_id=:user
and p.role='gm' and p.removed_at is null and not r.is_archived)
"""),
        {"campaign": campaign, "user": user},
    )
    if not found:
        raise TransferFailure("forbidden", "Нет прав на экспорт кампании", 403)


async def read_campaign(
    connection: AsyncConnection, user: UUID, campaign_id: UUID, options: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    await authorize_export(connection, user, campaign_id)
    campaign = (await rows(connection, "select * from app.campaigns where id=:id", id=campaign_id))[
        0
    ]
    source: dict[str, list[dict[str, Any]]] = {}
    source_bytes = 0
    for name, table in (
        ("room", "rooms"),
        ("actor", "participants"),
        ("scene", "scenes"),
        ("asset", "assets"),
        ("card", "cards"),
        ("item", "scene_items"),
        ("annotation", "scene_annotations"),
        ("presentation", "ability_presentations"),
    ):
        active_filter = (
            " and t.deleted_at is null" if name in {"scene", "card", "item", "annotation"} else ""
        )
        asset_filter = (
            """ and (status='ready' or exists(
            select 1 from app.scene_items i where i.asset_id=t.id and i.deleted_at is null)
            or exists(select 1 from app.cards c where c.image_asset_id=t.id
                      and c.deleted_at is null))"""
            if name == "asset"
            else ""
        )
        bounded = (
            await rows(
                connection,
                "select count(*) as count,coalesce(sum(octet_length(row_to_json(t)::text)),0) "  # noqa: S608 - fixed table allowlist
                f"as size from app.{table} t where campaign_id=:id{asset_filter}{active_filter}",
                id=campaign_id,
            )
        )[0]
        source_bytes += bounded["size"]
        if bounded["count"] > MAX_ENTITIES or source_bytes > MAX_JSON:
            raise TransferFailure("entity_limit")
        source[name] = await rows(
            connection,
            f"select * from app.{table} t where campaign_id=:id{asset_filter}{active_filter} "  # noqa: S608 - fixed table allowlist
            f"order by id limit {MAX_ENTITIES + 1}",
            id=campaign_id,
        )
    if sum(len(values) for values in source.values()) > MAX_ENTITIES:
        raise TransferFailure("entity_limit")
    if sum(asset["byte_size"] for asset in source["asset"]) + source_bytes > MAX_ZIP:
        raise TransferFailure("archive_limit")
    refs = {
        kind: {row["id"]: f"{kind}:{index + 1}" for index, row in enumerate(values)}
        for kind, values in source.items()
    }

    def ref(kind: str, value: Any) -> str | None:
        if value is None:
            return None
        try:
            return refs[kind][UUID(str(value))]
        except (KeyError, ValueError) as error:
            raise TransferFailure("invalid_reference") from error

    rooms = [
        {
            "ref": ref("room", r["id"]),
            "name": r["name"],
            "game_system": r["game_system"],
            "system_config": r["system_config"],
            "is_archived": r["is_archived"],
            "active_scene_ref": ref("scene", r["active_scene_id"]),
        }
        for r in source["room"]
    ]
    actors = [
        {
            "ref": ref("actor", r["id"]),
            "room_ref": ref("room", r["room_id"]),
            "name": r["display_name"],
            "role": r["role"],
            "is_owner": r["user_id"] == campaign["owner_user_id"],
        }
        for r in source["actor"]
    ]
    cards = []
    nested_counter = {"ability": 0, "inventory": 0}
    for row in source["card"]:
        data = json.loads(encode(row["data"]))
        data["owner_participant_id"] = ref("actor", row["owner_participant_id"])
        data["image_asset_id"] = ref("asset", row["image_asset_id"])
        for key, kind in (("abilities", "ability"), ("inventory", "inventory")):
            for nested in data[key]:
                nested_counter[kind] += 1
                nested["id"] = f"{kind}:{nested_counter[kind]}"
        cards.append(
            {"ref": ref("card", row["id"]), "room_ref": ref("room", row["room_id"]), "data": data}
        )
    scene_fields = (
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
    )
    scenes = [
        {
            "ref": ref("scene", r["id"]),
            "room_ref": ref("room", r["room_id"]),
            **{key: r[key] for key in scene_fields},
        }
        for r in source["scene"]
    ]
    item_fields = (
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
    )
    items = [
        {
            "ref": ref("item", r["id"]),
            "scene_ref": ref("scene", r["scene_id"]),
            "asset_ref": ref("asset", r["asset_id"]),
            "owner_ref": ref("actor", r["owner_participant_id"]),
            "creator_ref": ref("actor", r["created_by_participant_id"]),
            "card_ref": ref("card", r["card_id"]),
            **{key: r[key] for key in item_fields},
        }
        for r in source["item"]
    ]
    assets = []
    keys = {}
    for index, row in enumerate(source["asset"]):
        if row["status"] != "ready":
            raise TransferFailure("asset_unavailable", "Завершите загрузку всех изображений", 409)
        path = f"assets/asset-{index + 1}.bin"
        keys[path] = row["object_key"]
        assets.append(
            {
                "ref": ref("asset", row["id"]),
                "path": path,
                **{
                    key: row[key]
                    for key in (
                        "name",
                        "kind",
                        "content_type",
                        "byte_size",
                        "width",
                        "height",
                        "metadata",
                    )
                },
            }
        )
    annotations = [
        {
            "ref": ref("annotation", r["id"]),
            "scene_ref": ref("scene", r["scene_id"]),
            "owner_ref": ref("actor", r["owner_participant_id"]),
            "data": {key: r[key] for key in ("kind", "points", "label", "visibility")},
            "deleted_at": r["deleted_at"].isoformat() if r["deleted_at"] else None,
        }
        for r in source["annotation"]
    ]
    presentations = [
        {
            "ref": ref("presentation", r["id"]),
            "scene_ref": ref("scene", r["scene_id"]),
            "owner_ref": ref("actor", r["owner_participant_id"]),
            "geometry": r["geometry"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in source["presentation"]
    ]
    packages = (
        {(campaign["system_id"], 1)}
        | {(r["game_system"], 1) for r in source["room"]}
        | {(r["data"]["system_id"], r["data"]["system_version"]) for r in source["card"]}
    )
    docs = {
        "campaign.json": {
            "schema_version": 1,
            "name": campaign["name"],
            "system_id": campaign["system_id"],
            "status": campaign["status"],
            "rooms": rooms,
        },
        "actors.json": actors,
        "cards.json": cards,
        "scenes.json": scenes,
        "items.json": items,
        "assets.json": assets,
        "annotations.json": annotations,
        "presentations.json": presentations,
        "packages.json": [get_schema(*p) for p in sorted(packages)],
    }
    if options.get("include_snapshot"):
        docs["snapshot.json"] = {
            "schema_version": 1,
            "rooms": [
                {"room_ref": r["ref"], "active_scene_ref": r["active_scene_ref"]} for r in rooms
            ],
        }
    if options.get("include_history"):
        history = await rows(
            connection,
            """
select e.* from app.room_events e join app.rooms r on r.id=e.room_id
where r.campaign_id=:id order by e.id desc limit :limit
""",
            id=campaign_id,
            limit=MAX_HISTORY,
        )
        revoked = {
            str(row["payload"].get("undo_of"))
            for row in history
            if row["event_type"] == "action.undo" and row["payload"].get("undo_type") == "dice.roll"
        }
        journal = []
        for row in reversed(history):
            payload = row["payload"]
            if row["event_type"] == "campaign.history":
                archived = payload["history"]
                kind, action, visibility = (
                    archived["type"],
                    archived["action"],
                    archived["visibility"],
                )
                owner = archived.get("owner_participant_id")
                roll = archived.get("roll")
            else:
                kind = row["event_type"]
                action = LABELS.get(kind, "Изменение стола")
                subject = payload.get("annotation", payload.get("item", payload.get("card", {})))
                visibility = subject.get("visibility", payload.get("visibility", "everyone"))
                owner = subject.get("owner_participant_id")
                original_roll = payload.get("roll") if kind == "dice.roll" else None
                roll = (
                    {
                        key: original_roll[key]
                        for key in ("expression", "results", "modifier", "total")
                    }
                    if original_roll
                    else None
                )
                if original_roll:
                    visibility = original_roll["visibility"]
                    if str(row["id"]) in revoked:
                        action += " · отменён мастером"
            journal.append(
                {
                    "room_ref": ref("room", row["room_id"]),
                    "scene_ref": ref("scene", row["scene_id"])
                    if row["scene_id"] in refs["scene"]
                    else None,
                    "actor_ref": ref("actor", row["actor_participant_id"]),
                    "type": kind,
                    "action": action,
                    "occurred_at": row["created_at"].isoformat(),
                    "visibility": visibility,
                    "owner_ref": ref("actor", owner),
                    "roll": roll,
                }
            )
        docs["journal.json"] = journal
    return docs, keys


def remap(docs: dict[str, Any]) -> dict[str, UUID]:
    result = {
        r["ref"]: uuid4()
        for name in (
            "actors.json",
            "cards.json",
            "scenes.json",
            "items.json",
            "assets.json",
            "annotations.json",
            "presentations.json",
        )
        for r in docs[name]
    }
    result.update({r["ref"]: uuid4() for r in docs["campaign.json"]["rooms"]})
    for card in docs["cards.json"]:
        for entries in (card["data"]["inventory"], card["data"]["abilities"]):
            result.update({r["id"]: uuid4() for r in entries})
    return result


async def restore_campaign(
    connection: AsyncConnection,
    user: UUID,
    campaign: UUID,
    docs: dict[str, Any],
    ids: dict[str, UUID],
) -> None:
    def id_for(ref: str | None) -> UUID | None:
        return ids[ref] if ref else None

    now = datetime.now(UTC)
    source = docs["campaign.json"]
    profile = await connection.scalar(
        text("select display_name from app.profiles where user_id=:user"), {"user": user}
    )
    if profile is None:
        raise TransferFailure("forbidden", "Сессия мастера недействительна", 403)
    await connection.execute(
        text("""
insert into app.campaigns(id,owner_user_id,name,system_id,status)
values(:id,:user,:name,:system,:status)
"""),
        {
            "id": campaign,
            "user": user,
            "name": source["name"],
            "system": source["system_id"],
            "status": source["status"],
        },
    )
    for room in source["rooms"]:
        await connection.execute(
            text("""
insert into
app.rooms(id,campaign_id,owner_user_id,name,game_system,system_config,is_archived)
values(:id,:campaign,:user,:name,:system,cast(:config as jsonb),:archived)
"""),
            {
                "id": id_for(room["ref"]),
                "campaign": campaign,
                "user": user,
                "name": room["name"],
                "system": room["game_system"],
                "config": encode(room["system_config"]).decode(),
                "archived": room["is_archived"],
            },
        )
    for actor in docs["actors.json"]:
        await connection.execute(
            text("""
insert into app.participants(id,campaign_id,room_id,user_id,
identity_kind,role,display_name,removed_at)
values(:id,:campaign,:room,:user,:kind,:role,:name,:removed)
"""),
            {
                "id": id_for(actor["ref"]),
                "campaign": campaign,
                "room": id_for(actor["room_ref"]),
                "user": user if actor["is_owner"] else None,
                "kind": "registered" if actor["is_owner"] else "guest",
                "role": "gm" if actor["is_owner"] else actor["role"],
                "name": profile if actor["is_owner"] else actor["name"],
                "removed": None if actor["is_owner"] else now,
            },
        )
    for asset in docs["assets.json"]:
        owner = next(a for a in docs["actors.json"] if a["is_owner"])
        await connection.execute(
            text("""
insert into app.assets(id,owner_user_id,campaign_id,uploaded_by,name,kind,
object_key,content_type,byte_size,width,height,metadata,status)
values(:id,:user,:campaign,:actor,:name,:kind,:key,:mime,:size,:width,:height,cast(:metadata
as
jsonb),'ready')
"""),
            {
                "id": id_for(asset["ref"]),
                "user": user,
                "campaign": campaign,
                "actor": id_for(owner["ref"]),
                "name": asset["name"],
                "kind": asset["kind"],
                "key": f"{campaign}/{id_for(asset['ref'])}",
                "mime": asset["content_type"],
                "size": asset["byte_size"],
                "width": asset["width"],
                "height": asset["height"],
                "metadata": encode(asset["metadata"]).decode(),
            },
        )
    for card in docs["cards.json"]:
        value = json.loads(encode(card["data"]))
        for key in ("owner_participant_id", "image_asset_id"):
            value[key] = str(id_for(value[key])) if value[key] else None
        for entries in (value["inventory"], value["abilities"]):
            for nested in entries:
                nested["id"] = str(ids[nested["id"]])
        await connection.execute(
            text("""
insert into
app.cards(id,campaign_id,room_id,owner_participant_id,image_asset_id,data)
values(:id,:campaign,:room,:owner,:image,cast(:data as jsonb))
"""),
            {
                "id": id_for(card["ref"]),
                "campaign": campaign,
                "room": id_for(card["room_ref"]),
                "owner": UUID(value["owner_participant_id"])
                if value["owner_participant_id"]
                else None,
                "image": UUID(value["image_asset_id"]) if value["image_asset_id"] else None,
                "data": encode(value).decode(),
            },
        )
    for scene in docs["scenes.json"]:
        await connection.execute(
            text("""
insert into app.scenes(id,room_id,campaign_id,name,width,height,grid_size,
grid_enabled,grid_color,background_color,snap_enabled,unit_size,unit_label,fog)
values(:id,:room,:campaign,:name,:width,:height,:grid_size,:grid_enabled,:grid_color,
:background_color,:snap_enabled,:unit_size,:unit_label,cast(:fog as jsonb))
"""),
            {
                **scene,
                "id": id_for(scene["ref"]),
                "room": id_for(scene["room_ref"]),
                "campaign": campaign,
                "fog": encode(scene["fog"]).decode(),
            },
        )
    for room in source["rooms"]:
        await connection.execute(
            text("update app.rooms set active_scene_id=:scene where id=:id"),
            {"id": id_for(room["ref"]), "scene": id_for(room["active_scene_ref"])},
        )
    for item in docs["items.json"]:
        await connection.execute(
            text("""
insert into app.scene_items(id,scene_id,campaign_id,asset_id,
owner_participant_id,created_by_participant_id,card_id,kind,name,x,y,width,height,rotation,
z_index,visibility,is_locked,payload)
values(:id,:scene,:campaign,:asset,:owner,:creator,:card,
:kind,:name,:x,:y,:width,:height,:rotation,:z_index,:visibility,:is_locked,cast(:payload
as
jsonb))
"""),
            {
                **item,
                "id": id_for(item["ref"]),
                "scene": id_for(item["scene_ref"]),
                "campaign": campaign,
                "asset": id_for(item["asset_ref"]),
                "owner": id_for(item["owner_ref"]),
                "creator": id_for(item["creator_ref"]),
                "card": id_for(item["card_ref"]),
                "payload": encode(item["payload"]).decode(),
            },
        )
    for annotation in docs["annotations.json"]:
        await connection.execute(
            text("""
insert into app.scene_annotations(id,scene_id,campaign_id,owner_participant_id,
kind,points,label,visibility,deleted_at)
values(:id,:scene,:campaign,:owner,:kind,cast(:points as
jsonb),:label,:visibility,:deleted)
"""),
            {
                **annotation["data"],
                "id": id_for(annotation["ref"]),
                "scene": id_for(annotation["scene_ref"]),
                "campaign": campaign,
                "owner": id_for(annotation["owner_ref"]),
                "points": encode(annotation["data"]["points"]).decode(),
                "deleted": datetime.fromisoformat(annotation["deleted_at"])
                if annotation["deleted_at"]
                else None,
            },
        )
    for presentation in docs["presentations.json"]:
        await connection.execute(
            text("""
insert into
app.ability_presentations(id,scene_id,campaign_id,owner_participant_id,geometry,created_at)
values(:id,:scene,:campaign,:owner,cast(:geometry as jsonb),:created)
"""),
            {
                "id": id_for(presentation["ref"]),
                "scene": id_for(presentation["scene_ref"]),
                "campaign": campaign,
                "owner": id_for(presentation["owner_ref"]),
                "geometry": encode(presentation["geometry"]).decode(),
                "created": datetime.fromisoformat(presentation["created_at"]),
            },
        )
    versions = {r["ref"]: 0 for r in source["rooms"]}
    for entry in docs.get("journal.json", []):
        room = entry["room_ref"]
        versions[room] += 1
        history = {key: entry[key] for key in ("type", "action", "visibility", "roll")}
        history["owner_participant_id"] = (
            str(id_for(entry["owner_ref"])) if entry["owner_ref"] else None
        )
        await connection.execute(
            text("""
insert into app.room_events(event_id,room_id,scene_id,actor_participant_id,
event_type,aggregate_id,aggregate_version,payload,created_at)
values(:id,:room,:scene,:actor,'campaign.history',:room,:version,cast(:payload as
jsonb),:time)
"""),
            {
                "id": uuid4(),
                "room": id_for(room),
                "scene": id_for(entry["scene_ref"]),
                "actor": id_for(entry["actor_ref"]),
                "version": versions[room],
                "payload": encode({"history": history}).decode(),
                "time": datetime.fromisoformat(entry["occurred_at"]),
            },
        )
    for room, version in versions.items():
        await connection.execute(
            text("update app.rooms set scene_version=:version where id=:id"),
            {"id": id_for(room), "version": version},
        )
