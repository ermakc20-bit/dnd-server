import type { Point } from "../../renderer/viewport";
import type { Scene } from "../scene/types";
import type { Geometry, PresentedGeometry } from "./types";

export const directed=(geometry:Geometry)=>["cone","line","cube"].includes(geometry.shape);
export function previewGeometry(geometry:Geometry,scene:Scene,origin:Point,direction:Point|null):PresentedGeometry|null {
  if(geometry.units!==scene.unit_label)return null;
  const length=geometry.length??0,radius=geometry.radius??0,width=geometry.width??0;
  if(["circle","radius"].includes(geometry.shape)?radius<=0:length<=0)return null;
  if(geometry.shape==="line"&&width<=0)return null;
  if(geometry.shape==="cone"&&!(geometry.angle&&geometry.angle>0))return null;
  const scale=scene.grid_size/scene.unit_size;
  return {schema_version:1,shape:geometry.shape,origin,
    rotation:direction?Math.atan2(direction.y-origin.y,direction.x-origin.x):0,
    radius:radius*scale,length:length*scale,width:width*scale,angle:geometry.angle??360,
    color:geometry.color??"#c5a65c"};
}

// Shared visible overlay outline in world pixels. Server hit tests use the exact analytic shape.
export function outline(geometry:PresentedGeometry):Point[] {
  const local:Point[]=[];
  if(["circle","radius","cone"].includes(geometry.shape)) {
    const cone=geometry.shape==="cone",radius=cone?geometry.length:geometry.radius;
    const sweep=cone?geometry.angle*Math.PI/180:Math.PI*2;
    const start=cone?-sweep/2:0;
    if(cone&&geometry.angle<360)local.push({x:0,y:0});
    const steps=Math.max(16,Math.ceil(sweep/(Math.PI/32)));
    for(let i=0;i<=steps;i++){const angle=start+sweep*i/steps;local.push({x:Math.cos(angle)*radius,y:Math.sin(angle)*radius});}
  } else {
    const half=geometry.shape==="cube"?geometry.length/2:geometry.width/2;
    const left=geometry.shape==="cube"?-half:0,right=geometry.shape==="cube"?half:geometry.length;
    local.push({x:left,y:-half},{x:right,y:-half},{x:right,y:half},{x:left,y:half});
  }
  const c=Math.cos(geometry.rotation),s=Math.sin(geometry.rotation);
  return local.map(point=>({x:geometry.origin.x+point.x*c-point.y*s,y:geometry.origin.y+point.x*s+point.y*c}));
}
