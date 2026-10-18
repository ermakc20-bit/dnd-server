import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { SceneCanvas } from "../scene/SceneCanvas";
import type { SceneProjection } from "../scene/types";
import type { AbilitySelection } from "./types";
import { Viewport } from "../../renderer/viewport";

it("selects an explicit card token without dragging and maps keyboard direction through the viewport",async()=>{
  const projection:SceneProjection={room_id:"r",actor_session_id:"p",aggregate_version:1,event_cursor:1,
    can_manage:false,scenes:[],scene:{id:"s",name:"Test",width:4096,height:4096,grid_size:64,
      grid_enabled:true,snap_enabled:true,unit_size:5,unit_label:"фут"},items:[{
        id:"token",kind:"token",name:"Caster",asset_id:null,x:128,y:128,width:64,height:64,rotation:0,
        z_index:0,visibility:"everyone",is_locked:false,owner_participant_id:"p",can_transform:true,card_id:"card"}]};
  const selection:AbilitySelection={cardId:"card",ability:{id:"a",schema_version:1,name:"Cube",description:"",
    action_type:null,uses:null,automation:null,visibility:"everyone",geometry:{shape:"cube",origin:"token",length:10,units:"фут"}}};
  const draw=vi.fn(),move=vi.fn(),command=vi.fn();
  render(<SceneCanvas projection={projection} assetUrls={new Map()} onMove={move} onSelect={vi.fn()}
    disabled={false} abilitySelection={selection} onAbilityCommand={command}
    factory={async()=>({render:draw,destroy:vi.fn()})}/>);
  await waitFor(()=>expect(draw).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button",{name:"Повернуть вид карты"}));
  fireEvent.click(screen.getByRole("button",{name:"Увеличить карту"}));
  fireEvent.click(screen.getByRole("button",{name:"Источник: Caster"}));
  const map=screen.getByRole("region",{name:"Карта и токены"});
  fireEvent.keyDown(map,{key:"ArrowRight"});fireEvent.keyDown(map,{key:"Enter"});
  expect(move).not.toHaveBeenCalled();expect(command).not.toHaveBeenCalled();
  expect(draw.mock.lastCall?.[0].abilityPreview).toMatchObject({shape:"cube",origin:{x:160,y:160},length:128});
  fireEvent.click(screen.getByRole("button",{name:"Показать способность"}));
  expect(command).toHaveBeenCalledWith("ability.present",{card_id:"card",ability_id:"a",origin_item_id:"token",direction:{x:144,y:128}});
});

const sourceProjection:SceneProjection={room_id:"r",actor_session_id:"p",aggregate_version:1,event_cursor:1,
  can_manage:false,scenes:[],scene:{id:"s",name:"Test",width:4096,height:4096,grid_size:64,grid_enabled:true,
    snap_enabled:true,unit_size:5,unit_label:"фут"},items:[{id:"source",kind:"token",name:"Caster",asset_id:null,
    x:128,y:128,width:64,height:64,rotation:0,z_index:0,visibility:"everyone",is_locked:false,
    owner_participant_id:"p",can_transform:true,card_id:"card"}]};
const pointSelection:AbilitySelection={cardId:"card",ability:{id:"a",schema_version:1,name:"Cone",description:"",
  action_type:null,uses:null,automation:null,visibility:"everyone",geometry:{shape:"cone",origin:"point",length:10,angle:90,units:"фут"}}};
const tokenSelection:AbilitySelection={...pointSelection,sourceTokenId:"source",
  ability:{...pointSelection.ability,geometry:{...pointSelection.ability.geometry!,origin:"token"}}};

function pointer(surface:HTMLElement,type:string,x:number,y:number) {
  const event=new MouseEvent(type,{clientX:x,clientY:y,bubbles:true});
  Object.defineProperty(event,"pointerType",{value:"touch"});fireEvent(surface,event);
}

it("previews, moves and rotates one touch placement in world space without moving a token, then confirms once",async()=>{
  const draw=vi.fn(),move=vi.fn(),preview=vi.fn(),command=vi.fn();
  render(<SceneCanvas projection={sourceProjection} assetUrls={new Map()} onMove={move} onPreview={preview} onSelect={vi.fn()}
    disabled={false} abilitySelection={pointSelection} onAbilityCommand={command}
    factory={async()=>({render:draw,destroy:vi.fn()})}/>);
  await waitFor(()=>expect(draw).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button",{name:"Повернуть вид карты"}));
  fireEvent.click(screen.getByRole("button",{name:"Увеличить карту"}));
  const viewport=new Viewport();viewport.rotateAt({x:320,y:240},Math.PI/4);viewport.zoomAt({x:320,y:240},1.25);
  const surface=screen.getByRole("region",{name:"Карта и токены"});
  pointer(surface,"pointerdown",128,128);pointer(surface,"pointermove",256,192);
  let area=draw.mock.lastCall?.[0].abilityPreview;
  expect(area.origin.x).toBeCloseTo(viewport.screenToWorld({x:128,y:128}).x);
  expect(area.origin.y).toBeCloseTo(viewport.screenToWorld({x:128,y:128}).y);
  expect(command).not.toHaveBeenCalled();
  pointer(surface,"pointerup",256,192);
  pointer(surface,"pointerdown",320,160);pointer(surface,"pointermove",192,256);pointer(surface,"pointerup",192,256);
  area=draw.mock.lastCall?.[0].abilityPreview;
  const origin=viewport.screenToWorld({x:320,y:160}),direction=viewport.screenToWorld({x:192,y:256});
  expect(area.origin).toEqual(origin);expect(area.rotation).toBeCloseTo(Math.atan2(direction.y-origin.y,direction.x-origin.x));
  expect(move).not.toHaveBeenCalled();expect(preview).not.toHaveBeenCalled();expect(command).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"Показать способность"}));
  expect(command).toHaveBeenCalledExactlyOnceWith("ability.present",{card_id:"card",ability_id:"a",origin,direction});
  expect(sourceProjection.items[0]).toMatchObject({x:128,y:128});
});

