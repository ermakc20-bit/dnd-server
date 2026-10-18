import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SceneExperience } from "../features/scene/SceneExperience";
import type { SceneApi, SceneProjection } from "../features/scene/types";
import type { RealtimeOptions } from "../features/realtime/transport";
import { cardApi } from "../features/cards/api";
import { blankCard } from "../features/cards/types";

const room = { id: "r", campaign_id: "c", name: "Стол", is_locked: false, pin_enabled: false,
  can_manage: true, created_at: "" };
const initial: SceneProjection = { room_id: "r", actor_session_id: "gm", aggregate_version: 7,
  event_cursor: 7, can_manage: true, scenes: [{ id: "s", name: "Сцена" }],
  scene: { id: "s", name: "Сцена", width: 4096, height: 4096, grid_size: 64,
    grid_enabled: true, snap_enabled: true, unit_size: 5, unit_label: "фут" },
  items: [{ id: "token", kind: "token", name: "Токен героя", card_id: "hero-card", asset_id: null,
    x: 192, y: 128, width: 64, height: 64, rotation: 0, z_index: 0, visibility: "everyone",
    is_locked: false, owner_participant_id: null, can_transform: true }], annotations: [] };
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function tap(surface: HTMLElement, x: number, y: number) {
  for (const type of ["pointerdown", "pointerup"]) {
    const event = new MouseEvent(type, { clientX: x, clientY: y, bubbles: true, button: 0 });
    Object.defineProperty(event, "pointerType", { value: "touch" }); fireEvent(surface, event);
  }
}

it("connects the tool icon, cursor, gesture, server acknowledgement and Escape without remounting the map", async () => {
  let complete!: (result: { status: string }) => void;
  const command = vi.fn().mockImplementation(() => new Promise(resolve => { complete = resolve; }));
  const confirmed: SceneProjection = { ...initial, aggregate_version: 8, event_cursor: 8,
    annotations: [{ id: "line", kind: "line", points: [{ x: 100, y: 100 }, { x: 200, y: 100 }],
      label: "Метка", visibility: "everyone", owner_participant_id: "gm", can_edit: true }] };
  const factory = vi.fn().mockResolvedValue({ render: vi.fn(), destroy: vi.fn() });
  render(<SceneExperience room={room} api={{ command } as unknown as SceneApi} rendererFactory={factory}
    realtimeFactory={options => {
      queueMicrotask(() => { options.onSnapshot(initial); options.onState("connected"); });
      return { refresh: async () => { options.onSnapshot(confirmed); return true; }, reconnect: vi.fn(), preview: vi.fn(), close: vi.fn() };
    }} />);
  const line = await screen.findByRole("button", { name: "Линия" });
  fireEvent.click(line);
  const surface = screen.getByRole("region", { name: "Карта и токены" });
  expect(line).toHaveAttribute("aria-pressed", "true"); expect(surface).toHaveAttribute("data-tool", "line");
  expect(surface).toHaveFocus();
  tap(surface, 100, 100); expect(command).not.toHaveBeenCalled();
  expect(screen.getByText("Выберите вторую точку")).toBeInTheDocument();
  tap(surface, 200, 100);
  await waitFor(() => expect(command).toHaveBeenCalledTimes(1));
  expect(command.mock.calls[0][0]).toMatchObject({ type: "annotation.create", expected_aggregate_version: 7,
    payload: { kind: "line", points: [{ x: 100, y: 100 }, { x: 200, y: 100 }], visibility: "everyone" } });
  expect(line).toBeDisabled();
  expect(screen.getByRole("button", { name: "Линейка" })).toBeEnabled();
  tap(surface, 300, 100); tap(surface, 400, 100); expect(command).toHaveBeenCalledTimes(1);
  await act(async () => complete({ status: "accepted" }));
  fireEvent.keyDown(surface, { key: "r" });
  expect(surface).toHaveAttribute("data-tool", "ruler");
  fireEvent.keyDown(surface, { key: "Enter" }); fireEvent.keyDown(surface, { key: "ArrowRight" }); fireEvent.keyDown(surface, { key: "Enter" });
  expect(screen.getByLabelText("Расстояние")).toHaveTextContent("фут");
  fireEvent.keyDown(surface, { key: "Escape" });
  expect(screen.queryByLabelText("Расстояние")).not.toBeInTheDocument();
  fireEvent.keyDown(surface, { key: "Escape" }); expect(surface).toHaveAttribute("data-tool", "select");
  expect(factory).toHaveBeenCalledTimes(1);
});

it("opens the selected token's authorized card outside the current library page and preserves the edit workspace", async () => {
  const card = { ...blankCard(), id: "hero-card", name: "Савелий", version: 1, campaign_id: "c", room_id: "r",
    created_at: "", updated_at: "", can_edit_structure: true, can_edit_current: true, can_export: false,
    resources: [{ key: "hp", label: "Здоровье", current: 36, max: 36, color: null, visibility: "everyone" as const }] };
  const get = vi.spyOn(cardApi, "get").mockResolvedValue(card);
  vi.spyOn(cardApi, "list").mockResolvedValue({ cards: [], offset: 0, limit: 20, has_more: false });
  const factory = vi.fn().mockResolvedValue({ render: vi.fn(), destroy: vi.fn() });
  let receive!: RealtimeOptions["onSnapshot"];
  render(<SceneExperience room={room} accessToken="local-only" api={{ command: vi.fn() } as unknown as SceneApi}
    rendererFactory={factory} realtimeFactory={(options: RealtimeOptions) => {
      receive = options.onSnapshot;
      queueMicrotask(() => { options.onSnapshot(initial); options.onState("connected"); });
      return { refresh: async () => true, reconnect: vi.fn(), preview: vi.fn(), close: vi.fn() };
    }} />);
  const surface = await screen.findByRole("region", { name: "Карта и токены" }); tap(surface, 224, 160);
  const context = within(screen.getByRole("toolbar", { name: "Выбранный объект на карте" }));
  fireEvent.click(context.getByRole("button", { name: "Карточка" }));
  expect(await screen.findByRole("heading", { name: "Савелий" })).toHaveFocus();
  expect(get).toHaveBeenCalledWith("r", "hero-card", "local-only");
  expect(screen.getByLabelText("Текущее: Здоровье")).toHaveValue(36);
  fireEvent.click(screen.getByRole("button", { name: "Линия" }));
  await act(async () => receive({ ...initial, aggregate_version: 8, event_cursor: 8 }));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  expect(await screen.findByRole("heading", { name: "Савелий" })).toBeInTheDocument();
  expect(surface).toHaveFocus();
  fireEvent.keyDown(surface, { key: "Escape" });
  expect(surface).toHaveAttribute("data-tool", "select");
  expect(screen.getByRole("button", { name: "Карточки" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Редактировать карточку" }));
  const name = screen.getByLabelText("Название карточки"); fireEvent.change(name, { target: { value: "Мой черновик" } });
  fireEvent.keyDown(name, { key: "r" }); expect(surface).toHaveAttribute("data-tool", "select");
  fireEvent.click(screen.getByRole("button", { name: "Сцена" }));
  fireEvent.click(screen.getByRole("button", { name: "Карточки" }));
  expect(screen.getByLabelText("Название карточки")).toHaveValue("Мой черновик");
  expect(factory).toHaveBeenCalledTimes(1);
});
