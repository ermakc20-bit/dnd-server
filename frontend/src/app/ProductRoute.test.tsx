import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Session } from "@supabase/supabase-js";
import { AppView } from "../App";

vi.mock("../features/realtime/transport", async () => {
  const { sceneApi } = await import("../features/scene/api");
  const { testTransport } = await import("../features/realtime/testTransport");
  return { connectRoom: testTransport(sceneApi) };
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.history.replaceState(null, "", "/"); });
const room = { id: "11111111-1111-4111-8111-111111111111", campaign_id: "campaign", name: "Стол после обновления",
  is_locked: false, pin_enabled: false, can_manage: false, created_at: "2026-10-14T00:00:00Z" };
const auth = { status: "authenticated" as const, session: { access_token: "local-account" } as Session };

it("restores only an authorized room from its native route after a refresh", async () => {
  window.history.replaceState(null, "", `/rooms/${room.id}`);
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async url => new Response(JSON.stringify(
    String(url).endsWith("/campaigns") ? [{ id: room.campaign_id, name: "Кампания", rooms: [room] }] : {
      room_id: room.id, actor_session_id: "player", aggregate_version: 0, event_cursor: 0,
      can_manage: false, scenes: [], scene: null, items: [],
    }), { status: 200 }));
  const view = render(<AppView auth={auth} />);
  expect(await screen.findByRole("heading", { name: room.name })).toBeInTheDocument();
  expect(await screen.findByText("Мастер готовит сцену")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Создать сцену" })).not.toBeInTheDocument();
  view.unmount();
  render(<AppView auth={auth} />);
  expect(await screen.findByRole("heading", { name: room.name })).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("/api/v1/campaigns", expect.objectContaining({ headers: { Authorization: "Bearer local-account" } }));
  window.history.replaceState(null, "", "/join/%E0%A4%A");
  fireEvent(window, new PopStateEvent("popstate"));
  expect(await screen.findByRole("heading", { name: "Страница не найдена" })).toBeInTheDocument();
});
