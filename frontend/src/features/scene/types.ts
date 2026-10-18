import type { Annotation, Fog } from "../scene-tools/types";
import type { AbilityPresentation } from "../ability-geometry/types";
export interface Scene {
  id: string; name: string; width: number; height: number; grid_size: number;
  grid_enabled: boolean; snap_enabled: boolean; unit_size: number; unit_label: string;
}

export interface SceneItem {
  id: string; kind: "map" | "token"; name: string; asset_id: string | null;
  x: number; y: number; width: number; height: number; rotation: number; z_index: number;
  visibility: "everyone" | "gm_only" | "owner_only"; is_locked: boolean;
  owner_participant_id: string | null; can_transform: boolean;
  card_id?: string | null;
}

export interface SceneProjection {
  room_id: string; aggregate_version: number; event_cursor: number; actor_session_id: string;
  can_manage: boolean; scenes: { id: string; name: string }[]; scene: Scene | null;
  items: SceneItem[]; fog?:Fog; annotations?:Annotation[];
  ability_presentations?:AbilityPresentation[];
}

export interface SceneCommand {
  command_id: string; room_id: string; actor_session_id: string;
  expected_aggregate_version: number; type: string; payload: Record<string, unknown>;
  client_sent_at: string;
}

export interface CommandResult {
  command_id: string; status: "accepted" | "rejected" | "duplicate";
  aggregate_version: number | null; event_cursor: number | null;
  error_code: string | null; message: string | null;
}

export interface AssetMetadata {
  id: string; name: string; content_type: string; byte_size: number;
  width: number | null; height: number | null; status: "pending" | "ready"; upload_url: string;
}

export interface SceneApi {
  projection(roomId: string, accessToken?: string): Promise<SceneProjection>;
  command(command: SceneCommand, accessToken?: string): Promise<CommandResult>;
  prepareUpload(roomId: string, file: File, accessToken?: string): Promise<AssetMetadata>;
  upload(asset: AssetMetadata, file: File, accessToken?: string): Promise<AssetMetadata>;
  download(roomId: string, assetId: string, accessToken?: string): Promise<{ url: string; expires_in: number }>;
}