it.each(["missing","wrong-card","map","deleted","scene","offline"] as const)("discards a %s source rather than reauthorizing a stale choice",async(kind)=>{
  const draw=vi.fn(),command=vi.fn();
  const props={projection:sourceProjection,assetUrls:new Map<string,string>(),onMove:vi.fn(),onSelect:vi.fn(),
    disabled:false,abilitySelection:kind==="missing"?{...tokenSelection,sourceTokenId:"absent"}:tokenSelection,
    onAbilityCommand:command,factory:async()=>({render:draw,destroy:vi.fn()})};
  const view=render(<SceneCanvas {...props}/>);
  await waitFor(()=>expect(draw).toHaveBeenCalled());
  const surface=screen.getByRole("region",{name:"Карта и токены"});
  pointer(surface,"pointerdown",256,128);pointer(surface,"pointerup",256,128);
  if(kind!=="missing") {
    expect(screen.getByRole("button",{name:"Показать способность"})).toBeEnabled();
    const changed=kind==="deleted"?{...sourceProjection,items:[]}:
      kind==="wrong-card"?{...sourceProjection,items:[{...sourceProjection.items[0],card_id:"other"}]}:
      kind==="map"?{...sourceProjection,items:[{...sourceProjection.items[0],kind:"map" as const}]}:
      kind==="scene"?{...sourceProjection,scene:{...sourceProjection.scene!,id:"other"}}:sourceProjection;
    view.rerender(<SceneCanvas {...props} projection={changed} disabled={kind==="offline"}/>);
    if(kind==="offline")view.rerender(<SceneCanvas {...props}/>);
  }
  await waitFor(()=>expect(draw.mock.lastCall?.[0].abilityPreview).toBeNull());
  const confirm=screen.queryByRole("button",{name:"Показать способность"});
  if(confirm){expect(confirm).toBeDisabled();fireEvent.click(confirm);}
  expect(command).not.toHaveBeenCalled();
});

