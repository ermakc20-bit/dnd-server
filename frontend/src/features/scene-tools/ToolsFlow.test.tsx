import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { SceneExperience } from "../scene/SceneExperience";
import type { SceneApi, SceneProjection } from "../scene/types";
import type { RealtimeOptions } from "../realtime/transport";

it("uses versioned fog commands and keeps durable tools read-only until resync", async () => {
  const snapshot: SceneProjection = { room_id:"r",actor_session_id:"gm",aggregate_version:7,event_cursor:7,
    can_manage:true,scenes:[{id:"s",name:"Table"}],items:[],scene:{id:"s",name:"Table",width:4096,height:4096,
      grid_size:64,unit_size:5,unit_label:"фут",grid_enabled:true,snap_enabled:true} };
  let connection: RealtimeOptions;
  const realtimeFactory = (options: RealtimeOptions) => {
    connection=options;
    queueMicrotask(()=>{ options.onSnapshot(snapshot); options.onState("connected"); });
    return { refresh:async()=>{ options.onSnapshot(snapshot);return true; },reconnect:vi.fn(),preview:vi.fn(),close:vi.fn() };
  };
  const api={ command:vi.fn().mockResolvedValue({status:"accepted"}),download:vi.fn() } as unknown as SceneApi;
  render(<SceneExperience room={{id:"r",campaign_id:"c",name:"Table",can_manage:true,is_locked:false,pin_enabled:false,created_at:""}}
    api={api} realtimeFactory={realtimeFactory} rendererFactory={async()=>({render:vi.fn(),destroy:vi.fn()})} />);
  fireEvent.click(await screen.findByRole("button",{name:"Инструменты"}));
  fireEvent.click(screen.getByRole("button",{name:"Закрыть сцену туманом"}));
  await waitFor(()=>expect(api.command).toHaveBeenCalledWith(expect.objectContaining({type:"fog.fill",expected_aggregate_version:7}),undefined));
  act(()=>connection.onState("disconnected"));
  expect(screen.getByRole("button",{name:"Закрыть сцену туманом"})).toBeDisabled();
  fireEvent.click(screen.getByRole("button",{name:"Кубы"}));
  expect(screen.getByRole("button",{name:"Бросить кубы"})).toBeDisabled();
  fireEvent.click(screen.getByRole("button",{name:"Инструменты"}));
  expect(screen.getByRole("button",{name:"Увеличить карту"})).toBeEnabled();
  act(()=>connection.onState("connecting"));
  expect(screen.getByRole("button",{name:"Закрыть сцену туманом"})).toBeDisabled();
  act(()=>{connection.onSnapshot({...snapshot,aggregate_version:8});connection.onState("connected");});
  expect(screen.getByRole("button",{name:"Закрыть сцену туманом"})).toBeEnabled();
});
