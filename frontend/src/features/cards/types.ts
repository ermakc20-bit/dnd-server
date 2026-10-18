import type { Geometry } from "../ability-geometry/types";
export type Visibility = "everyone" | "gm_only" | "owner_only";
export interface CardField { key: string; label: string; value: string | number | boolean | null;
  value_type: "text" | "number" | "boolean"; visibility: Visibility; order: number }
export interface Resource { key: string; label: string; current: number; max: number | null;
  color: string | null; visibility: Visibility }
export interface Skill { key: string; name: string; bonus: number | null; proficient: boolean;
  description: string | null; visibility: Visibility }
export interface InventoryItem { id: string; name: string; quantity: number | null;
  description: string | null; icon: string | null; visibility: Visibility }
export interface Ability { id: string; schema_version: 1; name: string; description: string;
  action_type: string | null; uses: Resource | null; geometry: Geometry | null;
  automation: null; visibility: Visibility }
export interface CardData { schema_version: 1; system_id: string; system_version: number;
  kind: "player_character" | "npc" | "mob" | "object"; name: string; subtitle: string | null;
  image_asset_id: string | null; external_key: string | null; owner_participant_id: string | null;
  visibility: Visibility; allow_player_export: boolean; fields: CardField[]; resources: Resource[];
  skills: Skill[]; inventory: InventoryItem[]; abilities: Ability[]; notes: string | null;
  notes_visibility: Visibility }
export interface Card extends CardData { id: string; campaign_id: string; room_id: string; version: number;
  created_at: string; updated_at: string; can_edit_structure: boolean; can_edit_current: boolean; can_export: boolean }
export interface CardPage { cards: Card[]; offset: number; limit: number; has_more: boolean }
export interface Package { system_id: string; version: number; schema_version: 1;
  defaults: Pick<CardData, "fields" | "resources" | "skills"> }
export const kinds = { player_character: "Персонаж игрока", npc: "NPC", mob: "Моб", object: "Объект" };
export function blankCard(): CardData { return { schema_version: 1, system_id: "neutral", system_version: 1,
  kind: "player_character", name: "", subtitle: null, image_asset_id: null, external_key: null,
  owner_participant_id: null, visibility: "everyone", allow_player_export: false,
  fields: [], resources: [], skills: [], inventory: [], abilities: [], notes: null, notes_visibility: "gm_only" }; }
export function editable(card: Card): CardData {
  const { id, campaign_id, room_id, version, created_at, updated_at, can_edit_structure, can_edit_current, can_export, ...data } = card;
  void [id, campaign_id, room_id, version, created_at, updated_at, can_edit_structure, can_edit_current, can_export];
  return structuredClone(data);
}
