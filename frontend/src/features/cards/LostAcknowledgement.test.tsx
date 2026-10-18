import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SceneExperience } from "../scene/SceneExperience";
import type { SceneApi } from "../scene/types";
import { testTransport } from "../realtime/testTransport";

afterEach(() => vi.unstubAllGlobals());

it("finalizes the original native-card draft after a lost acknowledgement is recovered", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true,
    json: async () => ({ cards: [], has_more: false }) }));
  const empty = { room_id: "r", actor_session_id: "gm", aggregate_version: 0,
    event_cursor: 0, can_manage: true, scenes: [], scene: null, items: [] };
  const command = vi.fn().mockRejectedValueOnce(new Error("Acknowledgement lost"))
    .mockResolvedValueOnce({ status: "duplicate", aggregate_version: 1, event_cursor: 1 })
    .mockResolvedValue({ status: "accepted", aggregate_version: 2, event_cursor: 2 });
  const api = { projection: vi.fn().mockResolvedValueOnce(empty)
    .mockResolvedValue({ ...empty, aggregate_version: 1, event_cursor: 1 }), command } as unknown as SceneApi;
  render(<SceneExperience room={{ id: "r", campaign_id: "c", name: "Стол", is_locked: false,
    pin_enabled: false, created_at: "", can_manage: true }} accessToken="credential" api={api} realtimeFactory={testTransport(api)} />);
  fireEvent.click(await screen.findByRole("button", { name: "Карточки" }));
  fireEvent.click(screen.getByRole("button", { name: "Новая карточка" }));
  fireEvent.change(screen.getByLabelText("Название карточки"), { target: { value: "Один страж" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить карточку" }));
  await screen.findByText("Acknowledgement lost");
  expect(screen.getByRole("button", { name: "Сохранить карточку" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Повторить неподтверждённую команду" }));
  await waitFor(() => expect(screen.queryByRole("button", {
    name: "Повторить неподтверждённую команду",
  })).not.toBeInTheDocument());
  expect(command).toHaveBeenCalledTimes(2);
  expect(command.mock.calls[1][0]).toEqual(command.mock.calls[0][0]);
  const saveAgain = screen.queryByRole("button", { name: "Сохранить карточку" });
  if (saveAgain) {
    await waitFor(() => expect(saveAgain).not.toBeDisabled());
    fireEvent.click(saveAgain);
    await waitFor(() => expect(command).toHaveBeenCalledTimes(3));
    expect(command.mock.calls[2][0].type).toBe("card.create");
    expect(command.mock.calls[2][0].command_id).not.toBe(command.mock.calls[0][0].command_id);
  }
  expect(command).toHaveBeenCalledTimes(2);
  expect(screen.queryByLabelText("Название карточки")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Новая карточка" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Новая карточка" }));
  expect(screen.getByLabelText("Название карточки")).toHaveValue("");
  expect(command).toHaveBeenCalledTimes(2);
});
