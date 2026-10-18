import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { cardApi } from "../cards/api";
import { blankCard, type Card } from "../cards/types";
import type { RealtimeOptions } from "../realtime/transport";
import { SceneExperience } from "../scene/SceneExperience";
import type { SceneApi, SceneProjection } from "../scene/types";
import type { Geometry } from "./types";

it("preserves staged point placement and clears ephemeral drafts on cancel or reconnect", async () => {
  const card:Card={...blankCard(),id:"card",campaign_id:"c",room_id:"r",name:"Mage",version:1,
    owner_participant_id:"player",can_edit_structure:false,can_edit_current:true,can_export:false,
    created_at:"",updated_at:"",abilities:[{id:"ability",schema_version:1,name:"Cone",description:"",
      action_type:null,uses:null,automation:null,visibility:"everyone",
      geometry:{shape:"cone",origin:"point",length:10,angle:90,units:"фут",range:null,radius:null,width:null,color:null}}]};
  vi.spyOn(cardApi,"list").mockResolvedValue({cards:[card],offset:0,limit:20,has_more:false});
  const snapshot:SceneProjection={room_id:"r",actor_session_id:"player",aggregate_version:7,event_cursor:7,
    can_manage:false,scenes:[{id:"s",name:"Table"}],items:[],scene:{id:"s",name:"Table",width:4096,height:4096,
      grid_size:64,unit_size:5,unit_label:"фут",grid_enabled:true,snap_enabled:true}};
  let connection:RealtimeOptions;
  const realtimeFactory=(options:RealtimeOptions)=>{
    connection=options;queueMicrotask(()=>{options.onSnapshot(snapshot);options.onState("connected");});
    return {refresh:async()=>{options.onSnapshot({...snapshot,aggregate_version:8});return true;},reconnect:vi.fn(),preview:vi.fn(),close:vi.fn()};
  };
  const command=vi.fn().mockResolvedValue({status:"accepted"}),draw=vi.fn();
  render(<SceneExperience room={{id:"r",campaign_id:"c",name:"Table",can_manage:false,is_locked:false,pin_enabled:false,created_at:""}}
    api={{command,download:vi.fn()} as unknown as SceneApi} realtimeFactory={realtimeFactory}
    rendererFactory={async()=>({render:draw,destroy:vi.fn()})}/>);
  fireEvent.click(await screen.findByRole("button",{name:"Карточки"}));
  fireEvent.click(await screen.findByRole("button",{name:/Mage/}));
  fireEvent.click(await screen.findByRole("button",{name:"Показать область: Cone"}));
  const map=screen.getByRole("region",{name:"Карта и токены"});
  function tap(x:number,y:number){for(const type of ["pointerdown","pointerup"]){
    const event=new MouseEvent(type,{clientX:x,clientY:y,bubbles:true});
    Object.defineProperty(event,"pointerType",{value:"touch"});fireEvent(map,event);
  }}
  tap(128,128);tap(256,128);
  expect(command).not.toHaveBeenCalled();
  await waitFor(()=>expect(draw.mock.lastCall?.[0].abilityPreview?.shape).toBe("cone"));
  fireEvent.click(screen.getByRole("button",{name:"Показать способность"}));
  await waitFor(()=>expect(command).toHaveBeenCalledTimes(1));
  expect(command.mock.calls[0][0]).toMatchObject({type:"ability.present",payload:{card_id:"card",ability_id:"ability",origin:{x:128,y:128},direction:{x:256,y:128}}});
  await waitFor(()=>expect(screen.queryByRole("button",{name:"Показать способность"})).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole("button",{name:"Карточки"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"Показать область: Cone"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button",{name:"Показать область: Cone"}));tap(128,128);
  fireEvent.click(screen.getByRole("button",{name:"Отменить область"}));
  expect(command).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button",{name:"Карточки"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"Показать область: Cone"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button",{name:"Показать область: Cone"}));tap(128,128);
  act(()=>connection.onState("disconnected"));
  expect(screen.queryByRole("button",{name:"Показать способность"})).not.toBeInTheDocument();
  await waitFor(()=>expect(draw.mock.lastCall?.[0].abilityPreview).toBeNull());
  act(()=>{connection.onSnapshot({...snapshot,aggregate_version:9});connection.onState("connected");});
  expect(screen.queryByRole("button",{name:"Показать способность"})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"Карточки"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"Показать область: Cone"})).toBeEnabled());
  await waitFor(()=>expect(screen.getByRole("button",{name:"Показать область: Cone"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button",{name:"Показать область: Cone"}));tap(128,128);
  fireEvent.click(screen.getByRole("button",{name:"Линия"}));
  expect(screen.queryByRole("button",{name:"Показать способность"})).not.toBeInTheDocument();
  tap(128,128);tap(256,128);
  await waitFor(()=>expect(command).toHaveBeenCalledTimes(2));
  expect(command.mock.calls[1][0].type).toBe("annotation.create");
});

const launchCases = (["token", "point"] as const).flatMap(origin =>
  (["circle", "radius", "cone", "line", "cube"] as const).map(shape => ({ origin, shape })));

it.each(launchCases)("launches $origin $shape from the open card in at most three complete touch actions", async ({ origin, shape }) => {
  const geometry:Geometry={shape,origin,radius:10,length:10,width:5,angle:90,units:"фут"};
  const card:Card={...blankCard(),id:"card",campaign_id:"c",room_id:"r",name:"Mage",version:1,
    owner_participant_id:"player",can_edit_structure:false,can_edit_current:true,can_export:false,
    created_at:"",updated_at:"",abilities:[{id:"ability",schema_version:1,name:"Area",description:"",
      action_type:null,uses:null,automation:null,visibility:"everyone",geometry}]};
  vi.spyOn(cardApi,"list").mockResolvedValue({cards:[card],offset:0,limit:20,has_more:false});
  const source={kind:"token" as const,asset_id:null,x:128,y:128,width:64,height:64,rotation:0,z_index:0,
    visibility:"everyone" as const,is_locked:false,owner_participant_id:"player",can_transform:true,card_id:"card"};
  const snapshot:SceneProjection={room_id:"r",actor_session_id:"player",aggregate_version:7,event_cursor:7,
    can_manage:false,scenes:[{id:"s",name:"Table"}],items:[{...source,id:"a",name:"Source A"},{...source,id:"b",name:"Source B",x:320}],
    scene:{id:"s",name:"Table",width:4096,height:4096,grid_size:64,unit_size:5,unit_label:"фут",grid_enabled:true,snap_enabled:true}};
  let connection!:RealtimeOptions;
  const realtimeFactory=(options:RealtimeOptions)=>{
    connection=options;queueMicrotask(()=>{options.onSnapshot(snapshot);options.onState("connected");});
    return {refresh:async()=>{options.onSnapshot({...snapshot,aggregate_version:8});return true;},reconnect:vi.fn(),preview:vi.fn(),close:vi.fn()};
  };
  let complete!:(result:{status:string})=>void;
  const command=vi.fn().mockImplementation(()=>new Promise(resolve=>{complete=resolve;})),draw=vi.fn();
  render(<SceneExperience room={{id:"r",campaign_id:"c",name:"Table",can_manage:false,is_locked:false,pin_enabled:false,created_at:""}}
    api={{command,download:vi.fn()} as unknown as SceneApi} realtimeFactory={realtimeFactory}
    rendererFactory={async()=>({render:draw,destroy:vi.fn()})}/>);
  fireEvent.click(await screen.findByRole("button",{name:"Карточки"}));
  fireEvent.click(await screen.findByRole("button",{name:/Mage/}));
  const launchName=origin==="token"?"Показать область: Area · источник: Source B":"Показать область: Area";
  let actions=0;
  fireEvent.click(screen.getByRole("button",{name:launchName}));actions++;
  const map=screen.getByRole("region",{name:"Карта и токены"});
  function pointer(type:string,x:number,y:number) {
    const event=new MouseEvent(type,{clientX:x,clientY:y,bubbles:true});
    Object.defineProperty(event,"pointerType",{value:"touch"});fireEvent(map,event);
  }
  const directed=["cone","line","cube"].includes(shape);
  if(origin==="point") {
    pointer("pointerdown",128,128);
    if(directed)pointer("pointermove",256,192);
    pointer("pointerup",directed?256:128,directed?192:128);actions++;
  } else if(directed) {pointer("pointerdown",480,192);pointer("pointerup",480,192);actions++;}
  await waitFor(()=>expect(draw.mock.lastCall?.[0].abilityPreview).toMatchObject({shape,origin:origin==="token"?{x:352,y:160}:{x:128,y:128}}));
  expect(command).not.toHaveBeenCalled();
  expect(snapshot.items.map(item=>[item.x,item.y])).toEqual([[128,128],[320,128]]);
  fireEvent.click(screen.getByRole("button",{name:"Показать способность"}));actions++;
  expect(actions).toBeLessThanOrEqual(3);
  await waitFor(()=>expect(command).toHaveBeenCalledTimes(1));
  expect(command.mock.calls[0][0]).toMatchObject({type:"ability.present",payload:{
    card_id:"card",ability_id:"ability",...(origin==="token"?{origin_item_id:"b"}:{origin:{x:128,y:128}}),
    ...(directed?{direction:origin==="token"?{x:480,y:192}:{x:256,y:192}}:{})}});
  fireEvent.click(screen.getByRole("button",{name:"Карточки"}));
  expect(screen.getByRole("button",{name:launchName})).toBeDisabled();
  act(()=>complete({status:"accepted"}));
  await waitFor(()=>expect(screen.queryByRole("button",{name:"Показать способность"})).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole("button",{name:launchName}));
  act(()=>connection.onState("disconnected"));
  expect(screen.queryByRole("button",{name:"Показать способность"})).not.toBeInTheDocument();
  act(()=>{connection.onSnapshot({...snapshot,aggregate_version:9});connection.onState("connected");});
  await waitFor(()=>expect(draw.mock.lastCall?.[0].abilityPreview).toBeNull());
  expect(command).toHaveBeenCalledTimes(1);
});
