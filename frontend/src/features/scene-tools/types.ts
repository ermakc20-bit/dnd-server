import type { Point } from "../../renderer/viewport";
export type TableTool = "select" | "ruler" | "line" | "arrow" | "label" | "fog.rectangle" | "fog.polygon";
export interface Fog { enabled:boolean; reveals:{points:Point[]}[] }
export interface Annotation { id:string; kind:"line"|"arrow"|"label"; points:Point[]; label:string;
  visibility:"everyone"|"gm_only"; owner_participant_id:string; can_edit:boolean }
export interface ToolDraft { tool:TableTool; points:Point[] }
export type Execute = (type:string,payload:Record<string,unknown>,onAcknowledged?:()=>void)=>Promise<boolean>;
