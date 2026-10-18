import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DicePanel } from "./DicePanel";

afterEach(() => vi.unstubAllGlobals());
it("shows the unchanged revoked roll and reuses journal compensation with offline rights", async () => {
  const entries = [{cursor: 4, aggregate_version: 4, actor_name: "GM", occurred_at: "2026-10-15T00:00:00Z",
    action: "Бросок кубов", type: "dice.roll", result: "accepted", visibility: "everyone", can_undo: false,
    revoked: true, roll: {expression: "2d6+3", results: [2, 5], modifier: 3, total: 10}},
    {cursor: 5, aggregate_version: 5, actor_name: "GM", occurred_at: "2026-10-15T00:00:01Z",
      action: "Создана сцена", type: "scene.create", result: "accepted", visibility: "everyone", can_undo: true,
      revoked: false, roll: null}];
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok: true, json: async () => ({entries,next_cursor:null})}));
  const execute = vi.fn().mockResolvedValue(true);
  const props = {roomId:"r",canManage:true,disabled:false,version:5,execute};
  const view = render(<DicePanel {...props}/>);
  expect(await screen.findByText("Бросок отменён мастером")).toBeVisible();
  expect(screen.getByText("2d6+3: [2, 5] +3 = 10")).toBeVisible();
  fireEvent.click(screen.getByRole("button", {name:"Отменить последнее действие"}));
  await waitFor(() => expect(execute).toHaveBeenCalledExactlyOnceWith("action.undo", {event_cursor:5}));
  view.rerender(<DicePanel {...props} disabled/>);
  expect(screen.getByRole("button", {name:"Отменить последнее действие"})).toBeDisabled();
  view.rerender(<DicePanel {...props} canManage={false}/>);
  expect(screen.queryByRole("button", {name:"Отменить последнее действие"})).toBeNull();
});
