import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CardsPanel } from "./CardsPanel";
import { blankCard } from "./types";

afterEach(() => vi.unstubAllGlobals());

it("defaults new NPCs privately and retains a deliberate visibility choice", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ cards: [], has_more: false }) }));
  const execute = vi.fn().mockResolvedValue(true);
  render(<CardsPanel roomId="room" canManage disabled={false} version={1} execute={execute} players={[]} onLoadPlayers={vi.fn()} hasScene />);
  fireEvent.click(screen.getByRole("button", { name: "Новая карточка" }));
  fireEvent.change(screen.getByLabelText("Вид карточки"), { target: { value: "npc" } });
  expect(screen.getByLabelText("Видимость карточки")).toHaveValue("gm_only");
  fireEvent.change(screen.getByLabelText("Видимость карточки"), { target: { value: "everyone" } });
  fireEvent.change(screen.getByLabelText("Вид карточки"), { target: { value: "mob" } });
  expect(screen.getByLabelText("Видимость карточки")).toHaveValue("everyone");
  fireEvent.change(screen.getByLabelText("Название карточки"), { target: { value: "Страж" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить карточку" }));
  await waitFor(() => expect(execute).toHaveBeenCalledWith("card.create", { card: expect.objectContaining({ kind: "mob", visibility: "everyone" }) }, expect.any(Function)));
});

it("deletes cards through the command callback and labels existing representations", async () => {
  const card = { ...blankCard(), id: "a", name: "Страж", version: 1, can_edit_structure: true,
    can_edit_current: true, can_export: true, campaign_id: "c", room_id: "r", created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ cards: [card], has_more: false }) }));
  const execute = vi.fn().mockResolvedValue(true);
  render(<CardsPanel roomId="room" canManage disabled={false} version={1} execute={execute} players={[]} onLoadPlayers={vi.fn()} hasScene />);
  fireEvent.click(await screen.findByRole("button", { name: /Страж/ }));
  fireEvent.click(screen.getByText("Ещё", { selector: "summary" }));
  expect(screen.getByText(/Представление существующего персонажа/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Удалить карточку в корзину" }));
  expect(execute).toHaveBeenCalledWith("card.delete", { card_id: "a" }, expect.any(Function));
});
