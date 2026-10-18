import type { ItemPreview } from "../../renderer/viewport";
import type { SceneProjection } from "../scene/types";

export type ConnectionState = "connecting" | "connected" | "disconnected" | "revoked";
export interface ConnectionDiagnostics {
  attempt: number; lastConfirmedSyncAt: string | null; failureStartedAt: number | null;
}
export interface RealtimeOptions {
  roomId: string; accessToken?: string;
  onSnapshot(snapshot: SceneProjection): void;
  onState(state: ConnectionState, error?: string): void;
  onPreview(preview: ItemPreview | null): void;
  onPresence(count: number): void;
  onDiagnostics?(diagnostics: ConnectionDiagnostics): void;
}
export interface RoomConnection {
  refresh(): Promise<boolean>;
  reconnect(): void;
  preview(preview: ItemPreview | null): void;
  close(): void;
}
export type RealtimeFactory = (options: RealtimeOptions) => RoomConnection;

export const connectRoom: RealtimeFactory = (options) => {
  let socket: WebSocket | null = null;
  let cursor = 0;
  let attempt = 0;
  let backoff = 0;
  let lastConfirmedSyncAt: string | null = null;
  let failureStartedAt: number | null = null;
  let generation = 0;
  let disposed = false;
  let revoked = false;
  let synced = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let watchdog: ReturnType<typeof setTimeout> | undefined;
  let previewTimer: ReturnType<typeof setTimeout> | undefined;
  let fetchController: AbortController | null = null;
  let lastPreview: ItemPreview | null = null;
  let previewAt = 0;
  const pending = new Set<(ok: boolean) => void>();
  const finish = (ok: boolean) => { for (const resolve of pending) resolve(ok); pending.clear(); };
  const diagnose = () => options.onDiagnostics?.({ attempt, lastConfirmedSyncAt, failureStartedAt });

  function offline() {
    failureStartedAt ??= Date.now(); diagnose();
    synced = false; options.onPreview(null); options.onPresence(0); finish(false);
    options.onState("disconnected", "Связь потеряна · восстанавливаем соединение");
  }
  function removeSocket() {
    clearTimeout(watchdog);
    if (socket) {
      socket.onclose = null; socket.onmessage = null; socket.onopen = null; socket.onerror = null;
      socket.close(); socket = null;
    }
  }
  function deny() {
    revoked = true; generation++; fetchController?.abort(); clearTimeout(timer); removeSocket();
    synced = false; finish(false); options.onPreview(null); options.onPresence(0);
    attempt = 0; lastConfirmedSyncAt = null; failureStartedAt = null; diagnose();
    options.onState("revoked", "Доступ к комнате отозван");
  }
  function retry() {
    removeSocket();
    if (disposed || revoked) return;
    offline();
    clearTimeout(timer);
    const delay = Math.min(250 * 2 ** backoff, 3000);
    backoff = Math.min(backoff + 1, 4);
    timer = setTimeout(() => void open(), delay);
  }
  function armWatchdog(delay = 12000) {
    clearTimeout(watchdog);
    watchdog = setTimeout(retry, delay);
  }
  async function open() {
    if (disposed || revoked) return;
    attempt++; failureStartedAt ??= Date.now(); diagnose();
    const current = ++generation;
    fetchController?.abort();
    fetchController = new AbortController();
    const timeout = setTimeout(() => fetchController?.abort(), 4000);
    options.onState("connecting");
    try {
      const response = await fetch(`/api/v1/rooms/${options.roomId}/realtime/ticket`, {
        method: "POST", credentials: "same-origin", signal: fetchController.signal,
        headers: options.accessToken ? { Authorization: `Bearer ${options.accessToken}` } : {},
      });
      if (disposed || current !== generation) return;
      if (response.status === 401 || response.status === 403) { deny(); return; }
      if (!response.ok) throw new Error("ticket unavailable");
      const body = await response.json() as { ticket: string };
      if (disposed || current !== generation) return;
      const url = new URL(`/api/v1/rooms/${options.roomId}/realtime/ws`, window.location.href);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(url.href); socket = ws;
      armWatchdog(5000);
      ws.onopen = () => ws.send(JSON.stringify({ type: "subscribe", ticket: body.ticket, cursor }));
      ws.onmessage = (event) => {
        if (disposed || current !== generation) return;
        try {
          const message = JSON.parse(String(event.data));
          if (message.type === "sync") {
            const snapshot = message.snapshot as SceneProjection;
            if (snapshot.room_id !== options.roomId || !Number.isSafeInteger(snapshot.event_cursor)
                || !Array.isArray(snapshot.items) || !Array.isArray(message.events)) throw new Error("invalid sync");
            // One authoritative snapshot replaces the entire visible projection.
            cursor = snapshot.event_cursor; synced = true; backoff = 0; attempt = 0;
            lastConfirmedSyncAt = new Date().toISOString(); failureStartedAt = null; diagnose();
            options.onPreview(null); options.onSnapshot(snapshot); options.onState("connected"); finish(true);
          } else if (message.type === "preview" && synced) {
            clearTimeout(previewTimer);
            options.onPreview(message.clear ? null : { id: message.item_id, x: message.x, y: message.y });
            previewTimer = setTimeout(() => options.onPreview(null), 2000);
          } else if (message.type === "heartbeat") {
            options.onPresence(message.presence_count ?? 0);
          }
          armWatchdog();
        } catch { retry(); }
      };
      ws.onclose = (event) => { if (event.code === 4403) deny(); else retry(); };
      ws.onerror = retry;
    } catch {
      if (!disposed && current === generation) retry();
    } finally { clearTimeout(timeout); }
  }

  function reconnect() {
    if (disposed || revoked) return;
    generation++; clearTimeout(timer); fetchController?.abort(); removeSocket();
    offline(); void open();
  }
  const browserOffline = () => { generation++; fetchController?.abort(); retry(); };
  window.addEventListener("offline", browserOffline);
  window.addEventListener("online", reconnect);
  void open();
  return {
    refresh: () => {
      if (disposed || revoked) return Promise.resolve(false);
      return new Promise<boolean>((resolve) => {
        const timeout = setTimeout(() => { pending.delete(done); resolve(false); }, 6000);
        const done = (ok: boolean) => { clearTimeout(timeout); resolve(ok); };
        pending.add(done);
        if (socket?.readyState === 1 && synced) socket.send(JSON.stringify({ type: "resync" }));
        else { pending.delete(done); reconnect(); pending.add(done); }
      });
    },
    reconnect,
    preview: (preview) => {
      if (!synced || socket?.readyState !== 1) return;
      if (preview && performance.now() - previewAt < 80) return;
      const value = preview ?? lastPreview;
      if (value) socket.send(JSON.stringify({ type: "preview", item_id: value.id, x: value.x, y: value.y, clear: !preview }));
      lastPreview = preview; previewAt = performance.now();
    },
    close: () => {
      disposed = true; generation++; fetchController?.abort();
      clearTimeout(timer); clearTimeout(previewTimer); removeSocket(); finish(false);
      window.removeEventListener("offline", browserOffline); window.removeEventListener("online", reconnect);
    },
  };
};