it("cancels a touch placement and rejects an unbounded release without a durable command",async()=>{
  const draw=vi.fn(),command=vi.fn(),cancel=vi.fn();
  render(<SceneCanvas projection={sourceProjection} assetUrls={new Map()} onMove={vi.fn()} onSelect={vi.fn()}
    disabled={false} abilitySelection={pointSelection} onAbilityCancel={cancel} onAbilityCommand={command}
    factory={async()=>({render:draw,destroy:vi.fn()})}/>);
  await waitFor(()=>expect(draw).toHaveBeenCalled());
  const surface=screen.getByRole("region",{name:"Карта и токены"});
  pointer(surface,"pointerdown",128,128);pointer(surface,"pointermove",256,128);pointer(surface,"pointercancel",256,128);
  expect(cancel).toHaveBeenCalledOnce();expect(draw.mock.lastCall?.[0].abilityPreview).toBeNull();
  pointer(surface,"pointerdown",128,128);pointer(surface,"pointermove",256,128);pointer(surface,"pointerup",1000001,128);
  expect(draw.mock.lastCall?.[0].abilityPreview).toBeNull();
  expect(screen.getByRole("button",{name:"Показать способность"})).toBeDisabled();
  expect(command).not.toHaveBeenCalled();
});

it("does not finish a gesture against a replacement projection or after pending read-only state",async()=>{
  const draw=vi.fn(),command=vi.fn();
  const props={projection:sourceProjection,assetUrls:new Map<string,string>(),onMove:vi.fn(),onSelect:vi.fn(),
    disabled:false,abilitySelection:pointSelection,onAbilityCommand:command,factory:async()=>({render:draw,destroy:vi.fn()})};
  const view=render(<SceneCanvas {...props}/>);
  await waitFor(()=>expect(draw).toHaveBeenCalled());
  const surface=screen.getByRole("region",{name:"Карта и токены"});
  pointer(surface,"pointerdown",128,128);pointer(surface,"pointermove",256,128);
  view.rerender(<SceneCanvas {...props} projection={{...sourceProjection,aggregate_version:2}}/>);
  pointer(surface,"pointerup",256,128);
  expect(draw.mock.lastCall?.[0].abilityPreview).toBeNull();
  pointer(surface,"pointerdown",128,128);pointer(surface,"pointermove",256,128);
  view.rerender(<SceneCanvas {...props} disabled/>);
  pointer(surface,"pointerup",256,128);
  view.rerender(<SceneCanvas {...props}/>);
  expect(draw.mock.lastCall?.[0].abilityPreview).toBeNull();
  expect(screen.getByRole("button",{name:"Показать способность"})).toBeDisabled();
  expect(command).not.toHaveBeenCalled();
});

it.each(["circle","radius","cone","line","cube"] as const)("moves the same %s point draft from A to B and confirms only B",async(shape)=>{
  const selection:AbilitySelection={...pointSelection,ability:{...pointSelection.ability,
    geometry:{...pointSelection.ability.geometry!,shape,radius:10,width:5}}};
  const draw=vi.fn(),command=vi.fn();
  render(<SceneCanvas projection={sourceProjection} assetUrls={new Map()} onMove={vi.fn()} onSelect={vi.fn()}
    disabled={false} abilitySelection={selection} onAbilityCommand={command}
    factory={async()=>({render:draw,destroy:vi.fn()})}/>);
  await waitFor(()=>expect(draw).toHaveBeenCalled());
  const surface=screen.getByRole("region",{name:"Карта и токены"}),directed=["cone","line","cube"].includes(shape);
  for(const [origin,direction] of [[{x:128,y:128},{x:256,y:128}],[{x:320,y:256},{x:320,y:128}]] as const) {
    pointer(surface,"pointerdown",origin.x,origin.y);
    if(directed)pointer(surface,"pointermove",direction.x,direction.y);
    pointer(surface,"pointerup",directed?direction.x:origin.x,directed?direction.y:origin.y);
    expect(draw.mock.lastCall?.[0].abilityPreview).toMatchObject({shape,origin});
    expect(command).not.toHaveBeenCalled();
  }
  fireEvent.click(screen.getByRole("button",{name:"Показать способность"}));
  expect(command).toHaveBeenCalledExactlyOnceWith("ability.present",{card_id:"card",ability_id:"a",origin:{x:320,y:256},
    ...(directed?{direction:{x:320,y:128}}:{})});
});
