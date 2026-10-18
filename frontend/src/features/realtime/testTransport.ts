import type { SceneApi } from "../scene/types";
import type { RealtimeFactory } from "./transport";

// Explicit component-test seam; production always uses the WebSocket transport.
export function testTransport(api: SceneApi): RealtimeFactory {
  return (options) => {
    let active = true;
    const refresh = async () => {
      try {
        const snapshot = await api.projection(options.roomId, options.accessToken);
        if (!active) return false;
        options.onSnapshot(snapshot); options.onState("connected"); return true;
      } catch (reason) {
        if (active) options.onState("disconnected", reason instanceof Error ? reason.message : "Нет связи");
        return false;
      }
    };
    void refresh();
    return { refresh, reconnect: () => { void refresh(); }, preview: () => {}, close: () => { active = false; } };
  };
}
