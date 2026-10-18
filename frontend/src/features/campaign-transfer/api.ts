export interface TransferJob {
  id: string; kind: "import" | "export"; phase: string; progress: number;
  cancel_requested: boolean; result_campaign_id: string | null; error_code: string | null;
  expires_at: string; archive_available: boolean;
}
export class TransferError extends Error { constructor(message: string, readonly code: string) { super(message); } }
const base = "/api/v1/campaign-transfers";
async function request(path: string, token: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(base + path, { ...init, credentials: "same-origin",
    headers: { ...init.headers, Authorization: `Bearer ${token}` } });
  if (!response.ok) {
    let detail: { message?: string; code?: string } = {};
    try { detail = (await response.json()).detail ?? {}; } catch { /* Fixed gateway fallback. */ }
    throw new TransferError(detail.message ?? "Связь прервана. Проверьте статус перед повтором.", detail.code ?? "unavailable");
  }
  return response;
}
export const transferApi = {
  async export(id: string, campaign: string, history: boolean, snapshot: boolean, token: string): Promise<TransferJob> {
    return (await request(`/${id}/export`, token, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ campaign_id: campaign, include_history: history, include_snapshot: snapshot }) })).json();
  },
  async import(id: string, file: File, token: string, signal?: AbortSignal): Promise<TransferJob> {
    if (!file.name.toLowerCase().endsWith(".zip") || !file.size || file.size > 268435456)
      throw new TransferError("Выберите ZIP кампании до 256 МБ", "archive_limit");
    return (await request(`/${id}/import`, token, { method: "PUT", headers: { "Content-Type": "application/zip" }, body: file, signal })).json();
  },
  async get(id: string, token: string): Promise<TransferJob> { return (await request(`/${id}`, token)).json(); },
  async cancel(id: string, token: string): Promise<TransferJob> { return (await request(`/${id}`, token, { method: "DELETE" })).json(); },
  async download(id: string, token: string): Promise<void> {
    const blob = await (await request(`/${id}/archive`, token)).blob();
    const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = "campaign-v1.zip"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
export type TransferApi = typeof transferApi;
