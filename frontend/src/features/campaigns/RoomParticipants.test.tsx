import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { RoomAdmin } from "./CampaignExperience";
import { CampaignApiError, type CampaignApi } from "./api";
const room = { id: "r", campaign_id: "c", name: "Стол", is_locked: false,
  pin_enabled: false, created_at: "", can_manage: true };
const summary = { id: "p", display_name: "Игрок", role: "player", connection_status: "connected",
  assigned_tokens: [{ id: "t", name: "Воин", scene_id: "s", scene_name: "Карта" }] };
const event = { id: 9, participant_id: "p", display_name: "Игрок", type: "connection.closed",
  occurred_at: "2026-10-15T12:00:00Z", reason: "socket_closed_actor_connected" };

it("keeps the newest participant read when an older same-room response arrives later", async () => {
  let oldResolve!: (value: unknown) => void;
  const status = vi.fn().mockImplementationOnce(() => new Promise(resolve => { oldResolve = resolve; }))
    .mockResolvedValueOnce([{ ...summary, display_name: "Новый статус", connection_status: "disconnected" }]);
  const api = { listParticipantStatus: status } as unknown as CampaignApi;
  render(<RoomAdmin room={room} accessToken="identity" api={api} onRoom={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Показать участников" }));
  fireEvent.click(screen.getByRole("button", { name: "Показать участников" }));
  await screen.findByText(/Новый статус · игрок/);
  await act(async () => oldResolve([summary]));
  expect(screen.getByText(/Новый статус · игрок/)).toBeInTheDocument();
  expect(screen.queryByText(/Игрок · игрок/)).not.toBeInTheDocument();
});

it("shows actor status and active assignments plus a bounded security journal page and truthful source errors", async () => {
  const status = vi.fn().mockResolvedValue([summary]);
  const journal = vi.fn().mockResolvedValueOnce({ events: [event], next_before_id: 9 })
    .mockRejectedValueOnce(new Error("Источник журнала недоступен"))
    .mockResolvedValueOnce({ events: [{ ...event, id: 8, type: "participant.joined", reason: "guest_join" }], next_before_id: null });
  const api = { listParticipantStatus: status, securityEvents: journal } as unknown as CampaignApi;
  render(<RoomAdmin room={room} accessToken="identity" api={api} onRoom={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Показать участников" }));
  expect(await screen.findByText(/Игрок · игрок · Подключён/)).toBeInTheDocument();
  expect(screen.getByText("Воин · Карта")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Журнал безопасности" }));
  expect(await screen.findByText(/Отключение соединения · Игрок/)).toBeInTheDocument();
  expect(screen.getByText(/Другие соединения участника активны/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Более ранние записи" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Источник журнала недоступен");
  expect(screen.getByText(/Отключение соединения · Игрок/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Более ранние записи" }));
  expect(await screen.findByText(/Вход в комнату · Игрок/)).toBeInTheDocument();
  expect(journal).toHaveBeenLastCalledWith("identity", "r", 9);
  expect(screen.queryByRole("button", { name: "Более ранние записи" })).not.toBeInTheDocument();
});

it("clears identity/room state, ignores late responses, and clears panels on authoritative access denial", async () => {
  let oldResolve!: (value: unknown) => void;
  const status = vi.fn().mockImplementationOnce(() => new Promise(resolve => { oldResolve = resolve; }))
    .mockResolvedValueOnce([summary]).mockRejectedValueOnce(new CampaignApiError("Доступ отозван", 403));
  const journal = vi.fn().mockResolvedValue({ events: [event], next_before_id: null });
  const api = { listParticipantStatus: status, securityEvents: journal } as unknown as CampaignApi;
  const view = render(<RoomAdmin room={room} accessToken="old" api={api} onRoom={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Показать участников" }));
  view.rerender(<RoomAdmin room={{ ...room, id: "new" }} accessToken="new" api={api} onRoom={() => {}} />);
  await act(async () => oldResolve([summary]));
  expect(screen.queryByText(/Игрок · игрок/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Показать участников" }));
  await screen.findByText(/Игрок · игрок/);
  fireEvent.click(screen.getByRole("button", { name: "Журнал безопасности" }));
  await screen.findByText(/Отключение соединения · Игрок/);
  fireEvent.click(screen.getByRole("button", { name: "Показать участников" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Доступ отозван");
  expect(screen.queryByText(/Игрок · игрок/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Отключение соединения · Игрок/)).not.toBeInTheDocument();
  view.rerender(<RoomAdmin room={{ ...room, can_manage: false }} accessToken="new" api={api} onRoom={() => {}} />);
  expect(screen.queryByRole("button", { name: "Журнал безопасности" })).not.toBeInTheDocument();
});
