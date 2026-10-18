import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SceneExperience } from "../scene/SceneExperience";
import type { SceneApi } from "../scene/types";

class Socket {
  static instances: Socket[] = [];
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  send = vi.fn(); close = vi.fn();
  constructor(public url: string) { Socket.instances.push(this); }
}

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); Socket.instances = []; });

it("counts uncapped connect attempts, retains failure start until full sync, and offers GM diagnostics at exactly 30 seconds", async () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-15T12:00:00Z"));
  vi.stubGlobal("WebSocket", Socket);
  let available = true;
  const request = vi.fn(async () => ({ ok: available, status: available ? 200 : 503,
    json: async () => ({ ticket: "fixture-ticket" }) }));
  vi.stubGlobal("fetch", request);
  const snapshot = { room_id: "r", actor_session_id: "private-session", aggregate_version: 3,
    event_cursor: 3, can_manage: true, scenes: [], scene: null, items: [] };
  const view = render(<SceneExperience room={{ id: "r", campaign_id: "c", name: "Стол", is_locked: false,
    pin_enabled: false, created_at: "", can_manage: true }} api={{ command: vi.fn() } as unknown as SceneApi} />);
  try {
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => Socket.instances[0].onmessage?.({ data: JSON.stringify({ type: "sync", snapshot, events: [] }) }));
    available = false;
    act(() => Socket.instances[0].onclose?.({ code: 1006 }));
    await act(async () => { await vi.advanceTimersByTimeAsync(29999); });
    expect(screen.getByText(/Переподключение · попытка/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Скачать аварийный снимок" })).not.toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.getByRole("button", { name: "Скачать аварийный снимок" })).toBeEnabled();
    const attempts = request.mock.calls.length;
    expect(attempts).toBeGreaterThan(10);
    expect(screen.getByText(`Переподключение · попытка ${attempts - 1}`)).toBeInTheDocument();
    available = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    act(() => Socket.instances.at(-1)?.onopen?.());
    expect(screen.getByRole("button", { name: "Скачать аварийный снимок" })).toBeEnabled();
    act(() => Socket.instances.at(-1)?.onmessage?.({ data: JSON.stringify({ type: "heartbeat", presence_count: 1 }) }));
    expect(screen.getByRole("button", { name: "Скачать аварийный снимок" })).toBeEnabled();
    act(() => Socket.instances.at(-1)?.onmessage?.({ data: JSON.stringify({ type: "sync",
      snapshot: { ...snapshot, aggregate_version: 4 }, events: [] }) }));
    expect(screen.queryByRole("button", { name: "Скачать аварийный снимок" })).not.toBeInTheDocument();
    act(() => Socket.instances.at(-1)?.onclose?.({ code: 1006 }));
    await act(async () => { await vi.advanceTimersByTimeAsync(29999); });
    expect(screen.queryByRole("button", { name: "Скачать аварийный снимок" })).not.toBeInTheDocument();
  } finally { view.unmount(); }
});

