export interface RoomSummary {
  id: string;
  campaign_id: string;
  name: string;
  is_locked: boolean;
  pin_enabled: boolean;
  created_at: string;
  can_manage: boolean;
}

export interface CampaignSummary {
  id: string;
  owner_user_id: string;
  name: string;
  system_id: string;
  status: "draft" | "active" | "archived";
  created_at: string;
  rooms: RoomSummary[];
}

export interface ParticipantSummary {
  id: string;
  campaign_id: string;
  room_id: string;
  role: "gm" | "player";
  display_name: string;
  user_id: string | null;
  guest_session_id: string | null;
  joined_at: string;
  removed_at: string | null;
}

export interface GuestSession { participant: ParticipantSummary; room: RoomSummary }
export interface InviteSummary { room_id: string; token: string; expires_at: string }
export interface ParticipantStatus {
  id: string; display_name: string; role: "gm" | "player";
  connection_status: "connected" | "disconnected" | "unknown";
  assigned_tokens: { id: string; name: string; scene_id: string; scene_name: string }[];
}
export interface RoomSecurityEvent {
  id: number; participant_id: string; display_name: string;
  type: "participant.joined" | "connection.opened" | "connection.closed";
  occurred_at: string; reason: "guest_join" | "registered_join" | "authorized_socket" |
    "socket_closed_actor_connected" | "socket_closed_actor_disconnected" | "socket_closed_actor_unknown";
}
export interface RoomSecurityPage { events: RoomSecurityEvent[]; next_before_id: number | null }

export class CampaignApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  let message = "Сервер временно недоступен";
  let code: string | undefined;
  try {
    const payload = (await response.json()) as {
      detail?: { message?: string; code?: string } | string;
    };
    if (typeof payload.detail === "string") message = payload.detail;
    else if (payload.detail) {
      message = payload.detail.message ?? message;
      code = payload.detail.code;
    }
  } catch {
    // Keep the safe generic text for transport and non-JSON gateway errors.
  }
  throw new CampaignApiError(message, response.status, code);
}

export interface CampaignApi {
  listCampaigns(accessToken: string): Promise<CampaignSummary[]>;
  createCampaign(accessToken: string, name: string, systemId: string): Promise<CampaignSummary>;
  issueInvite(accessToken: string, roomId: string): Promise<InviteSummary>;
  rotateInvite(accessToken: string, roomId: string): Promise<InviteSummary>;
  revokeInvites(accessToken: string, roomId: string): Promise<void>;
  updateRoomAccess(
    accessToken: string,
    roomId: string,
    change: { is_locked?: boolean; pin?: string; remove_pin?: boolean },
  ): Promise<RoomSummary>;
  listParticipants(accessToken: string, roomId: string): Promise<ParticipantSummary[]>;
  listParticipantStatus?(accessToken: string, roomId: string): Promise<ParticipantStatus[]>;
  securityEvents?(accessToken: string, roomId: string, beforeId?: number): Promise<RoomSecurityPage>;
  removeParticipant(accessToken: string, roomId: string, participantId: string): Promise<void>;
}

export interface GuestApi {
  restoreGuest(inviteToken: string, accessToken?: string): Promise<GuestSession>;
  joinGuest(inviteToken: string, displayName: string, pin?: string): Promise<GuestSession>;
  joinRegistered(
    accessToken: string,
    inviteToken: string,
    displayName: string,
    pin?: string,
  ): Promise<GuestSession>;
}

export const campaignApi: CampaignApi & GuestApi = {
  async listParticipantStatus(accessToken, roomId) {
    const result = await parseResponse<{ participants: ParticipantStatus[] }>(
      await fetch(`/api/v1/rooms/${roomId}/participants/status`, { credentials: "same-origin", headers: authHeaders(accessToken) }));
    if (!Array.isArray(result.participants)) throw new Error("Статус участников недоступен");
    return result.participants;
  },
  async securityEvents(accessToken, roomId, beforeId) {
    const query = new URLSearchParams({ limit: "50" });
    if (beforeId !== undefined) query.set("before_id", String(beforeId));
    return parseResponse<RoomSecurityPage>(await fetch(`/api/v1/rooms/${roomId}/security-events?${query}`,
      { credentials: "same-origin", headers: authHeaders(accessToken) }));
  },
  async listCampaigns(accessToken) {
    return parseResponse<CampaignSummary[]>(
      await fetch("/api/v1/campaigns", { headers: authHeaders(accessToken) }),
    );
  },
  async createCampaign(accessToken, name, systemId) {
    return roomMutation<CampaignSummary>(accessToken, "/campaigns", "POST", {
      name, system_id: systemId,
    });
  },
  async issueInvite(accessToken, roomId) {
    return roomMutation<InviteSummary>(accessToken, `/rooms/${roomId}/invites`, "POST", {
      expires_in_minutes: 1440,
    });
  },
  async rotateInvite(accessToken, roomId) {
    return roomMutation<InviteSummary>(
      accessToken, `/rooms/${roomId}/invites/rotate`, "POST", { expires_in_minutes: 1440 },
    );
  },
  async revokeInvites(accessToken, roomId) {
    await roomMutation<void>(accessToken, `/rooms/${roomId}/invites`, "DELETE");
  },
  async updateRoomAccess(accessToken, roomId, change) {
    return roomMutation<RoomSummary>(accessToken, `/rooms/${roomId}/access`, "PATCH", change);
  },
  async listParticipants(accessToken, roomId) {
    const result = await parseResponse<{ participants: ParticipantSummary[] }>(
      await fetch(`/api/v1/rooms/${roomId}/participants`, {
        credentials: "same-origin", headers: authHeaders(accessToken),
      }),
    );
    return result.participants;
  },
  async removeParticipant(accessToken, roomId, participantId) {
    await roomMutation<void>(accessToken, `/rooms/${roomId}/participants/${participantId}`, "DELETE");
  },
  async restoreGuest(inviteToken, accessToken) {
    return parseResponse<GuestSession>(
      await fetch(`/api/v1/join/${encodeURIComponent(inviteToken)}/session`, {
        credentials: "same-origin",
        headers: accessToken ? authHeaders(accessToken) : undefined,
      }),
    );
  },
  async joinGuest(inviteToken, displayName, pin) {
    return joinMutation(`/join/${encodeURIComponent(inviteToken)}`, displayName, pin);
  },
  async joinRegistered(accessToken, inviteToken, displayName, pin) {
    return joinMutation(
      `/join/${encodeURIComponent(inviteToken)}/registered`, displayName, pin, accessToken,
    );
  },
};

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

async function roomMutation<T>(
  accessToken: string,
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body?: object,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    credentials: "same-origin",
    headers: { ...authHeaders(accessToken), ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 204) return undefined as T;
  return parseResponse<T>(response);
}

async function joinMutation(
  path: string,
  displayName: string,
  pin?: string,
  accessToken?: string,
): Promise<GuestSession> {
  return parseResponse<GuestSession>(
    await fetch(`/api/v1${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { ...(accessToken ? authHeaders(accessToken) : {}), "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName, pin: pin || null }),
    }),
  );
}
