import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { blankCard } from "../cards/types";
import { ImportPanel } from "./ImportPanel";
import { importApi } from "./api";

afterEach(() => vi.unstubAllGlobals());

it("pastes literal UTF-8 text, reviews source fragments and count2, edits, saves and confirms", async () => {
  const text = "PRIVATE_UNASSIGNED\nschema_version: 1\nКарточка: guard\nНазвание: Страж\nКоличество: 2\n  PRIVATE_ASSOCIATED  ";
  const job = { id: "paste-job", status: "draft", version: 1, expires_at: "2026-12-01T00:00:00Z", card_ids: [],
    draftset: { schema_version: 1, diagnostics: [{ severity: "warning", code: "unknown_field", message: "Неизвестное поле сохранено", entity: "guard", section: "Раздел", row: 5, field: "Знамя" }],
      fragments: [{ external_key: null, text: "PRIVATE_UNASSIGNED\n", section: "Раздел", row: 1, field: "текст" },
        { external_key: "guard", text: "  PRIVATE_ASSOCIATED  ", section: "Раздел", row: 6, field: "текст" }],
      drafts: [{ external_key: "guard", card: { ...blankCard(), name: "Страж" }, count: 2, included: true, create_token: false,
        source: { name: { section: "Раздел", row: 4, field: "Название" } } }] } };
  const requests: { url: string; init?: RequestInit }[] = [];
  let current = job;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    requests.push({ url, init });
    if (init?.method === "PATCH") current = { ...current, version: 2,
      draftset: { ...current.draftset, drafts: JSON.parse(init.body as string).drafts } };
    return new Response(JSON.stringify(url.endsWith("/imports") ? [] : current), { status: 200 });
  }));
  const execute = vi.fn(async (_type, _payload, acknowledge) => {
    current = { ...current, status: "confirmed", draftset: { ...current.draftset, fragments: [] } };
    acknowledge(); return true;
  });
  render(<ImportPanel roomId="room" accessToken="fixture-token" canManage disabled={false} hasScene execute={execute} players={[]} onLoadPlayers={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Вставить текст" }));
  const textarea = screen.getByLabelText("Текст карточек");
  fireEvent.change(textarea, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Разобрать текст" }));
  await screen.findByText("Страж", { selector: "h3" });
  expect(execute).not.toHaveBeenCalled();
  expect(screen.getByText("PRIVATE_UNASSIGNED", { exact: false, selector: "pre" })).toBeInTheDocument();
  expect(screen.getByText("PRIVATE_ASSOCIATED", { exact: false, selector: "pre" }).textContent).toBe("  PRIVATE_ASSOCIATED  ");
  expect(screen.getByText(/guard · Раздел · строка 5 · Знамя/)).toBeInTheDocument();
  const post = requests.find((r) => r.init?.method === "POST")!;
  expect(post.url).toBe("/api/v1/rooms/room/imports?format=txt");
  expect((post.init?.headers as Record<string, string>).Authorization).toBe("Bearer fixture-token");
  const decoded = await new Promise<string>((resolve) => { const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string); reader.readAsText(post.init!.body as Blob); });
  expect(decoded).toBe(text);
  fireEvent.click(screen.getByRole("button", { name: "Редактировать: Страж" }));
  expect(screen.getByText("PRIVATE_ASSOCIATED", { exact: false, selector: "pre" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Название карточки"), { target: { value: "Проверенный страж" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить карточку" }));
  fireEvent.click(screen.getByRole("button", { name: "Подтвердить импорт (2)" }));
  await waitFor(() => expect(execute).toHaveBeenCalledWith("import.confirm", { job_id: "paste-job", expected_job_version: 2 }, expect.any(Function)));
  const update = JSON.parse(requests.find((r) => r.init?.method === "PATCH")!.init!.body as string);
  expect(update.drafts[0].card.name).toBe("Проверенный страж");
  expect(update.drafts[0].count).toBe(2);
  expect(update.fragments).toBeUndefined();
  expect(textarea).toHaveValue("");
});

