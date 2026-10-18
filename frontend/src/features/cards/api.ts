import type { Card, CardPage, Package } from "./types";

async function request(url: string, token?: string): Promise<Response> {
  const response = await fetch(url, { credentials: "same-origin", headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) {
    let text = "Карточки временно недоступны. Введённые данные сохранены в форме.";
    try { text = (await response.json() as { detail?: { message?: string } }).detail?.message ?? text; }
    catch { /* Non-JSON gateway error. */ }
    throw new Error(text);
  }
  return response;
}
export const cardApi = {
  async list(room: string, search: string, offset: number, token?: string): Promise<CardPage> {
    return (await request(`/api/v1/rooms/${room}/cards?${new URLSearchParams({ search, offset: String(offset), limit: "20" })}`, token)).json();
  },
  async get(room: string, id: string, token?: string): Promise<Card> {
    return (await request(`/api/v1/rooms/${room}/cards/${id}`, token)).json();
  },
  async schema(system: string): Promise<Package> { return (await request(`/api/v1/system-packages/${system}/1`)).json(); },
  async export(room: string, id: string, format: "json" | "html", token?: string): Promise<void> {
    const response = await request(`/api/v1/rooms/${room}/cards/${id}/export?format=${format}`, token);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a"); link.href = url; link.download = `card-${id}.${format}`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
