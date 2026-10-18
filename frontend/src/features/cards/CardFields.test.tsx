import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ImportPanel } from "../card-import/ImportPanel";
import { CardEditor } from "./CardEditor";
import { CardsPanel } from "./CardsPanel";
import { blankCard, editable, type Card } from "./types";

function sampleCard(): Card {
  return { ...blankCard(), id: "card", name: "Проверка полей", version: 1,
    campaign_id: "campaign", room_id: "room", created_at: "", updated_at: "",
    can_edit_structure: false, can_edit_current: true, can_export: false,
    notes: "Сохранить исходные заметки", external_key: "stable-card",
    fields: [{ key: "trait", label: "Особенность", value: "Исходная", value_type: "text", visibility: "everyone", order: 2 }],
    resources: [{ key: "hp", label: "HP", current: 7, max: 10, color: null, visibility: "everyone" }],
    skills: [
      { key: "dex_save", name: "Ловкость", bonus: 6, proficient: true, description: "Спасброски", visibility: "everyone" },
      { key: "quiet", name: "Тишина", bonus: null, proficient: false, description: null, visibility: "everyone" },
    ],
    inventory: [
      { id: "item", name: "Кинжал", quantity: 2, description: "Атака +6 · Урон 1к4+4", icon: "🗡", visibility: "everyone" },
      { id: "literal", name: "Знак", quantity: null, description: null, icon: '<img src="https://invalid.example/icon">', visibility: "everyone" },
    ],
    abilities: [
      { id: "ability", schema_version: 1, name: "Кувырок", description: "Защита от атаки", action_type: "Реакция",
        uses: { key: "uses_0", label: "За игру", current: 2, max: 3, color: "#aabbcc", visibility: "everyone" },
        geometry: { shape: "cone", origin: "point", length: 9, angle: 60, units: "м" }, automation: null, visibility: "everyone" },
      { id: "empty", schema_version: 1, name: "Наблюдение", description: "", action_type: null, uses: null,
        geometry: null, automation: null, visibility: "everyone" },
    ],
  };
}

const props = () => ({ roomId: "room", canManage: false, disabled: false, version: 1,
  execute: vi.fn().mockResolvedValue(true), players: [], onLoadPlayers: vi.fn(), hasScene: true });