it("keeps malformed pasted text and diagnostics, validates empty input before sending", async () => {
  const post = vi.fn();
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") { post(); return new Response(JSON.stringify({ detail: { code: "parse_error", message: "Проверьте документ",
      diagnostics: [{ severity: "error", code: "schema_version", message: "Нужна разметка", entity: null, section: "Раздел", row: 1, field: "файл" }] } }), { status: 422 }); }
    return new Response("[]", { status: 200 });
  }));
  render(<ImportPanel roomId="room" canManage disabled={false} hasScene execute={vi.fn()} players={[]} onLoadPlayers={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Вставить текст" }));
  fireEvent.click(screen.getByRole("button", { name: "Разобрать текст" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Вставьте текст");
  expect(post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Текст карточек"), { target: { value: "Неразмеченная история" } });
  fireEvent.click(screen.getByRole("button", { name: "Разобрать текст" }));
  expect(await screen.findByText(/Нужна разметка/)).toBeInTheDocument();
  expect(screen.getByLabelText("Текст карточек")).toHaveValue("Неразмеченная история");
  expect(screen.getByRole("textbox", { name: "Текст карточек" })).toHaveValue("Неразмеченная история");
  expect(screen.queryByRole("button", { name: /Подтвердить импорт/ })).not.toBeInTheDocument();
});

it("enforces UTF-8 byte limit before request and keeps existing file upload", async () => {
  const fetch = vi.fn(async (_url: string, _init?: RequestInit) => new Response("{}", { status: 201 })); vi.stubGlobal("fetch", fetch);
  await expect(importApi.paste("room", "я".repeat(2621441))).rejects.toMatchObject({ code: "file_size" });
  expect(fetch).not.toHaveBeenCalled();
  await importApi.upload("room", new File(["schema_version: 1"], "cards.txt"));
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe("/api/v1/rooms/room/imports?format=txt");
});

it("does not show import or fetch creator data to guests", () => {
  const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  render(<ImportPanel roomId="room" canManage={false} disabled={false} hasScene execute={vi.fn()} players={[]} onLoadPlayers={() => {}} />);
  expect(screen.queryByLabelText("Текст карточек")).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it("reviews, edits, excludes, counts and confirms only after saving the draft", async () => {
  const job = { id: "job-1", status: "draft", version: 1, expires_at: "2026-12-01T00:00:00Z", card_ids: [],
    draftset: { schema_version: 1, diagnostics: [], drafts: ["guard", "torch"].map((external_key) => ({ external_key,
      card: { ...blankCard(), name: external_key }, count: 1, included: true, create_token: false, source: {} })) } };
  const requests: { url: string; method: string; body?: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    requests.push({ url, method: init?.method ?? "GET", body: init?.body as string });
    const result = init?.method === "PATCH" ? { ...job, version: 2, draftset: { ...job.draftset,
      drafts: JSON.parse(init.body as string).drafts } } : url.endsWith("/imports") ? [job] : job;
    return new Response(JSON.stringify(result), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  const execute = vi.fn(async () => true);
  render(<ImportPanel roomId="room" canManage disabled={false} hasScene execute={execute} players={[]} onLoadPlayers={() => {}} />);
  fireEvent.click(await screen.findByRole("button", { name: /Продолжить импорт/ }));
  fireEvent.change(screen.getByLabelText("Экземпляров: guard"), { target: { value: "3" } });
  fireEvent.click(screen.getByLabelText("Включить: torch"));
  fireEvent.click(screen.getByLabelText("Токен для: guard"));
  fireEvent.click(screen.getByRole("button", { name: "Редактировать: guard" }));
  fireEvent.change(screen.getByLabelText("Название карточки"), { target: { value: "Проверенный страж" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить карточку" }));
  fireEvent.click(screen.getByRole("button", { name: "Подтвердить импорт (3)" }));
  await waitFor(() => expect(execute).toHaveBeenCalledWith("import.confirm", { job_id: "job-1", expected_job_version: 2 }, expect.any(Function)));
  const update = JSON.parse(requests.find((r) => r.method === "PATCH")!.body!);
  expect(update.drafts[0].card.name).toBe("Проверенный страж");
  expect(update.drafts[1].included).toBe(false);
});
