import "../scene-tools/tools.css";

import { ToolOverlay } from "../scene-tools/ToolOverlay";
import type { TableTool } from "../scene-tools/types";
import { useEffect, useRef, useState } from "react";
import type { PointerEvent } from "react";

import { createPixiRenderer, type RendererFactory, type SceneRenderer } from "../../renderer/PixiSceneRenderer";
import { buildFrame, hitTest, Viewport, type ItemPreview, type Point } from "../../renderer/viewport";
import type { SceneItem, SceneProjection } from "./types";
import type { AbilitySelection } from "../ability-geometry/types";
import { directed, previewGeometry } from "../ability-geometry/geometry";
import { AbilityControls } from "../ability-geometry/AbilityControls";

export function SceneCanvas({ projection, assetUrls, onMove, onSelect, disabled,
  factory = createPixiRenderer, onAssetError,
  remotePreview, onPreview, tool="select", onToolCommand, annotationLabel="Метка", annotationVisibility="everyone",
  abilitySelection=null,onAbilityCancel,onAbilityCommand,selectedId=null,onExitTool,
}: {
  projection: SceneProjection; assetUrls: ReadonlyMap<string, string>; disabled: boolean;
  onMove(id: string, position: Point): void; onSelect(item: SceneItem | null): void;
  factory?: RendererFactory; onAssetError?(message: string): void;
  remotePreview?: ItemPreview | null; onPreview?(preview: ItemPreview | null): void;
  tool?:TableTool;onToolCommand?(type:string,payload:Record<string,unknown>):void;
  annotationLabel?:string;annotationVisibility?:"everyone"|"gm_only";
  selectedId?: string | null; onExitTool?(): void;
  abilitySelection?:AbilitySelection|null;onAbilityCancel?():void;
  onAbilityCommand?(type:string,payload:Record<string,unknown>):void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const viewport = useRef(new Viewport());
  const renderer = useRef<SceneRenderer | null>(null);
  const gesture = useRef<{ start: Point; original: Point; item: SceneItem | null } | null>(null);
  const previewRef = useRef<ItemPreview | null>(null);
  const [preview, setPreview] = useState<ItemPreview | null>(null);
  const [revision, setRevision] = useState(0);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toolDraft,setToolDraft]=useState<{tool:TableTool;points:Point[]}>({tool,points:[]});
  const toolPoints=toolDraft.tool===tool?toolDraft.points:[];
  function setToolPoints(points:Point[]) {setToolDraft({tool,points});}
  const [hover,setHover]=useState<Point|null>(null);
  const [cursor,setCursor]=useState<Point>({x:128,y:128});
  const toolGesture=useRef<Point|null>(null);
  const toolAllowed=tool==="ruler"||(!disabled&&(!tool.startsWith("fog.")||projection.can_manage));
  const [abilityDraft,setAbilityDraft]=useState<{selection:AbilitySelection;projection:SceneProjection;origin:Point|null;itemId:string|null;direction:Point|null}|null>(null);
  const abilityGesture=useRef<{selection:AbilitySelection;projection:SceneProjection;start:Point;pointerId:number;dragging:boolean}|null>(null);
  const activeAbility=disabled?null:abilitySelection;
  const draft=activeAbility&&abilityDraft?.selection===activeAbility&&abilityDraft.projection===projection&&projection.scene
    &&(!abilityDraft.itemId||projection.items.some(item=>item.id===abilityDraft.itemId&&item.kind==="token"&&item.card_id===activeAbility.cardId))
    ?abilityDraft:null;
  const geometry=activeAbility?.ability.geometry;
  const areaPreview=geometry&&draft?.origin&&projection.scene
    ?previewGeometry(geometry,projection.scene,draft.origin,draft.direction):null;

  function chooseToken(id:string) {
    if(!activeAbility||geometry?.origin!=="token"||!projection.scene)return;
    const item=projection.items.find(item=>item.id===id&&item.kind==="token"&&item.card_id===activeAbility.cardId);
    if(item&&Number.isFinite(item.x+item.width/2)&&Number.isFinite(item.y+item.height/2))
      setAbilityDraft({selection:activeAbility,projection,origin:{x:item.x+item.width/2,y:item.y+item.height/2},itemId:id,direction:null});
  }
  function validPoint(value:Point) {return Number.isFinite(value.x)&&Number.isFinite(value.y)&&Math.abs(value.x)<=1000000&&Math.abs(value.y)<=1000000;}
  function chooseAbilityPoint(value:Point) {
    if(!activeAbility||!geometry||!projection.scene||!validPoint(value))return;
    setCursor(value);
    if(!draft?.origin) {
      if(geometry.origin==="token") {
        const item=hitTest(buildFrame(projection).items,value);
        if(item)chooseToken(item.id);
      } else setAbilityDraft({selection:activeAbility,projection,origin:value,itemId:null,direction:null});
    } else if(directed(geometry)&&Math.hypot(value.x-draft.origin.x,value.y-draft.origin.y)>1e-7)
      setAbilityDraft({...draft,direction:value});
    else if(geometry.origin==="point"&&!directed(geometry))setAbilityDraft({...draft,origin:value});
  }
  function placeAbility(start:Point,end:Point) {
    if(!activeAbility||geometry?.origin!=="point"||!projection.scene||!validPoint(start)||!validPoint(end)) {
      setAbilityDraft(null);return;
    }
    setAbilityDraft({selection:activeAbility,projection,origin:directed(geometry)?start:end,itemId:null,
      direction:directed(geometry)&&Math.hypot(end.x-start.x,end.y-start.y)>1e-7?end:null});
  }
  function presentAbility() {
    if(!activeAbility||!draft?.origin||!geometry||!areaPreview||(directed(geometry)&&!draft.direction))return;
    onAbilityCommand?.("ability.present",{card_id:activeAbility.cardId,ability_id:activeAbility.ability.id,
      ...(draft.itemId?{origin_item_id:draft.itemId}:{origin:draft.origin}),
      ...(draft.direction?{direction:draft.direction}:{})});
  }

  useEffect(() => {
    let active = true;
    if (!host.current) return;
    void factory(host.current, (message) => {
      if (active) { setError(message); onAssetError?.(message); }
    }).then((instance) => {
      if (!active) { instance.destroy(); return; }
      renderer.current = instance;
      setReady(true);
    }).catch(() => active && setError("Canvas недоступен. Используйте список объектов и поля трансформации."));
    return () => { active = false; renderer.current?.destroy(); renderer.current = null; };
  }, [factory]);

  useEffect(()=>{setToolPoints([]);setHover(null);toolGesture.current=null;},[disabled,projection.scene?.id]);

  useEffect(() => {
    gesture.current = null;
    previewRef.current = null;
    setPreview(null);
    setAbilityDraft(null);abilityGesture.current=null;
  }, [projection, disabled]);

  useEffect(() => {
    setAbilityDraft(null);abilityGesture.current=null;
    // The ID came from an explicit card button. Never infer an origin from cardinality.
    if(activeAbility?.sourceTokenId)chooseToken(activeAbility.sourceTokenId);
  }, [abilitySelection]);

  useEffect(() => {
    if (ready) renderer.current?.render(buildFrame(projection, preview ?? (disabled ? null : remotePreview),areaPreview), viewport.current, assetUrls);
  }, [projection, assetUrls, preview, remotePreview, disabled, revision, ready,abilityDraft,abilitySelection]);

  useEffect(() => {
    const surface = host.current;
    if (!surface) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const bounds = surface.getBoundingClientRect();
      viewport.current.zoomAt({ x: event.clientX - bounds.left, y: event.clientY - bounds.top },
        Math.exp(-event.deltaY * 0.001));
      setRevision((value) => value + 1);
    };
    surface.addEventListener("wheel", wheel, { passive: false });
    return () => surface.removeEventListener("wheel", wheel);
  }, []);

  function point(event: PointerEvent<HTMLDivElement>): Point {
    const bounds = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
  }
  function cancel() { gesture.current = null; previewRef.current = null; setPreview(null); onPreview?.(null);
    setToolPoints([]);setHover(null);toolGesture.current=null;setAbilityDraft(null);abilityGesture.current=null;onAbilityCancel?.(); }
  function finish(points:Point[]) {
    if(!toolAllowed) return;
    if(tool==="ruler") {setToolPoints(points.slice(-2));return;}
    if(tool.startsWith("fog.")) {
      let polygon=points;
      if(tool==="fog.rectangle"&&points.length===2) {
        const [a,b]=points; polygon=[a,{x:b.x,y:a.y},b,{x:a.x,y:b.y}];
      }
      if(polygon.length>=3) onToolCommand?.("fog.reveal",{points:polygon});
    } else if(["line","arrow","label"].includes(tool)) {
      onToolCommand?.("annotation.create",{kind:tool,points,label:tool==="label"?annotationLabel:"",
        visibility:projection.can_manage?annotationVisibility:"everyone"});
    }
    setToolPoints([]);setHover(null);
  }
  function addPoint(point:Point) {
    if(!toolAllowed||tool==="select")return;
    setCursor(point);
    const next=tool==="ruler"&&toolPoints.length===2?[point]:[...toolPoints,point];
    if(next.length>32)return;
    if(tool==="label"||(tool!=="fog.polygon"&&next.length===2))finish(next);
    else setToolPoints(next);
  }
  const rulerPoints=toolPoints.length===1&&hover?[toolPoints[0],hover]:toolPoints;
  const distance=projection.scene&&tool==="ruler"&&rulerPoints.length===2
    ? Math.hypot(rulerPoints[1].x-rulerPoints[0].x,rulerPoints[1].y-rulerPoints[0].y)*projection.scene.unit_size/projection.scene.grid_size:null;

  return (
    <div className="scene-map-area">
      <div ref={host} className="scene-canvas" data-tool={activeAbility ? "ability" : tool} role="region" aria-label="Карта и токены" tabIndex={0}
        onPointerDown={(event) => {
          const start = point(event);
          if(activeAbility&&!event.shiftKey&&event.button!==1) {
            const world=viewport.current.screenToWorld(start);
            if(event.button!==0||event.isPrimary===false||!validPoint(world))return;
            abilityGesture.current={selection:activeAbility,projection,start:world,pointerId:event.pointerId,dragging:false};
            event.currentTarget.setPointerCapture?.(event.pointerId);return;
          }
          if(tool!=="select"&&toolAllowed&&!event.shiftKey&&event.button!==1) {
            if(toolAllowed) {toolGesture.current=viewport.current.screenToWorld(start);event.currentTarget.setPointerCapture?.(event.pointerId);}
            return;
          }
          const hit = disabled || event.button === 1 || event.shiftKey ? null
            : hitTest(buildFrame(projection).items, viewport.current.screenToWorld(start));
          onSelect(hit);
          const item = hit?.is_locked && hit.kind === "map" ? null : hit;
          if (item && (disabled || !item.can_transform || item.is_locked)) return;
          gesture.current = { start, item, original: item
            ? { x: item.x, y: item.y } : { x: viewport.current.x, y: viewport.current.y } };
          event.currentTarget.setPointerCapture?.(event.pointerId);
        }}
        onPointerMove={(event) => {
          const placement=abilityGesture.current;
          if(placement) {
            if(placement.pointerId!==event.pointerId)return;
            if(!activeAbility||placement.selection!==activeAbility||placement.projection!==projection) {
              abilityGesture.current=null;setAbilityDraft(null);return;
            }
            const end=viewport.current.screenToWorld(point(event));
            if(geometry?.origin==="point"&&validPoint(end)&&Math.hypot(end.x-placement.start.x,end.y-placement.start.y)>1) {
              placement.dragging=true;placeAbility(placement.start,end);
            }
            return;
          }
          if(tool!=="select"&&toolAllowed) setHover(viewport.current.screenToWorld(point(event)));
          const current = gesture.current;
          if (!current) return;
          const position = point(event);
          const dx = position.x - current.start.x;
          const dy = position.y - current.start.y;
          if (current.item) {
            const worldStart=viewport.current.screenToWorld(current.start),worldNow=viewport.current.screenToWorld(position);
            const next = { id: current.item.id, x: current.original.x + worldNow.x-worldStart.x,
              y: current.original.y + worldNow.y-worldStart.y };
            previewRef.current = next;
            setPreview(next);
            onPreview?.(next);
          } else {
            viewport.current.x = current.original.x + dx;
            viewport.current.y = current.original.y + dy;
            setRevision((value) => value + 1);
          }
        }}
        onPointerUp={(event) => {
          const placement=abilityGesture.current;
          if(placement) {
            if(placement.pointerId!==event.pointerId)return;
            abilityGesture.current=null;
            if(!activeAbility||placement.selection!==activeAbility||placement.projection!==projection) {setAbilityDraft(null);return;}
            const end=viewport.current.screenToWorld(point(event));
            if(geometry?.origin==="point"&&(placement.dragging||Math.hypot(end.x-placement.start.x,end.y-placement.start.y)>1))
              placeAbility(placement.start,end);
            else chooseAbilityPoint(end);
            return;
          }
          if(toolGesture.current) {
            const start=toolGesture.current,end=viewport.current.screenToWorld(point(event));toolGesture.current=null;
            if(toolAllowed) {
              if(toolPoints.length===0&&!['label','fog.polygon'].includes(tool)&&Math.hypot(end.x-start.x,end.y-start.y)>1)finish([start,end]);
              else addPoint(end);
            }
            return;
          }
          onPreview?.(null);
          const current = gesture.current;
          gesture.current = null;
          const next = previewRef.current;
          if (!disabled && current?.item && next
              && (next.x !== current.original.x || next.y !== current.original.y)) {
            onMove(next.id, { x: next.x, y: next.y });
          } else { previewRef.current = null; setPreview(null); }
        }}
        onPointerCancel={cancel}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault(); event.stopPropagation();
            const hasDraft = Boolean(activeAbility || gesture.current || toolPoints.length || toolGesture.current);
            cancel(); if (!hasDraft) onExitTool?.();
          }
          if(activeAbility&&["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Enter"].includes(event.key)) {
            event.preventDefault();
            if(event.key==="Enter")chooseAbilityPoint(cursor);
            else {const step=(projection.scene?.grid_size??64)/4;
              setCursor(previous=>({x:Math.max(-1000000,Math.min(1000000,previous.x+(event.key==="ArrowLeft"?-step:event.key==="ArrowRight"?step:0))),
                y:Math.max(-1000000,Math.min(1000000,previous.y+(event.key==="ArrowUp"?-step:event.key==="ArrowDown"?step:0)))}));}
            return;
          }
          if(tool!=="select"&&toolAllowed&&["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Enter"].includes(event.key)) {
            event.preventDefault();
            if(event.key==="Enter")addPoint(cursor);
            else {const step=(projection.scene?.grid_size??64)/4;
              setCursor(previous=>({x:previous.x+(event.key==="ArrowLeft"?-step:event.key==="ArrowRight"?step:0),
                y:previous.y+(event.key==="ArrowUp"?-step:event.key==="ArrowDown"?step:0)}));}
            return;
          }
          const delta: Record<string, Point> = { ArrowLeft: { x: 64, y: 0 }, ArrowRight: { x: -64, y: 0 },
            ArrowUp: { x: 0, y: 64 }, ArrowDown: { x: 0, y: -64 } };
          if (delta[event.key]) { event.preventDefault(); viewport.current.pan(delta[event.key].x, delta[event.key].y); }
          if (["+", "=", "-"].includes(event.key)) viewport.current.zoomAt({ x: 320, y: 240 }, event.key === "-" ? 0.8 : 1.25);
          setRevision((value) => value + 1);
        }} ><ToolOverlay projection={projection} viewport={viewport.current} points={toolPoints} hover={hover} tool={tool} cursor={cursor} selectedId={selectedId} preview={preview}/></div>
      <div className="scene-viewport-tools" aria-label="Масштаб карты">
        <button type="button" aria-label="Уменьшить карту" onClick={() => {
          viewport.current.zoomAt({ x: 320, y: 240 }, 0.8); setRevision((value) => value + 1);
        }}>−</button>
        <output>{Math.round(viewport.current.zoom * 100)}%</output>
        <button type="button" aria-label="Увеличить карту" onClick={() => {
          viewport.current.zoomAt({ x: 320, y: 240 }, 1.25); setRevision((value) => value + 1);
        }}>+</button>
        <button type="button" aria-label="Повернуть вид карты" onClick={()=>{viewport.current.rotateAt({x:320,y:240},Math.PI/4);setRevision(value=>value+1);}}>Повернуть вид</button>
        <button type="button" onClick={() => { viewport.current = new Viewport(); setRevision((value) => value + 1); }}>Сбросить вид</button>
      </div>
      <div className="map-mode-controls" hidden={tool === "select"}><strong>{tool === "select" ? "" : ({ruler:"Линейка",line:"Линия",arrow:"Стрелка",label:"Метка","fog.rectangle":"Открыть прямоугольник","fog.polygon":"Открыть многоугольник"})[tool]}</strong><span>{toolPoints.length === 0 ? "Выберите первую точку" : tool === "fog.polygon" ? `Точек: ${toolPoints.length}` : tool === "ruler" && toolPoints.length === 2 ? "Измерение готово" : "Выберите вторую точку"}</span>
      {tool==="fog.polygon"?<button type="button" disabled={!toolAllowed||toolPoints.length<3} onClick={()=>finish(toolPoints)}>Завершить область</button>:null}
      {tool!=="select"?<button type="button" onClick={cancel}>Очистить измерение / черновик</button>:null}
      {distance!==null?<output aria-label="Расстояние">{distance.toFixed(2)} {projection.scene?.unit_label}</output>:null}
      </div>
      <AbilityControls selection={activeAbility} origin={draft?.origin??null} direction={draft?.direction??null}
        projection={projection} onPoint={chooseAbilityPoint} onToken={chooseToken} onConfirm={presentAbility}
        onCancel={cancel} onClear={id=>{if(!disabled)onAbilityCommand?.("ability.clear",{presentation_id:id});}} disabled={disabled}/>
      {error ? <p className="scene-error" role="alert">{error}</p> : null}
      <p className="scene-help">Колесо — масштаб · пустое поле или Shift — панорама · стрелки и +/− доступны с клавиатуры</p>
    </div>
  );
}
