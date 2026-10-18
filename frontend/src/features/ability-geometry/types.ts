import type { Point } from "../../renderer/viewport";
import type { Ability } from "../cards/types";

export interface Geometry {
  shape:"circle"|"radius"|"cone"|"line"|"cube";origin:"token"|"point";
  range?:number|null;radius?:number|null;length?:number|null;width?:number|null;angle?:number|null;
  units:string;color?:string|null;
}
export interface PresentedGeometry {
  schema_version:1;shape:Geometry["shape"];origin:Point;rotation:number;
  radius:number;length:number;width:number;angle:number;color:string;
}
export interface AbilityPresentation {
  id:string;geometry:PresentedGeometry;created_at:string;can_clear:boolean;affected_item_ids:string[];
}
export interface AbilitySelection {cardId:string;ability:Ability;sourceTokenId?:string}
