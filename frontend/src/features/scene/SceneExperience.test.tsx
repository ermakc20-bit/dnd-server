import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SceneExperience } from "./SceneExperience";
import type { SceneApi, SceneProjection } from "./types";
import { testTransport } from "../realtime/testTransport";
import type { RealtimeOptions } from "../realtime/transport";

const empty: SceneProjection = { room_id: "r", actor_session_id: "gm", aggregate_version: 0,
  event_cursor: 0, can_manage: true, scenes: [], scene: null, items: [] };
const room = { id: "r", campaign_id: "c", name: "Стол", is_locked: false, pin_enabled: false,
  created_at: "2026-10-11T00:00:00Z", can_manage: true };

const transformProjection: SceneProjection = { ...empty, aggregate_version: 7, event_cursor: 7,
  scenes: [{ id: "s", name: "Таверна" }],
  scene: { id: "s", name: "Таверна", width: 4096, height: 4096, grid_size: 64,
    grid_enabled: true, snap_enabled: true, unit_size: 5, unit_label: "фут" },
  items: [{ id: "token", kind: "token", name: "Страж", asset_id: null,
    x: 192, y: 128, width: 64, height: 64, rotation: 0, z_index: 0, visibility: "everyone",
    is_locked: false, owner_participant_id: null, can_transform: true }], ability_presentations: [] };

function renderTransform(projection = transformProjection) {
  let connection!: RealtimeOptions;
  const command = vi.fn().mockResolvedValue({ status: "accepted" });
  const api = { command } as unknown as SceneApi;
  render(<SceneExperience room={room} accessToken="credential" api={api}
    realtimeFactory={options => { connection = options; return { refresh: async () => true,
      reconnect: vi.fn(), preview: vi.fn(), close: vi.fn() }; }}
    rendererFactory={async () => ({ render: vi.fn(), destroy: vi.fn() })} />);
  act(() => { connection.onSnapshot(projection); connection.onState("connected"); });
  fireEvent.click(screen.getByRole("button", { name: "Сцена" }));
  fireEvent.change(screen.getByLabelText("Выбранный объект"), { target: { value: "token" } });
  return { command, connection };
}

