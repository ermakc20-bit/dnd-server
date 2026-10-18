import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CampaignHome } from "../features/campaigns/CampaignExperience";
import type { CampaignApi } from "../features/campaigns/api";
import { SceneExperience } from "../features/scene/SceneExperience";
import type { RealtimeFactory } from "../features/realtime/transport";
import type { SceneApi, SceneProjection } from "../features/scene/types";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("hides campaign preparation on phone transition and restores the same draft on desktop", async () => {
  vi.stubGlobal("innerWidth", 1440);
  const api = { listCampaigns: vi.fn().mockResolvedValue([]), createCampaign: vi.fn() };
  render(<CampaignHome accessToken="local-account" api={api as unknown as CampaignApi} />);
  fireEvent.click(await screen.findByRole("button", { name: "Создать кампанию" }));
  fireEvent.change(screen.getByLabelText("Название кампании"), { target: { value: "Сохранить черновик" } });
  vi.stubGlobal("innerWidth", 390); fireEvent(window, new Event("resize"));
  expect(screen.queryByRole("button", { name: "Сохранить кампанию" })).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Название кампании" })).not.toBeInTheDocument();
  expect(api.createCampaign).not.toHaveBeenCalled();
  vi.stubGlobal("innerWidth", 1440); fireEvent(window, new Event("resize"));
  expect(screen.getByRole("textbox", { name: "Название кампании" })).toHaveValue("Сохранить черновик");
  expect(screen.getByRole("button", { name: "Сохранить кампанию" })).toBeEnabled();
});

it("blocks every durable room-admin request while offline and connecting until snapshot resync", async () => {
  vi.stubGlobal("innerWidth", 1440);
  const room = { id: "r", campaign_id: "c", name: "Стол", is_locked: false, pin_enabled: false, can_manage: true, created_at: "" };
  const projection: SceneProjection = { room_id: "r", actor_session_id: "gm", aggregate_version: 1, event_cursor: 1,
    can_manage: true, scenes: [], scene: null, items: [] };
  const fetch = vi.fn().mockImplementation(async (url: string, init?: RequestInit) =>
    new Response(init?.method === "DELETE" ? null : JSON.stringify(url.endsWith("/participants")
      ? { participants: [{ id: "guest", display_name: "Игрок", role: "player" }] }
      : { room_id: "r", token: "local-invite", expires_at: "" }), { status: init?.method === "DELETE" ? 204 : 200 }));
  vi.stubGlobal("fetch", fetch);
  let offline = () => {}; let connecting = () => {}; let resync = () => {};
  const realtimeFactory: RealtimeFactory = options => {
    offline = () => options.onState("disconnected");
    connecting = () => options.onState("connecting");
    resync = () => { options.onSnapshot({ ...projection, aggregate_version: 2 }); options.onState("connected"); };
    queueMicrotask(() => { options.onSnapshot(projection); options.onState("connected"); });
    return { refresh: async () => true, reconnect() {}, preview() {}, close() {} };
  };
  const api = { projection: vi.fn(), command: vi.fn() } as unknown as SceneApi;
  render(<SceneExperience room={room} accessToken="local-account" api={api} realtimeFactory={realtimeFactory} />);
  fireEvent.click(await screen.findByRole("button", { name: "Участники" }));
  fireEvent.click(screen.getByRole("button", { name: "Показать участников" }));
  await screen.findByText("Игрок · игрок");
  fireEvent.change(screen.getByLabelText("PIN комнаты"), { target: { value: "1234" } });
  fetch.mockClear(); act(() => offline());
  expect(screen.getByText("Только чтение · последнее подтверждённое состояние")).toBeInTheDocument();
  const writes = ["Выпустить приглашение", "Перевыпустить", "Отозвать", "Сохранить PIN", "Убрать PIN", "Закрыть комнату", "Удалить"];
  for (const name of writes) fireEvent.click(screen.getByRole("button", { name }));
  expect(fetch).not.toHaveBeenCalled();
  for (const name of writes) expect(screen.getByRole("button", { name })).toBeDisabled();
  expect(screen.getByText("Игрок · игрок")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Показать участников" })).toBeEnabled();
  act(() => connecting());
  for (const name of writes) expect(screen.getByRole("button", { name })).toBeDisabled();
  act(() => resync());
  expect(screen.getByLabelText("PIN комнаты")).toHaveValue("1234");
  for (const name of writes) expect(screen.getByRole("button", { name })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Выпустить приглашение" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/rooms/r/invites", expect.objectContaining({ method: "POST" })));
});
