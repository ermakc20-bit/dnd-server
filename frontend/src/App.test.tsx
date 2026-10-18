import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Session } from "@supabase/supabase-js";

import { AppView } from "./App";
import { VttShell } from "./components/VttShell";

vi.mock("./features/realtime/transport", async () => {
  const { sceneApi } = await import("./features/scene/api");
  const { testTransport } = await import("./features/realtime/testTransport");
  return { connectRoom: testTransport(sceneApi) };
});

describe("AppView", () => {
  it("renders the session loading state", () => {
    render(<AppView auth={{ status: "loading", session: null }} />);

    expect(screen.getByText("Проверяем сессию…")).toBeInTheDocument();
  });

  it("explains missing public configuration", () => {
    render(<AppView auth={{ status: "misconfigured", session: null }} />);

    expect(screen.getByRole("heading", { name: "Supabase ещё не подключён" })).toBeInTheDocument();
  });

  it("renders anonymous landing", () => {
    render(<AppView auth={{ status: "anonymous", session: null }} />);

    expect(screen.getByRole("heading", { name: "Вход для мастера" })).toBeInTheDocument();
  });

  it("renders the authenticated workspace shell", () => {
    render(<VttShell userLabel="Гейм-мастер" />);

    expect(screen.getByRole("main")).toHaveClass("app-shell");
    expect(screen.getByRole("region", { name: "Игровая сцена" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Библиотека материалов" })).toBeInTheDocument();
  });

  it("opens the selected campaign room in the actual scene screen", async () => {
    const room = { id: "room-scene", campaign_id: "campaign-scene", name: "Стол кампании",
      is_locked: false, pin_enabled: false, can_manage: false, created_at: "2026-10-11T00:00:00Z" };
    const mockFetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => new Response(JSON.stringify(
      String(url).endsWith("/campaigns") ? [{ id: "campaign-scene", owner_user_id: "gm", name: "Кампания",
        system_id: "neutral", status: "active", created_at: room.created_at, rooms: [room] }] : {
        room_id: room.id, actor_session_id: "player", aggregate_version: 0, event_cursor: 0,
        can_manage: false, scenes: [], scene: null, items: [],
      }), { status: 200 }));
    try {
      render(<AppView auth={{ status: "authenticated", session: { access_token: "account" } as Session }} />);
      fireEvent.click(await screen.findByRole("button", { name: "Открыть стол Стол кампании" }));
      expect(await screen.findByText("Мастер готовит сцену")).toBeInTheDocument();
      expect(mockFetch).toHaveBeenCalledWith("/api/v1/rooms/room-scene/scene", expect.objectContaining({
        headers: { Authorization: "Bearer account" }, credentials: "same-origin",
      }));
    } finally { mockFetch.mockRestore(); }
  });
});