describe("SceneExperience", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("opens native card creation while keeping the map-first table visible", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ cards: [], has_more: false }) }));
    const api = { projection: vi.fn().mockResolvedValue(empty), command: vi.fn() } as unknown as SceneApi;
    render(<SceneExperience room={room} api={api} realtimeFactory={testTransport(api)} />);
    fireEvent.click(await screen.findByRole("button", { name: "Карточки" }));
    expect(await screen.findByRole("button", { name: "Новая карточка" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Новая карточка" }));
    expect(screen.getByLabelText("Название карточки")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Игровая сцена" })).toBeInTheDocument();
  });
  it("creates the first scene with server command identity/version and displays the ack", async () => {
    const api = { projection: vi.fn().mockResolvedValueOnce(empty).mockResolvedValue({
      ...empty, aggregate_version: 1, event_cursor: 1,
      scenes: [{ id: "s", name: "Таверна" }],
      scene: { id: "s", name: "Таверна", width: 4096, height: 4096, grid_size: 64,
        grid_enabled: true, snap_enabled: true, unit_size: 5, unit_label: "фут" },
    }), command: vi.fn().mockResolvedValue({ status: "accepted", aggregate_version: 1 }) } as unknown as SceneApi;
    render(<SceneExperience room={room} accessToken="credential" api={api}
      realtimeFactory={testTransport(api)}
      rendererFactory={async () => ({ render: vi.fn(), destroy: vi.fn() })} />);
    fireEvent.click(await screen.findByRole("button", { name: "Добавить сцену" }));
    fireEvent.change(screen.getByLabelText("Название сцены"), { target: { value: "Таверна" } });
    fireEvent.click(screen.getByRole("button", { name: "Создать сцену" }));
    await waitFor(() => expect(api.command).toHaveBeenCalledWith(expect.objectContaining({
      command_id: expect.any(String), room_id: "r", actor_session_id: "gm",
      expected_aggregate_version: 0, type: "scene.create", payload: { name: "Таверна" },
    }), "credential"));
    expect(await screen.findByText("0 объектов")).toBeInTheDocument();
    expect(api.projection).toHaveBeenCalledTimes(2);
  });

  it("shows preparation to a guest, never exposes GM controls and keeps failed snapshots read-only", async () => {
    const api = { projection: vi.fn().mockResolvedValueOnce({ ...empty, can_manage: false })
      .mockRejectedValue(new Error("Сцена недоступна")), command: vi.fn() } as unknown as SceneApi;
    render(<SceneExperience room={{ ...room, can_manage: false }} api={api} realtimeFactory={testTransport(api)} />);
    expect(await screen.findByText("Мастер готовит сцену")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Создать сцену" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Обновить сцену" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Сцена недоступна");
    expect(screen.getByText(/Только чтение/)).toBeInTheDocument();
    expect(api.command).not.toHaveBeenCalled();
  });

  it("uses the existing participant API to assign a player by name", async () => {
    const item = { id: "token", kind: "token", name: "Страж", asset_id: null,
      x: 0, y: 0, width: 64, height: 64, rotation: 0, z_index: 0, visibility: "everyone",
      is_locked: false, owner_participant_id: null, can_transform: true };
    const api = { projection: vi.fn().mockResolvedValue({ ...empty, items: [item],
      scene: { id: "s", name: "Таверна", width: 4096, height: 4096, grid_size: 64,
        grid_enabled: true, snap_enabled: true, unit_size: 5, unit_label: "фут" } }),
      command: vi.fn().mockResolvedValue({ status: "accepted" }) } as unknown as SceneApi;
    const participantApi = { listParticipants: vi.fn().mockResolvedValue([{ id: "player-id",
      campaign_id: "c", room_id: "r", role: "player", display_name: "Ирина", user_id: null,
      guest_session_id: "guest-id", joined_at: "2026-10-11T00:00:00Z", removed_at: null }]) };
    render(<SceneExperience room={room} accessToken="credential" api={api} participantApi={participantApi}
      realtimeFactory={testTransport(api)}
      rendererFactory={async () => ({ render: vi.fn(), destroy: vi.fn() })} />);
    fireEvent.click(await screen.findByRole("button", { name: "Сцена" }));
    fireEvent.change(await screen.findByLabelText("Выбранный объект"), { target: { value: "token" } });
    fireEvent.click(screen.getByRole("button", { name: "Загрузить игроков" }));
    await screen.findByRole("option", { name: "Ирина" });
    expect(participantApi.listParticipants).toHaveBeenCalledWith("credential", "r");
    fireEvent.change(screen.getByLabelText("Управление токеном"), { target: { value: "player-id" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить трансформацию" }));
    await waitFor(() => expect(api.command).toHaveBeenCalledWith(expect.objectContaining({
      type: "item.update", payload: expect.objectContaining({ item_id: "token", owner_participant_id: "player-id" }),
    }), "credential"));
  });

  it("preserves a transform draft across an unrelated ability snapshot and submits the current version", async () => {
    const { command, connection } = renderTransform();
    fireEvent.change(screen.getByLabelText("X"), { target: { value: "256" } });
    expect(screen.getByRole("button", { name: "Сохранить трансформацию" })).toBeEnabled();
    act(() => connection.onSnapshot({ ...transformProjection, aggregate_version: 8, event_cursor: 8,
      ability_presentations: [{ id: "area", geometry: { schema_version: 1, shape: "circle",
        origin: { x: 256, y: 180 }, rotation: 0, radius: 128, length: 0, width: 0, angle: 0,
        color: "#ff7448" }, created_at: "2026-10-15T00:00:00Z", can_clear: true, affected_item_ids: [] }] }));
    expect(screen.getByLabelText("X")).toHaveValue(256);
    expect(command).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить трансформацию" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(1));
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ type: "item.update",
      expected_aggregate_version: 8, payload: expect.objectContaining({ item_id: "token", x: 256 }) }), "credential");
  });

  it.each([
    { field: "x", value: 352 }, { field: "y", value: 224 }, { field: "width", value: 96 },
    { field: "height", value: 128 }, { field: "rotation", value: 45 }, { field: "name", value: "Новый страж" },
    { field: "z_index", value: 2 }, { field: "is_locked", value: true },
    { field: "visibility", value: "gm_only" }, { field: "owner_participant_id", value: "new-player" },
  ])("refreshes the transform form when the selected item's canonical $field changes", ({ field, value }) => {
    const { command, connection } = renderTransform();
    fireEvent.change(screen.getByLabelText("X"), { target: { value: "256" } });
    act(() => connection.onSnapshot({ ...transformProjection, aggregate_version: 8, event_cursor: 8,
      items: [{ ...transformProjection.items[0], [field]: value }] }));
    expect(screen.getByLabelText("X")).toHaveValue(field === "x" ? 352 : 192);
    if (field === "y") expect(screen.getByLabelText("Y")).toHaveValue(224);
    if (field === "width") expect(screen.getByLabelText("Ширина")).toHaveValue(96);
    if (field === "height") expect(screen.getByLabelText("Высота")).toHaveValue(128);
    if (field === "rotation") expect(screen.getByLabelText("Поворот, °")).toHaveValue(45);
    if (field === "name") expect(screen.getByLabelText("Название объекта")).toHaveValue("Новый страж");
    if (field === "z_index") expect(screen.getByLabelText("Слой")).toHaveValue(2);
    if (field === "is_locked") expect(screen.getByLabelText("Заблокирован")).toBeChecked();
    if (field === "visibility") expect(screen.getByLabelText("Видимость")).toHaveValue("gm_only");
    if (field === "owner_participant_id") expect(screen.getByLabelText("Управление токеном")).toHaveValue("new-player");
    expect(command).not.toHaveBeenCalled();
  });

  it("loads the newly selected item's values instead of the previous item's draft", () => {
    const other = { ...transformProjection.items[0], id: "other-token", x: 448, y: 320, name: "Другой страж" };
    const { command } = renderTransform({ ...transformProjection, items: [...transformProjection.items, other] });
    fireEvent.change(screen.getByLabelText("X"), { target: { value: "256" } });
    fireEvent.change(screen.getByLabelText("Выбранный объект"), { target: { value: other.id } });
    expect(screen.getByLabelText("X")).toHaveValue(448);
    expect(screen.getByLabelText("Y")).toHaveValue(320);
    expect(screen.getByLabelText("Название объекта")).toHaveValue("Другой страж");
    expect(command).not.toHaveBeenCalled();
  });

  it.each(["disconnected", "connecting"] as const)("does not submit a preserved draft while %s", state => {
    const { command, connection } = renderTransform();
    fireEvent.change(screen.getByLabelText("X"), { target: { value: "256" } });
    act(() => { connection.onSnapshot({ ...transformProjection, aggregate_version: 8 }); connection.onState(state); });
    expect(screen.getByRole("button", { name: "Сохранить трансформацию" })).toBeDisabled();
    fireEvent.submit(screen.getByLabelText("X").closest("form")!);
    expect(command).not.toHaveBeenCalled();
  });

  it("keeps a preserved draft disabled when transform permission is withdrawn", () => {
    const { command, connection } = renderTransform();
    fireEvent.change(screen.getByLabelText("X"), { target: { value: "256" } });
    act(() => connection.onSnapshot({ ...transformProjection, aggregate_version: 8,
      items: [{ ...transformProjection.items[0], can_transform: false }] }));
    expect(screen.getByLabelText("X")).toHaveValue(256);
    const save = screen.getByRole("button", { name: "Сохранить трансформацию" });
    expect(save).toBeDisabled(); fireEvent.click(save);
    expect(command).not.toHaveBeenCalled();
  });

  it("does not send another transform while the first acknowledgement is pending", async () => {
    const { command, connection } = renderTransform();
    let acknowledge!: (result: { status: string }) => void;
    command.mockImplementationOnce(() => new Promise(resolve => { acknowledge = resolve; }));
    fireEvent.change(screen.getByLabelText("X"), { target: { value: "256" } });
    const form = screen.getByLabelText("X").closest("form")!;
    fireEvent.submit(form);
    act(() => connection.onSnapshot({ ...transformProjection, aggregate_version: 8 }));
    expect(screen.getByRole("button", { name: "Сохранить трансформацию" })).toBeDisabled();
    fireEvent.submit(screen.getByLabelText("X").closest("form")!);
    expect(command).toHaveBeenCalledTimes(1);
    await act(async () => acknowledge({ status: "accepted" }));
  });
});
