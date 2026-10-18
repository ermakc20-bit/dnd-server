import { useLayoutEffect, useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { SceneCanvas } from "../scene/SceneCanvas";
import type { SceneProjection } from "../scene/types";

it("measures in world units after zoom/rotation and creates one touch or keyboard mark",async()=>{
  const projection:SceneProjection={room_id:"r",actor_session_id:"p",aggregate_version:1,event_cursor:1,
    can_manage:true,scenes:[],items:[],scene:{id:"s",name:"Test",width:4096,height:4096,grid_size:64,grid_enabled:true,snap_enabled:true,unit_size:5,unit_label:"фут"}};
  const draw=vi.fn(),onToolCommand=vi.fn();
  const props={projection,assetUrls:new Map<string,string>(),onMove:vi.fn(),onSelect:vi.fn(),disabled:false,
    onToolCommand,factory:async()=>({render:draw,destroy:vi.fn()})};
  const view=render(<SceneCanvas {...props} tool="ruler"/>);
  await waitFor(()=>expect(draw).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button",{name:"Увеличить карту"}));
  fireEvent.click(screen.getByRole("button",{name:"Повернуть вид карты"}));
  const surface=screen.getByRole("region",{name:"Карта и токены"});
  function tap(x:number,y:number){
    for(const type of ["pointerdown","pointerup"]){
      const event=new MouseEvent(type,{clientX:x,clientY:y,bubbles:true});
      Object.defineProperty(event,"pointerType",{value:"touch"});fireEvent(surface,event);
    }
  }
  tap(320,240);tap(400,240);
  expect(screen.getByLabelText("Расстояние")).toHaveTextContent("5.00 фут");
  expect(onToolCommand).not.toHaveBeenCalled();
  view.rerender(<SceneCanvas {...props} tool="arrow"/>);
  tap(320,240);tap(400,240);
  expect(onToolCommand).toHaveBeenCalledTimes(1);
  const payload=onToolCommand.mock.calls[0][1];
  expect(payload.kind).toBe("arrow");
  expect(Math.hypot(payload.points[1].x-payload.points[0].x,payload.points[1].y-payload.points[0].y)).toBeCloseTo(64);
  view.rerender(<SceneCanvas {...props} tool="line"/>);
  fireEvent.keyDown(surface,{key:"Enter"});fireEvent.keyDown(surface,{key:"ArrowRight"});fireEvent.keyDown(surface,{key:"Enter"});
  expect(onToolCommand).toHaveBeenCalledTimes(2);
  expect(onToolCommand.mock.calls[1][1].points[1].x-onToolCommand.mock.calls[1][1].points[0].x).toBe(16);
  view.rerender(<SceneCanvas {...props} tool="arrow" disabled/>);tap(320,240);tap(400,240);
  expect(onToolCommand).toHaveBeenCalledTimes(2);
});


it("keeps the first keyboard point when a tool changes before passive effects",async()=>{
  const projection:SceneProjection={room_id:"r",actor_session_id:"p",aggregate_version:1,event_cursor:1,
    can_manage:true,scenes:[],items:[],scene:{id:"s",name:"Test",width:4096,height:4096,grid_size:64,grid_enabled:true,snap_enabled:true,unit_size:5,unit_label:"фут"}};
  const draw=vi.fn(),onToolCommand=vi.fn();
  const factory=async()=>({render:draw,destroy:vi.fn()});
  function RapidSwitch(){
    const [tool,setTool]=useState<"ruler"|"line">("ruler");
    useLayoutEffect(()=>{if(tool==="line")screen.getByRole("region",{name:"Карта и токены"}).dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}));},[tool]);
    return <><button onClick={()=>setTool("line")}>Сменить инструмент</button>
      <SceneCanvas projection={projection} assetUrls={new Map()} onMove={vi.fn()} onSelect={vi.fn()}
        disabled={false} tool={tool} onToolCommand={onToolCommand} factory={factory}/></>;
  }
  render(<RapidSwitch/>);await waitFor(()=>expect(draw).toHaveBeenCalled());
  const map=screen.getByRole("region",{name:"Карта и токены"});
  for(const x of [64,128])for(const type of ["pointerdown","pointerup"])fireEvent(map,new MouseEvent(type,{clientX:x,clientY:64,bubbles:true}));
  expect(screen.getByLabelText("Расстояние")).toHaveTextContent("5.00 фут");
  fireEvent.click(screen.getByRole("button",{name:"Сменить инструмент"}));
  fireEvent.keyDown(map,{key:"ArrowRight"});fireEvent.keyDown(map,{key:"Enter"});
  expect(onToolCommand).toHaveBeenCalledTimes(1);
  expect(onToolCommand.mock.calls[0][1].kind).toBe("line");
  expect(onToolCommand.mock.calls[0][1].points[1].x-onToolCommand.mock.calls[0][1].points[0].x).toBe(16);
});
