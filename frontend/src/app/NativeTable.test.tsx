import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SceneExperience } from "../features/scene/SceneExperience";
import { testTransport } from "../features/realtime/testTransport";
import type { SceneApi, SceneProjection } from "../features/scene/types";
import { blankCard } from "../features/cards/types";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const room = { id: "r", campaign_id: "c", name: "Стол", is_locked: false, pin_enabled: false,
  can_manage: true, created_at: "2026-10-14T00:00:00Z" };
const snapshot: SceneProjection = { room_id: "r", actor_session_id: "gm", aggregate_version: 1,
  event_cursor: 1, can_manage: true, scenes: [{ id: "s", name: "Карта" }], items: [],
  scene: { id: "s", name: "Карта", width: 4096, height: 4096, grid_size: 64,
    grid_enabled: true, snap_enabled: true, unit_size: 5, unit_label: "фут" } };

it("preserves an edited card across phone resize and keeps the desktop map stable while switching panels", async () => {
  const fetch = vi.fn().mockImplementation(async (url: string) => ({ ok: true, json: async () =>
    url.endsWith("/invites") ? { room_id: "r", token: "native-local-invite", expires_at: "2026-10-15T00:00:00Z" }
      : url.endsWith("/participants") ? { participants: [] } : { cards: [], jobs: [], entries: [], has_more: false } }));
  vi.stubGlobal("fetch", fetch);
  const api = { projection: vi.fn().mockResolvedValue(snapshot), command: vi.fn() } as unknown as SceneApi;
  const destroy = vi.fn(); const factory = vi.fn().mockResolvedValue({ render: vi.fn(), destroy });
  render(<SceneExperience room={room} accessToken="local-account" api={api} realtimeFactory={testTransport(api)} rendererFactory={factory} />);
  fireEvent.click(await screen.findByRole("button", { name: "Карточки" }));
  fireEvent.click(await screen.findByRole("button", { name: "Новая карточка" }));
  fireEvent.change(screen.getByLabelText("Название карточки"), { target: { value: "Сохранённый черновик" } });
  vi.stubGlobal("innerWidth", 390); fireEvent.resize(window);
  expect(screen.queryByRole("textbox", { name: "Название карточки" })).not.toBeInTheDocument();
  vi.stubGlobal("innerWidth", 1440); fireEvent.resize(window);
  expect(screen.getByLabelText("Название карточки")).toHaveValue("Сохранённый черновик");
  const mountsAfterResize = factory.mock.calls.length;
  const disposalsAfterResize = destroy.mock.calls.length;
  expect(mountsAfterResize).toBe(2); expect(disposalsAfterResize).toBe(1);
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.getByRole("button", { name: "Карточки" })).toHaveFocus();
  expect(screen.queryByRole("textbox", { name: "Название карточки" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Карточки" }));
  expect(screen.getByLabelText("Название карточки")).toHaveValue("Сохранённый черновик");
  fireEvent.click(screen.getByRole("button", { name: "Сцена" }));
  fireEvent.click(screen.getByRole("button", { name: "Карточки" }));
  expect(screen.getByLabelText("Название карточки")).toHaveValue("Сохранённый черновик");
  fireEvent.click(screen.getByRole("button", { name: "Участники" }));
  fireEvent.click(screen.getByRole("button", { name: "Выпустить приглашение" }));
  expect(await screen.findByText(/\/join\/native-local-invite$/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Показать участников" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/rooms/r/participants", expect.anything()));
  expect(screen.getByRole("region", { name: "Игровая сцена" })).toBeInTheDocument();
  expect(factory).toHaveBeenCalledTimes(mountsAfterResize); expect(destroy).toHaveBeenCalledTimes(disposalsAfterResize);
});

it("offers phone resources, dice and journal without map or preparation even for a GM", async () => {
  vi.stubGlobal("innerWidth", 390);
  const card = { ...blankCard(), id: "hero", name: "Герой", version: 1, campaign_id: "c", room_id: "r",
    created_at: "", updated_at: "", can_edit_structure: true, can_edit_current: true, can_export: true,
    resources: [{ key: "hp", label: "HP", current: 10, max: 20, color: null, visibility: "everyone" }] };
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => ({ ok: true, json: async () =>
    url.includes("/cards") ? { cards: [card], has_more: false } : { entries: [], next_cursor: null } })));
  const api = { projection: vi.fn().mockResolvedValue(snapshot), command: vi.fn().mockResolvedValue({ status: "accepted" }) } as unknown as SceneApi;
  const factory = vi.fn();
  render(<SceneExperience room={room} accessToken="local-account" api={api} realtimeFactory={testTransport(api)} rendererFactory={factory} />);
  fireEvent.click(await screen.findByRole("button", { name: /Герой/ }));
  expect(screen.queryByRole("button", { name: "Новая карточка" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Редактировать карточку" })).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Игровая сцена" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Участники" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Текущее: HP"), { target: { value: "7" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить HP" }));
  await waitFor(() => expect(api.command).toHaveBeenCalledWith(expect.objectContaining({ type: "card.resource", payload: { card_id: "hero", resource_key: "hp", current: 7 } }), "local-account"));
  fireEvent.click(screen.getByRole("button", { name: "Кубы и журнал" }));
  fireEvent.change(screen.getByLabelText("Выражение кубов"), { target: { value: "2d6+3" } });
  fireEvent.click(screen.getByRole("button", { name: "Бросить кубы" }));
  await waitFor(() => expect(api.command).toHaveBeenCalledWith(expect.objectContaining({ type: "dice.roll", payload: { expression: "2d6+3", visibility: "everyone" } }), "local-account"));
  expect(screen.getByRole("button", { name: "Обновить журнал" })).toBeInTheDocument();
  expect(factory).not.toHaveBeenCalled();
});
