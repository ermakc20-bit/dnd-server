import { useId } from "react";
import type { ItemPreview, Point, Viewport } from "../../renderer/viewport";
import type { SceneProjection } from "../scene/types";
import type { TableTool } from "./types";

export function ToolOverlay({projection,viewport,points,hover,tool,cursor,selectedId,preview}: {
  selectedId?: string | null; preview?: ItemPreview | null;
  projection:SceneProjection;viewport:Viewport;points:Point[];hover:Point|null;tool:TableTool;cursor:Point;
}) {
  const id=useId().replace(/:/g,"");
  const scene=projection.scene;
  const selected=projection.items.find(item => item.id === selectedId);
  const selectedPosition=selected && preview?.id === selected.id ? preview : selected;
  const draft=hover&&points.length===1?[points[0],hover]:points;
  const transform=`translate(${viewport.x} ${viewport.y}) rotate(${viewport.rotation*180/Math.PI}) scale(${viewport.zoom})`;
  return <svg className="table-overlay" aria-hidden="true">
    <defs><marker id={`arrow-${id}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#f1c875"/></marker></defs>
    <g transform={transform}>
      {scene&&projection.fog?.enabled?<><mask id={`fog-${id}`} maskUnits="userSpaceOnUse" x="0" y="0" width={scene.width} height={scene.height}>
        <rect x="0" y="0" width={scene.width} height={scene.height} fill="white"/>
        {projection.fog.reveals.map((reveal,index)=><polygon key={index} points={reveal.points.map(p=>`${p.x},${p.y}`).join(" ")} fill="black"/>)}
      </mask><rect x="0" y="0" width={scene.width} height={scene.height} fill="#050a11" opacity={projection.can_manage?0.45:1} mask={`url(#fog-${id})`}/></>:null}
      {projection.annotations?.map(mark=>mark.kind==="label"?<text key={mark.id} x={mark.points[0].x} y={mark.points[0].y}
        fill="#f1c875" stroke="#050a11" strokeWidth={0.7} paintOrder="stroke" fontSize={18/viewport.zoom}>{mark.label}</text>:
        <line key={mark.id} x1={mark.points[0].x} y1={mark.points[0].y} x2={mark.points[1].x} y2={mark.points[1].y}
          stroke="#f1c875" strokeWidth={3/viewport.zoom} markerEnd={mark.kind==="arrow"?`url(#arrow-${id})`:undefined}
          opacity={mark.visibility==="gm_only"?0.65:1}/>)}
      {selected && selectedPosition ? <g transform={`translate(${selectedPosition.x + selected.width / 2} ${selectedPosition.y + selected.height / 2}) rotate(${selected.rotation})`}>
        <rect x={-selected.width / 2 - 3 / viewport.zoom} y={-selected.height / 2 - 3 / viewport.zoom}
          width={selected.width + 6 / viewport.zoom} height={selected.height + 6 / viewport.zoom} rx={3 / viewport.zoom}
          fill="none" stroke="var(--accent)" strokeWidth={2 / viewport.zoom}/>
      </g> : null}
      {draft.length>=2?<polyline points={draft.map(p=>`${p.x},${p.y}`).join(" ")} stroke="#89d7eb" strokeWidth={2/viewport.zoom}
        fill={tool.startsWith("fog.")?"#89d7eb22":"none"} strokeDasharray={`${6/viewport.zoom}`}/>:null}
      {tool==="fog.rectangle"&&draft.length>=2?<rect x={Math.min(draft[0].x,draft[1].x)} y={Math.min(draft[0].y,draft[1].y)}
        width={Math.abs(draft[1].x-draft[0].x)} height={Math.abs(draft[1].y-draft[0].y)} fill="#89d7eb22" stroke="#89d7eb" strokeWidth={2/viewport.zoom}/>:null}
      {tool!=="select"?<g stroke="#89d7eb" strokeWidth={1/viewport.zoom}>
        <path d={`M${cursor.x-8/viewport.zoom},${cursor.y}h${16/viewport.zoom} M${cursor.x},${cursor.y-8/viewport.zoom}v${16/viewport.zoom}`}/>
        {points.map((p,index)=><circle key={index} cx={p.x} cy={p.y} r={4/viewport.zoom} fill="#89d7eb"/>)}</g>:null}
    </g>
  </svg>;
}
