import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { cardApi } from "./api";
import { CardsPanel } from "./CardsPanel";
import { blankCard } from "./types";
import type { SceneItem } from "../scene/types";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("preserves an edited draft but prevents replacing newer server state", async () => {
  const card = { ...blankCard(), id: "a", name: "Страж", version: 1, can_edit_structure: true,
    can_edit_current: true, can_export: true, campaign_id: "c", room_id: "r", created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ cards: [card], has_more: false }) }));
  const props = { roomId: "r", canManage: true, disabled: false, version: 1, execute: vi.fn().mockResolvedValue(true),
    players: [], onLoadPlayers: vi.fn(), hasScene: true };
  const view = render(<CardsPanel {...props} />);
  fireEvent.click(await screen.findByRole("button", { name: /Страж/ }));
  fireEvent.click(screen.getByRole("button", { name: "Редактировать карточку" }));
  fireEvent.change(screen.getByLabelText("Название карточки"), { target: { value: "Мой черновик" } });
  view.rerender(<CardsPanel {...props} version={2} />);
  fireEvent.click(screen.getByRole("button", { name: "Сохранить карточку" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Состояние комнаты изменилось"));
  expect(screen.getByLabelText("Название карточки")).toHaveValue("Мой черновик");
  expect(props.execute).not.toHaveBeenCalled();
});

it("launches only an explicitly chosen current linked source and preserves card access gates", async () => {
  const card={...blankCard(),id:"card",name:"Mage",version:1,can_edit_structure:false,can_edit_current:true,
    can_export:false,campaign_id:"c",room_id:"r",created_at:"",updated_at:"",
    abilities:[{id:"ability",schema_version:1 as const,name:"Cone",description:"",action_type:null,uses:null,
      automation:null,visibility:"everyone" as const,geometry:{shape:"cone" as const,origin:"token" as const,length:10,angle:90,units:"фут"}}]};
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({cards:[card],has_more:false})}));
  const item:SceneItem={id:"a",name:"Source A",kind:"token",asset_id:null,x:0,y:0,width:64,height:64,rotation:0,
    z_index:0,visibility:"everyone",is_locked:false,owner_participant_id:null,can_transform:false,card_id:"card"};
  const props={roomId:"r",canManage:false,disabled:false,version:1,execute:vi.fn(),players:[],onLoadPlayers:vi.fn(),hasScene:true,
    abilitySources:[item,{...item,id:"b",name:"Source B"},{...item,id:"other",name:"Other card",card_id:"other"},{...item,id:"map",name:"Map",kind:"map" as const}],onPresentAbility:vi.fn()};
  const view=render(<CardsPanel {...props}/>);
  fireEvent.click(await screen.findByRole("button",{name:/Mage/}));
  expect(props.onPresentAbility).not.toHaveBeenCalled();
  expect(screen.queryByRole("button",{name:/источник: Other card|источник: Map/})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"Показать область: Cone · источник: Source B"}));
  expect(props.onPresentAbility).toHaveBeenCalledExactlyOnceWith({cardId:"card",ability:card.abilities[0],sourceTokenId:"b"});
  view.rerender(<CardsPanel {...props} disabled/>);
  expect(screen.getByRole("button",{name:/источник: Source A/})).toBeDisabled();
  view.rerender(<CardsPanel {...props} abilitySources={[]}/>);
  expect(screen.queryByRole("button",{name:/источник:/})).not.toBeInTheDocument();
  view.rerender(<CardsPanel {...props} hasScene={false}/>);
  expect(screen.getByRole("button",{name:/источник: Source B/})).toBeDisabled();
  card.can_edit_current=false;
  view.rerender(<CardsPanel {...props}/>);
  expect(screen.queryByRole("button",{name:/Показать область:/})).not.toBeInTheDocument();
  card.can_edit_current=true;
  view.rerender(<CardsPanel {...props} auxiliary/>);
  expect(screen.queryByRole("button",{name:/Показать область:/})).not.toBeInTheDocument();
});

it("keeps confirmed cards read-only when their refresh fails", async () => {
  const card = { ...blankCard(), id: "a", name: "Страж", version: 1, can_edit_structure: false,
    can_edit_current: true, can_export: false, campaign_id: "c", room_id: "r", created_at: "", updated_at: "",
    resources: [{ key: "blood", label: "Очки крови", current: 5, max: 8, color: null, visibility: "everyone" }] };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ cards: [card], has_more: false }) })
    .mockRejectedValue(new Error("Сеть недоступна")));
  render(<CardsPanel roomId="r" canManage={false} disabled={false} version={1} execute={vi.fn()}
    players={[]} onLoadPlayers={vi.fn()} hasScene />);
  fireEvent.click(await screen.findByRole("button", { name: /Страж/ }));
  fireEvent.click(screen.getByRole("button", { name: "Обновить карточки" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Сеть недоступна");
  expect(screen.getByRole("button", { name: "Сохранить Очки крови" })).toBeDisabled();
  expect(screen.getByRole("spinbutton", { name: "Текущее: Очки крови" })).toHaveValue(5);
});

it("opens details immediately and returns to the same search without reloading the library", async () => {
  const card = { ...blankCard(), id: "guard", name: "Страж", version: 1, campaign_id: "c", room_id: "r",
    created_at: "", updated_at: "", can_edit_structure: false, can_edit_current: false, can_export: false };
  const list = vi.spyOn(cardApi, "list").mockResolvedValue({ cards: [card], has_more: false, offset: 0, limit: 20 });
  render(<CardsPanel roomId="r" canManage={false} disabled={false} version={1} execute={vi.fn()} players={[]} onLoadPlayers={vi.fn()} hasScene />);
  fireEvent.change(screen.getByLabelText("Поиск карточек"), { target: { value: "Страж" } });
  fireEvent.click(await screen.findByRole("button", { name: /Страж/ }));
  expect(screen.getByRole("heading", { name: "Страж" })).toHaveFocus();
  const calls = list.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "К списку карточек" }));
  expect(screen.queryByRole("article")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Поиск карточек")).toHaveValue("Страж");
  expect(screen.getByLabelText("Поиск карточек")).toHaveFocus();
  expect(list).toHaveBeenCalledTimes(calls);
  list.mockRestore();
});
