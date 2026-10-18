import { act, fireEvent, render, screen } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { SceneExperience } from "../scene/SceneExperience";
import type { SceneApi, SceneProjection } from "../scene/types";
import type { RealtimeFactory, RealtimeOptions } from "./transport";

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const room = { id: "r", campaign_id: "c", name: "Стол", is_locked: false,
  pin_enabled: false, created_at: "", can_manage: true };

it.each([
  "https://e.invalid/x?X-Amz-Signature=F3_SIGNED_CANARY",
  "https://e.invalid/map(1).png?X-Amz-Signature=F3_SIGNED_CANARY",
  "https://e.invalid/map'one'.png?X-Amz-Signature=F3_SIGNED_CANARY",
  "https://e.invalid/part;v=1,map@box+name.png?X-Amz-Signature=F3_SIGNED_CANARY",
  "https://e.invalid/map!$&'()*+,;=:@~_%25.png?X-Amz-Signature=F3_SIGNED_CANARY",
  "https://[2001:db8::1]/map(1).png?X-Amz-Signature=F3_SIGNED_CANARY",
  "https://e.invalid/map%22one%22.png?X-Amz-Signature=F3_SIGNED_CANARY",
  "https://e.invalid/map(1).png?X-Amz-Signature=F3_SIGNED_CANARY&file=(image)",
  "https://e.invalid/map(1).png?X-Amz-Signature=F3_SIGNED_CANARY&file=chapter:2:",
  "https://e.invalid/x?x-amz-signature=F3_SIGNED_CANARY&X-Amz-Credential=fixture",
  "https://e.invalid/x?X-Amz-Signature=F3_SIGNED_CANARY&x-amz-signature=",
  "https://e.invalid/x?X-Goog-Signature=F3_SIGNED_CANARY",
  "https://e.invalid/x?GoogleAccessId=fixture&Signature=F3_SIGNED_CANARY",
  "https://e.invalid/x?sv=2026-01-01&sp=r&sig=F3_SIGNED_CANARY",
  "https://e.invalid/x?Expires=1&Key-Pair-Id=fixture&Signature=F3_SIGNED_CANARY",
  "https://e.invalid/storage/v1/object/sign/private/x?token=F3_SIGNED_CANARY",
  "https://e.invalid/storage/v1/render/image/sign/private/x?token=F3_SIGNED_CANARY",
])("redacts recognized signed links in actual GM offline download, preserving ordinary text and projection: %s", async signed => {
  vi.useFakeTimers();
  let callbacks!: RealtimeOptions;
  const transport: RealtimeFactory = options => { callbacks = options; return {
    close() {}, reconnect() {}, preview() {}, refresh: async () => false,
  }; };
  const request = vi.fn(), command = vi.fn(); vi.stubGlobal("fetch", request);
  const blobs: Blob[] = [];
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: (blob: Blob) => { blobs.push(blob); return "blob:fixture"; }, revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const publicUrl = "https://public.invalid/map!$&'()*+,;=:@~_-%25.png?signature=chapter:2,3&token=public-document#section(1):";
  const snapshot: SceneProjection = { room_id: "r", actor_session_id: "SESSION_CANARY", aggregate_version: 4,
    event_cursor: 9, can_manage: true, scenes: [{ id: "s", name: signed }],
    scene: { id: "s", name: `Карта (${signed})`, width: 100, height: 200, grid_size: 50,
      grid_enabled: true, snap_enabled: true, unit_size: 5, unit_label: "ft" },
    items: [{ id: "t", kind: "token", name: `Токен ${signed}`, asset_id: null, x: 12, y: 34,
      width: 50, height: 50, rotation: 90, z_index: 1, visibility: "everyone", is_locked: false,
      owner_participant_id: "p", can_transform: true }],
    annotations: [{ id: "a", kind: "label", points: [{ x: 1, y: 2 }],
      label: `Обычный текст 1234 ${publicUrl} (${signed}), [${signed}]; '${signed}'! (${signed}): '${signed}': «${signed}»: конец`, visibility: "everyone",
      owner_participant_id: "p", can_edit: true }] };
  const unchanged = JSON.stringify(snapshot);
  const view = render(createElement(SceneExperience, { room, accessToken: "AUTH_CANARY",
    api: { command } as unknown as SceneApi, realtimeFactory: transport,
    rendererFactory: async () => ({ render() {}, destroy() {} }),
  }));
  try {
    act(() => { callbacks.onSnapshot(snapshot); callbacks.onState("connected"); callbacks.onState("disconnected"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    fireEvent.click(screen.getByRole("button", { name: "Скачать аварийный снимок" }));
    vi.useRealTimers();
    const raw = await new Promise<string>(resolve => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(blobs[0]); });
    const body = JSON.parse(raw);
    expect(raw).not.toContain("F3_SIGNED_CANARY"); expect(raw).not.toContain(signed);
    expect(raw).toContain("Обычный текст 1234"); expect(raw).toContain(publicUrl); expect(raw).toContain("конец");
    expect(body.scene.name).toBe("Карта ([подписанная ссылка скрыта])");
    expect(body.scenes[0].name).toBe("[подписанная ссылка скрыта]");
    expect(body.annotations[0].label).toBe(`Обычный текст 1234 ${publicUrl} ([подписанная ссылка скрыта]), [[подписанная ссылка скрыта]]; '[подписанная ссылка скрыта]'! ([подписанная ссылка скрыта]): '[подписанная ссылка скрыта]': «[подписанная ссылка скрыта]»: конец`);
    expect(body.scene).toMatchObject({ id: "s", width: 100, height: 200, grid_size: 50, unit_label: "ft" });
    expect(body.items[0]).toMatchObject({ id: "t", x: 12, y: 34, rotation: 90, owner_participant_id: "p" });
    expect(body.annotations[0].points).toEqual([{ x: 1, y: 2 }]);
    expect(JSON.stringify(snapshot)).toBe(unchanged);
    expect(request).not.toHaveBeenCalled(); expect(command).not.toHaveBeenCalled();
  } finally { view.unmount(); }
});

it.each([ ["(", ")"], ["'", "'"], ["«", "»"] ])(
  "preserves the wrapper and following colon in all allowed text fields: %s %s", async (opening, closing) => {
  vi.useFakeTimers();
  let callbacks!: RealtimeOptions;
  const transport: RealtimeFactory = options => { callbacks = options; return {
    close() {}, reconnect() {}, preview() {}, refresh: async () => false,
  }; };
  const request = vi.fn(), command = vi.fn(); vi.stubGlobal("fetch", request);
  const blobs: Blob[] = [];
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: (blob: Blob) => { blobs.push(blob); return "blob:fixture"; }, revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const signed = "https://e.invalid/map(1)'one'.png?X-Amz-Signature=F3_SIGNED_CANARY&file=chapter:2:";
  const publicUrl = "https://public.invalid/a!$&'()*+,;=:@~_-%25?q=chapter:2,3&token=public#section(1):";
  const text = `Ввод 1234 ${publicUrl} ${opening}${signed}${closing}: конец`;
  const expected = `Ввод 1234 ${publicUrl} ${opening}[подписанная ссылка скрыта]${closing}: конец`;
  const snapshot: SceneProjection = { room_id: "r", actor_session_id: "SESSION_CANARY", aggregate_version: 23,
    event_cursor: 47, can_manage: true, scenes: [{ id: "s", name: text }],
    scene: { id: "s", name: text, width: 100, height: 200, grid_size: 50,
      grid_enabled: true, snap_enabled: true, unit_size: 5, unit_label: text },
    items: [{ id: "t", kind: "token", name: text, asset_id: "asset-id", card_id: "card-id", x: 12.5, y: -8.25,
      width: 50, height: 50, rotation: 17, z_index: 3, visibility: "everyone", is_locked: false,
      owner_participant_id: "p", can_transform: true }],
    fog: { enabled: true, reveals: [{ points: [{ x: 1, y: 2 }] }] },
    annotations: [{ id: "a", kind: "label", points: [{ x: 1, y: 2 }], label: text,
      visibility: "everyone", owner_participant_id: "p", can_edit: true }],
    ability_presentations: [{ id: "ability-id", created_at: "2026-10-15T00:00:00Z", affected_item_ids: ["t"], can_clear: true,
      geometry: { schema_version: 1, shape: "cone", origin: { x: 5.5, y: 8.5 }, rotation: 45,
        radius: 12, length: 20, width: 5, angle: 30, color: text } }],
  };
  const unchanged = JSON.stringify(snapshot);
  const view = render(createElement(SceneExperience, { room, accessToken: "AUTH_CANARY",
    api: { command } as unknown as SceneApi, realtimeFactory: transport,
    rendererFactory: async () => ({ render() {}, destroy() {} }),
  }));
  try {
    act(() => { callbacks.onSnapshot(snapshot); callbacks.onState("connected"); callbacks.onState("disconnected"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    fireEvent.click(screen.getByRole("button", { name: "Скачать аварийный снимок" }));
    vi.useRealTimers();
    const raw = await new Promise<string>(resolve => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(blobs[0]); });
    const body = JSON.parse(raw);
    expect(raw).not.toContain("F3_SIGNED_CANARY"); expect(raw).not.toContain(signed);
    expect(raw).not.toContain("SESSION_CANARY"); expect(raw).not.toContain("AUTH_CANARY");
    expect([body.scenes[0].name, body.scene.name, body.scene.unit_label, body.items[0].name,
      body.annotations[0].label, body.ability_presentations[0].geometry.color]).toEqual(Array(6).fill(expected));
    expect(body).toMatchObject({ room_id: "r", aggregate_version: 23, event_cursor: 47 });
    expect(body.items[0]).toMatchObject({ id: "t", asset_id: "asset-id", card_id: "card-id", x: 12.5, y: -8.25,
      rotation: 17, owner_participant_id: "p" });
    expect(body.annotations[0].points).toEqual([{ x: 1, y: 2 }]);
    expect(body.fog).toEqual(snapshot.fog); expect(JSON.stringify(snapshot)).toBe(unchanged);
    expect(request).not.toHaveBeenCalled(); expect(command).not.toHaveBeenCalled();
  } finally { view.unmount(); }
});

it("downloads only the local confirmed allowlist, without fetch or commands, then replaces and clears it", async () => {
  vi.useFakeTimers();
  let callbacks!: RealtimeOptions;
  const transport: RealtimeFactory = options => { callbacks = options; return {
    close() {}, reconnect() {}, preview() {}, refresh: async () => false,
  }; };
  const command = vi.fn(); const request = vi.fn(); vi.stubGlobal("fetch", request);
  const blobs: Blob[] = [];
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: (blob: Blob) => { blobs.push(blob); return "blob:fixture"; }, revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const snapshot = { room_id: "r", actor_session_id: "SESSION_CANARY", aggregate_version: 3,
    event_cursor: 9, can_manage: true, scenes: [], scene: null, items: [],
    token: "TOKEN_CANARY", signed_url: "SIGNED_URL_CANARY", pending: "PENDING_CANARY",
    fog: { enabled: true, reveals: [], raw: "RAW_CANARY" },
  } as SceneProjection;
  const view = render(createElement(SceneExperience, { room, accessToken: "AUTH_CANARY",
    api: { command } as unknown as SceneApi, realtimeFactory: transport }));
  try {
    act(() => { callbacks.onSnapshot(snapshot); callbacks.onState("connected"); });
    act(() => callbacks.onState("disconnected"));
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    fireEvent.click(screen.getByRole("button", { name: "Скачать аварийный снимок" }));
    vi.useRealTimers();
    const text = await new Promise<string>(resolve => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(blobs[0]); });
    vi.useFakeTimers();
    const body = JSON.parse(text);
    expect(body.schema_version).toBe(1); expect(body.room_id).toBe("r");
    expect(body.aggregate_version).toBe(3); expect(body.event_cursor).toBe(9);
    expect(body.fog).toEqual({ enabled: true, reveals: [] });
    for (const canary of ["SESSION", "TOKEN", "SIGNED_URL", "PENDING", "RAW", "AUTH"]) expect(text).not.toContain(`${canary}_CANARY`);
    expect(request).not.toHaveBeenCalled(); expect(command).not.toHaveBeenCalled();
    act(() => { callbacks.onSnapshot({ ...snapshot, aggregate_version: 8, items: [] }); callbacks.onState("connected"); });
    act(() => callbacks.onState("disconnected"));
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    act(() => callbacks.onState("revoked"));
    expect(screen.queryByRole("button", { name: "Скачать аварийный снимок" })).not.toBeInTheDocument();
    view.rerender(createElement(SceneExperience, { room: { ...room, id: "new" }, accessToken: "new-identity",
      api: { command } as unknown as SceneApi, realtimeFactory: transport }));
    act(() => callbacks.onState("disconnected"));
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(screen.queryByRole("button", { name: "Скачать аварийный снимок" })).not.toBeInTheDocument();
    expect(screen.getByText(/Нет подтверждённого локального снимка/)).toBeInTheDocument();
  } finally { view.unmount(); }
});

it("never offers the GM download to a guest after prolonged failure", async () => {
  vi.useFakeTimers();
  const transport: RealtimeFactory = options => { queueMicrotask(() => {
    options.onSnapshot({ room_id: "r", actor_session_id: "guest", aggregate_version: 1,
      event_cursor: 1, can_manage: false, scenes: [], scene: null, items: [] });
    options.onState("disconnected");
  }); return { close() {}, reconnect() {}, preview() {}, refresh: async () => false }; };
  const view = render(createElement(SceneExperience, { room: { ...room, can_manage: false },
    api: {} as SceneApi, realtimeFactory: transport }));
  try {
    await act(async () => { await vi.advanceTimersByTimeAsync(32000); });
    expect(screen.queryByRole("button", { name: "Скачать аварийный снимок" })).not.toBeInTheDocument();
  } finally { view.unmount(); }
});