function serve(card: Card) {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ cards: [card], has_more: false }) });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it("shows projected metadata and zero uses as inert text without granting structural controls", async () => {
  const card = sampleCard(); card.abilities[0].uses!.current = 0;
  const fetch = serve(card), options = props();
  const view = render(<CardsPanel {...options} />);
  fireEvent.click(await screen.findByRole("button", { name: /Проверка полей/ }));
  const detail = within(screen.getByRole("article", { name: "Карточка Проверка полей" }));
  expect(detail.getByText("Владение")).toBeVisible();
  expect(detail.getByText("Спасброски")).toBeVisible();
  expect(detail.getByText("🗡")).toBeVisible();
  expect(detail.getByText("Атака +6 · Урон 1к4+4")).toBeVisible();
  expect(detail.getByText('<img src="https://invalid.example/icon">')).toBeVisible();
  expect(view.container.querySelector("img, script")).toBeNull();
  fireEvent.click(detail.getByText("Кувырок", { selector: "summary" }));
  expect(detail.getByText("Реакция")).toBeVisible();
  expect(detail.getByText("За игру: 0 / 3")).toBeVisible();
  expect(detail.getAllByText("Владение")).toHaveLength(1);
  expect(detail.queryByRole("button", { name: "Редактировать карточку" })).not.toBeInTheDocument();
  expect(detail.queryByLabelText(/Владение навыком|Использования способности/)).not.toBeInTheDocument();
  expect(options.execute).not.toHaveBeenCalled();
  fireEvent.change(detail.getByLabelText("Текущее: HP"), { target: { value: "0" } });
  fireEvent.click(detail.getByRole("button", { name: "Сохранить HP" }));
  await waitFor(() => expect(options.execute).toHaveBeenCalledExactlyOnceWith("card.resource", { card_id: "card", resource_key: "hp", current: 0 }));
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("saves rich GM edits through card.update with zero current and an optional maximum without losing sibling data", async () => {
  const card = sampleCard(); card.can_edit_structure = true;
  serve(card); const options = { ...props(), canManage: true };
  render(<CardsPanel {...options} />);
  fireEvent.click(await screen.findByRole("button", { name: /Проверка полей/ }));
  fireEvent.click(screen.getByRole("button", { name: "Редактировать карточку" }));
  fireEvent.click(screen.getByRole("button", { name: "Навыки, инвентарь и способности" }));
  fireEvent.click(screen.getByLabelText("Владение навыком 1"));
  fireEvent.change(screen.getByLabelText("Описание навыка 1"), { target: { value: "Проверенное описание навыка" } });
  fireEvent.change(screen.getByLabelText("Описание предмета 1"), { target: { value: "Проверенное описание вещи" } });
  fireEvent.change(screen.getByLabelText("Иконка предмета 1"), { target: { value: "🛡" } });
  fireEvent.change(screen.getByLabelText("Тип действия способности 1"), { target: { value: "Бонусное действие" } });
  fireEvent.change(screen.getByLabelText("Название использований способности 1"), { target: { value: "За отдых" } });
  fireEvent.change(screen.getByLabelText("Текущее использований способности 1"), { target: { value: "0" } });
  fireEvent.change(screen.getByLabelText("Максимум использований способности 1"), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("Название карточки"), { target: { value: "Проверенный страж" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить карточку" }));
  const expected = editable(card);
  expected.name = "Проверенный страж";
  expected.skills[0] = { ...expected.skills[0], proficient: false, description: "Проверенное описание навыка" };
  expected.inventory[0] = { ...expected.inventory[0], icon: "🛡", description: "Проверенное описание вещи" };
  expected.abilities[0] = { ...expected.abilities[0], action_type: "Бонусное действие",
    uses: { ...expected.abilities[0].uses!, label: "За отдых", current: 0, max: null } };
  await waitFor(() => expect(options.execute).toHaveBeenCalledExactlyOnceWith(
    "card.update", { card_id: card.id, card: expected }, expect.any(Function),
  ));
});

it("adds or removes optional uses and clears optional metadata in draft review while respecting disabled editing", async () => {
  const card = sampleCard();
  const job = { id: "job", status: "draft", version: 1, card_ids: [], expires_at: "2030-01-01T00:00:00Z",
    draftset: { schema_version: 1, diagnostics: [], drafts: [{ external_key: "stable-card", card: editable(card),
      count: 1, included: true, create_token: false, source: {} }] } };
  const updates: typeof job.draftset[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      const draftset = { ...job.draftset, drafts: JSON.parse(init.body as string).drafts };
      updates.push(draftset);
      return new Response(JSON.stringify({ ...job, version: 2, draftset }));
    }
    return new Response(JSON.stringify(url.endsWith("/imports") ? [job] : job));
  }));
  const options = { roomId: "room", canManage: true, disabled: false, hasScene: true,
    execute: vi.fn().mockResolvedValue(true), players: [], onLoadPlayers: vi.fn() };
  const view = render(<ImportPanel {...options} />);
  fireEvent.click(await screen.findByRole("button", { name: /Продолжить импорт/ }));
  fireEvent.click(screen.getByRole("button", { name: "Редактировать: Проверка полей" }));
  fireEvent.click(screen.getByRole("button", { name: "Навыки, инвентарь и способности" }));
  expect(screen.queryByLabelText("Текущее использований способности 2")).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Отслеживать использования способности 1"));
  expect(screen.queryByLabelText("Текущее использований способности 1")).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Отслеживать использования способности 2"));
  expect(screen.getByLabelText("Текущее использований способности 2")).toHaveValue(0);
  expect(screen.getByLabelText("Максимум использований способности 2")).toHaveValue(null);
  fireEvent.change(screen.getByLabelText("Название использований способности 2"), { target: { value: "За отдых" } });
  fireEvent.change(screen.getByLabelText("Максимум использований способности 2"), { target: { value: "4" } });
  for (const label of ["Описание навыка 1", "Описание предмета 1", "Иконка предмета 1", "Тип действия способности 1"]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value: "" } });
  }
  fireEvent.click(screen.getByLabelText("Владение навыком 1"));
  view.rerender(<ImportPanel {...options} disabled />);
  for (const label of ["Владение навыком 1", "Описание навыка 1", "Описание предмета 1", "Иконка предмета 1",
    "Тип действия способности 1", "Отслеживать использования способности 2", "Название использований способности 2",
    "Текущее использований способности 2", "Максимум использований способности 2"]) {
    expect(screen.getByLabelText(label)).toBeDisabled();
  }
  expect(screen.getByRole("button", { name: "Сохранить карточку" })).toBeDisabled();
  expect(updates).toHaveLength(0);
  view.rerender(<ImportPanel {...options} />);
  fireEvent.click(screen.getByRole("button", { name: "Сохранить карточку" }));
  fireEvent.click(screen.getByRole("button", { name: "Сохранить черновики" }));
  await waitFor(() => expect(updates).toHaveLength(1));
  const expected = editable(card);
  expected.skills[0] = { ...expected.skills[0], proficient: false, description: null };
  expected.inventory[0] = { ...expected.inventory[0], description: null, icon: null };
  expected.abilities[0] = { ...expected.abilities[0], action_type: null, uses: null };
  expected.abilities[1].uses = { key: expect.stringMatching(/^[a-z][a-z0-9_]{0,63}$/), label: "За отдых",
    current: 0, max: 4, color: null, visibility: "everyone" };
  expect(updates[0].drafts[0].card).toEqual(expected);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Черновик v2"));
  fireEvent.click(screen.getByRole("button", { name: "Подтвердить импорт (1)" }));
  await waitFor(() => expect(options.execute).toHaveBeenCalledExactlyOnceWith(
    "import.confirm", { job_id: "job", expected_job_version: 2 }, expect.any(Function),
  ));
});


it("reveals the hidden section and collapsed entry when native validation finds an invalid nested field", async () => {
  const card = editable(sampleCard()); card.name = "Проверка"; card.abilities[0].uses!.label = "";
  render(<CardEditor initial={card} disabled={false} players={[]} onLoadPlayers={vi.fn()} onSave={vi.fn()} onCancel={vi.fn()} />);
  const input = screen.getByLabelText("Название использований способности 1");
  const entry = input.closest("details")!;
  const section = entry.closest<HTMLElement>("[data-editor-section]")!;
  expect(entry.open).toBe(false); expect(section.hidden).toBe(true);
  fireEvent.invalid(input);
  await waitFor(() => { expect(entry.open).toBe(true); expect(section.hidden).toBe(false); });
  expect(input).toBeVisible();
});
