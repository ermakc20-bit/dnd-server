import type { SceneProjection } from "../scene/types";

// Allowed user text can itself contain a bearer URL. Strip only recognizable
// signing formats; ordinary links, text and PIN-like numbers remain unchanged.
function safeText(value: string): string {
  return value.replace(/https?:\/\/[^\s<>"]+/gi, (link, offset: number) => {
    // URI path/query punctuation is data. Peel only surrounding prose after
    // finding the whole URL, so a path like map(1).png keeps its signing query.
    const pairs: Record<string, string> = { ")": "(", "]": "[", "}": "{" };
    const wrappers: Record<string, string> = { "(": ")", "[": "]", "{": "}", "'": "'", "`": "`", "«": "»", "“": "”", "‘": "’" };
    let wrapper: string | undefined = wrappers[value[offset - 1]];
    let end = link.length;
    // A colon is also valid URI data. Treat a punctuation suffix containing it
    // as prose only when it follows a closing outside pair or the opening quote.
    const suffix = /[.,;!?:]*$/.exec(link)![0];
    const boundary = link.length - suffix.length;
    const closing = link[boundary - 1], opening = pairs[closing], body = link.slice(0, boundary);
    if (closing === wrapper || (opening && body.split(closing).length > body.split(opening).length)) {
      end = boundary;
    }
    while (end > 0) {
      const character = link[end - 1], opening = pairs[character], body = link.slice(0, end);
      const outsidePair = opening && body.split(character).length > body.split(opening).length;
      if (!/[.,;!?]/.test(character) && !outsidePair && character !== wrapper) break;
      if (character === wrapper) wrapper = undefined;
      end--;
    }
    const candidate = link.slice(0, end), punctuation = link.slice(end);
    let url: URL;
    try { url = new URL(candidate); } catch { return link; }
    const query = new Set([...url.searchParams].filter(([, entry]) => entry.length > 0)
      .map(([key]) => key.toLowerCase()));
    const has = (key: string) => query.has(key);
    const signed = has("x-amz-signature") || has("x-goog-signature")
      || (has("signature") && (has("awsaccesskeyid") || has("googleaccessid") || has("key-pair-id")))
      || (has("sig") && has("sv") && (has("sp") || has("se") || has("sr")))
      || (has("token") && /\/storage\/v1\/(?:object|render\/image)\/sign(?:\/|$)/i.test(url.pathname));
    return signed ? `[подписанная ссылка скрыта]${punctuation}` : link;
  });
}

// Explicit field projection: never copy a transport frame or an SDK/session object.
export function emergencySnapshot(projection: SceneProjection, confirmedAt: string) {
  const scene = projection.scene;
  return {
    schema_version: 1, confirmed_at: confirmedAt, room_id: projection.room_id,
    aggregate_version: projection.aggregate_version, event_cursor: projection.event_cursor,
    scenes: projection.scenes.map(({ id, name }) => ({ id, name: safeText(name) })),
    scene: scene ? { id: scene.id, name: safeText(scene.name), width: scene.width, height: scene.height,
      grid_size: scene.grid_size, grid_enabled: scene.grid_enabled, snap_enabled: scene.snap_enabled,
      unit_size: scene.unit_size, unit_label: safeText(scene.unit_label) } : null,
    items: projection.items.map(item => ({ id: item.id, kind: item.kind, name: safeText(item.name),
      asset_id: item.asset_id, card_id: item.card_id ?? null, x: item.x, y: item.y,
      width: item.width, height: item.height, rotation: item.rotation, z_index: item.z_index,
      visibility: item.visibility, is_locked: item.is_locked, owner_participant_id: item.owner_participant_id })),
    fog: projection.fog ? { enabled: projection.fog.enabled,
      reveals: projection.fog.reveals.map(reveal => ({ points: reveal.points.map(({ x, y }) => ({ x, y })) })) } : null,
    annotations: (projection.annotations ?? []).map(annotation => ({ id: annotation.id, kind: annotation.kind,
      points: annotation.points.map(({ x, y }) => ({ x, y })), label: safeText(annotation.label),
      visibility: annotation.visibility, owner_participant_id: annotation.owner_participant_id })),
    ability_presentations: (projection.ability_presentations ?? []).map(presentation => ({
      id: presentation.id, created_at: presentation.created_at,
      affected_item_ids: [...presentation.affected_item_ids], geometry: {
        schema_version: presentation.geometry.schema_version, shape: presentation.geometry.shape,
        origin: { x: presentation.geometry.origin.x, y: presentation.geometry.origin.y },
        rotation: presentation.geometry.rotation, radius: presentation.geometry.radius,
        length: presentation.geometry.length, width: presentation.geometry.width,
        angle: presentation.geometry.angle, color: safeText(presentation.geometry.color),
      },
    })),
  };
}

export function downloadEmergencySnapshot(snapshot: ReturnType<typeof emergencySnapshot>) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url; link.download = `room-${snapshot.room_id}-confirmed.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
