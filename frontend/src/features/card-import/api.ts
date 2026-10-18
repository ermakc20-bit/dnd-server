import type { CardData } from "../cards/types";

export interface Source { section: string; row: number; field: string }
export interface SourceFragment extends Source { external_key: string | null; text: string }
export interface Diagnostic extends Source { severity: "error" | "warning" | "info"; code: string; message: string; entity: string | null }
export interface Draft { external_key: string; card: CardData; count: number; included: boolean;
  create_token: boolean; source: Record<string, Source> }
export interface ImportJob { id: string; status: "draft" | "confirmed" | "cancelled" | "expired";
  version: number; expires_at: string; card_ids: string[];
  draftset: { schema_version: 1; drafts: Draft[]; diagnostics: Diagnostic[]; fragments?: SourceFragment[] } }
export class ImportError extends Error {
  constructor(message: string, readonly code: string, readonly diagnostics: Diagnostic[] = []) { super(message); }
}
async function request(url: string, token?: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(url, { ...init, credentials: "same-origin",
    headers: { ...init.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
  if (!response.ok) {
    let detail: { message?: string; code?: string; diagnostics?: Diagnostic[] } = {};
    try { detail = (await response.json()).detail ?? {}; } catch { /* Fixed fallback for gateways. */ }
    throw new ImportError(detail.message ?? "Импорт временно недоступен. Исходник и правки сохранены в форме.", detail.code ?? "unavailable", detail.diagnostics);
  }
  return response;
}
const base = (room: string) => `/api/v1/rooms/${room}/imports`;
export const importApi = {
  async list(room: string, token?: string): Promise<ImportJob[]> { return (await request(base(room), token)).json(); },
  async get(room: string, id: string, token?: string): Promise<ImportJob> { return (await request(`${base(room)}/${id}`, token)).json(); },
  async paste(room: string, text: string, token?: string, mode?: string): Promise<ImportJob> {
    if (!text.trim()) throw new ImportError("Вставьте текст карточек", "empty_text");
    const file = new File([text], "pasted.txt", { type: "text/plain;charset=utf-8" });
    if (file.size > 5242880) throw new ImportError("Текст превышает 5 МБ в UTF-8", "file_size");
    return importApi.upload(room, file, token, mode);
  },
  async upload(room: string, file: File, token?: string, mode?: string): Promise<ImportJob> {
    const format = file.name.split(".").at(-1)?.toLowerCase() === "htm" ? "html" : file.name.split(".").at(-1)?.toLowerCase();
    if (!format || !["json", "xlsx", "docx", "txt", "pdf", "html"].includes(format) || file.size > 5242880 || !file.size)
      throw new ImportError("Выберите JSON, XLSX, DOCX, TXT, PDF или HTML до 5 МБ", "format");
    return (await request(`${base(room)}?${new URLSearchParams({ format, ...(mode ? { mode } : {}) })}`, token,
      { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file })).json();
  },
  async save(room: string, job: ImportJob, token?: string): Promise<ImportJob> {
    return (await request(`${base(room)}/${job.id}`, token, { method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: job.version, drafts: job.draftset.drafts }) })).json();
  },
  async cancel(room: string, job: ImportJob, token?: string): Promise<ImportJob> {
    return (await request(`${base(room)}/${job.id}?expected_version=${job.version}`, token, { method: "DELETE" })).json();
  },
  async template(room: string, format: string, token?: string): Promise<void> {
    const response = await request(`${base(room)}/templates/${format}`, token);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a"); link.href = url; link.download = `cards-v1.${format}`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