it("keeps the last snapshot read-only after disconnect and clears it on revoke", async () => {
  vi.stubGlobal("WebSocket", Socket);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ticket: "single-use-ticket" }) }));
  const snapshot = { room_id: "r", actor_session_id: "gm", aggregate_version: 3,
    event_cursor: 3, can_manage: true, scenes: [], scene: null, items: [] };
  const api = { projection: vi.fn().mockResolvedValue(snapshot), command: vi.fn() } as unknown as SceneApi;
  render(<SceneExperience room={{ id: "r", campaign_id: "c", name: "Стол", is_locked: false,
    pin_enabled: false, created_at: "", can_manage: true }} api={api} />);
  await waitFor(() => expect(Socket.instances).toHaveLength(1));
  const ws = Socket.instances[0];
  expect(ws.url).not.toContain("ticket");
  act(() => ws.onopen?.());
  act(() => ws.onmessage?.({ data: JSON.stringify({ type: "sync", snapshot, events: [] }) }));
  expect(await screen.findByText("0 объектов")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Сцена" }));
  act(() => ws.onclose?.({ code: 1006 }));
  expect(screen.getByText("Только чтение · последнее подтверждённое состояние")).toBeInTheDocument();
  expect(screen.getByLabelText("Нет связи")).toHaveAttribute("title", expect.stringContaining("Последняя синхронизация:"));
  expect(screen.getByRole("button", { name: "Создать сцену" })).toBeDisabled();
  expect(screen.getByText("0 объектов")).toBeInTheDocument();
  await waitFor(() => expect(Socket.instances).toHaveLength(2));
  act(() => Socket.instances[1].onopen?.());
  expect(screen.getByRole("button", { name: "Создать сцену" })).toBeDisabled();
  act(() => Socket.instances[1].onmessage?.({ data: JSON.stringify({ type: "sync",
    snapshot: { ...snapshot, aggregate_version: 4, event_cursor: 4 }, events: [] }) }));
  expect(screen.getByText("0 объектов")).toBeInTheDocument();
  expect(screen.queryByText("Только чтение · последнее подтверждённое состояние")).not.toBeInTheDocument();
  act(() => Socket.instances[1].onclose?.({ code: 4403 }));
  expect(screen.queryByText("0 объектов")).not.toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Доступ к комнате отозван");
});

it("automatically recovers after more than ten failed attempts and stays read-only until resync", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", Socket);
  let available = true;
  const request = vi.fn(async () => ({ ok: available, status: available ? 200 : 503,
    json: async () => ({ ticket: "single-use-ticket" }) }));
  vi.stubGlobal("fetch", request);
  const snapshot = { room_id: "r", actor_session_id: "gm", aggregate_version: 3,
    event_cursor: 3, can_manage: true, scenes: [], scene: null, items: [] };
  const api = { projection: vi.fn(), command: vi.fn() } as unknown as SceneApi;
  const view = render(<SceneExperience room={{ id: "r", campaign_id: "c", name: "Стол", is_locked: false,
    pin_enabled: false, created_at: "", can_manage: true }} api={api} />);
  try {
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    const first = Socket.instances[0];
    act(() => first.onopen?.());
    act(() => first.onmessage?.({ data: JSON.stringify({ type: "sync", snapshot, events: [] }) }));
    fireEvent.click(screen.getByRole("button", { name: "Сцена" }));
    fireEvent.change(screen.getByLabelText("Название сцены"), { target: { value: "Следующая сцена" } });
    expect(screen.getByRole("button", { name: "Создать сцену" })).toBeEnabled();

    available = false;
    act(() => first.onclose?.({ code: 1006 }));
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
    expect(request.mock.calls.length).toBeGreaterThan(12);
    expect(screen.getByText("0 объектов")).toBeInTheDocument();
    expect(screen.getByText("Только чтение · последнее подтверждённое состояние")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Создать сцену" })).toBeDisabled();
    expect(Socket.instances).toHaveLength(1);

    available = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(Socket.instances).toHaveLength(2);
    const recovered = Socket.instances[1];
    act(() => recovered.onopen?.());
    expect(screen.getByRole("button", { name: "Создать сцену" })).toBeDisabled();
    expect(recovered.send).toHaveBeenCalledWith(JSON.stringify({ type: "subscribe",
      ticket: "single-use-ticket", cursor: 3 }));
    act(() => recovered.onmessage?.({ data: JSON.stringify({ type: "sync",
      snapshot: { ...snapshot, aggregate_version: 4, event_cursor: 4 }, events: [] }) }));
    expect(screen.getByText("0 объектов")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Создать сцену" })).toBeEnabled();
    expect(api.command).not.toHaveBeenCalled();

    act(() => recovered.onclose?.({ code: 4403 }));
    const attemptsAtRevoke = request.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
    expect(request).toHaveBeenCalledTimes(attemptsAtRevoke);
    expect(screen.getByRole("alert")).toHaveTextContent("Доступ к комнате отозван");
    expect(screen.queryByText("0 объектов")).not.toBeInTheDocument();
  } finally { view.unmount(); }
});
