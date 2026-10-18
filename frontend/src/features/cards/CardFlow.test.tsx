import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SceneExperience } from "../scene/SceneExperience";
import type { SceneApi } from "../scene/types";
import { testTransport } from "../realtime/testTransport";

afterEach(() => vi.unstubAllGlobals());

it("creates a mob with a named custom field and blood resource through the shared command callback", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ cards: [], has_more: false }) }));
  const api = { projection: vi.fn().mockResolvedValue({ room_id: "r", actor_session_id: "gm", aggregate_version: 2,
    event_cursor: 2, can_manage: true, scenes: [], scene: null, items: [] }),
    command: vi.fn().mockResolvedValue({ status: "accepted" }) } as unknown as SceneApi;
  render(<SceneExperience room={{ id: "r", campaign_id: "c", name: "Стол", is_locked: false, pin_enabled: false,
    created_at: "", can_manage: true }} accessToken="credential" api={api} realtimeFactory={testTransport(api)} />);
  fireEvent.click(await screen.findByRole("button", { name: "Карточки" }));
  fireEvent.click(screen.getByRole("button", { name: "Новая карточка" }));
  fireEvent.change(screen.getByLabelText("Название карточки"), { target: { value: "Страж" } });
  fireEvent.change(screen.getByLabelText("Вид карточки"), { target: { value: "mob" } });
  fireEvent.click(screen.getByRole("button", { name: "Поля 0" }));
  fireEvent.click(screen.getByRole("button", { name: "Добавить поле" }));
  fireEvent.change(screen.getByLabelText("Название поля 1"), { target: { value: "Клан" } });
  fireEvent.change(screen.getByLabelText("Значение поля 1"), { target: { value: "Север" } });
  fireEvent.click(screen.getByRole("button", { name: "Ресурсы 0" }));
  fireEvent.click(screen.getByRole("button", { name: "Добавить ресурс" }));
  fireEvent.change(screen.getByLabelText("Название ресурса 1"), { target: { value: "Очки крови" } });
  fireEvent.change(screen.getByLabelText("Текущее ресурса 1"), { target: { value: "5" } });
  fireEvent.change(screen.getByLabelText("Максимум ресурса 1"), { target: { value: "8" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить карточку" }));
  await waitFor(() => expect(api.command).toHaveBeenCalledWith(expect.objectContaining({
    expected_aggregate_version: 2, type: "card.create", payload: { card: expect.objectContaining({
      name: "Страж", kind: "mob", fields: [expect.objectContaining({ label: "Клан", value: "Север" })],
      resources: [expect.objectContaining({ label: "Очки крови", current: 5, max: 8 })],
    }) },
  }), "credential"));
});
