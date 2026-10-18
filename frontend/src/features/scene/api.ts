import type { SceneApi } from "./types";

async function request<T>(url: string, accessToken?: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { ...init, credentials: "same-origin", headers: {
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}), ...init.headers,
  } });
  if (!response.ok) {
    let message = "Сервер временно недоступен. Подтверждённое состояние сохранено.";
    try {
      const error = await response.json() as { detail?: { message?: string } };
      message = error.detail?.message ?? message;
    } catch { /* A gateway body is not an application error. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const sceneApi: SceneApi = {
  projection: (roomId, accessToken) => request(`/api/v1/rooms/${roomId}/scene`, accessToken),
  command: (command, accessToken) => request(`/api/v1/rooms/${command.room_id}/scene/commands`, accessToken,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(command) }),
  prepareUpload: (roomId, file, accessToken) => request(`/api/v1/rooms/${roomId}/assets/prepare`, accessToken,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      name: file.name.slice(0, 160), byte_size: file.size, content_type: file.type, kind: "map",
    }) }),
  upload: (asset, file, accessToken) => request(asset.upload_url, accessToken,
    { method: "PUT", headers: { "Content-Type": file.type }, body: file }),
  download: (roomId, assetId, accessToken) => request(`/api/v1/rooms/${roomId}/assets/${assetId}/download`, accessToken),
};
