import { afterEach, describe, expect, it, vi } from "vitest";

import { campaignApi } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("campaignApi room administration", () => {
  it("sends the exact HTTP payload for every GM mutation", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ id: "campaign-1" }))
      .mockResolvedValueOnce(jsonResponse({ room_id: "room-1", token: "first" }))
      .mockResolvedValueOnce(jsonResponse({ room_id: "room-1", token: "second" }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse({ id: "room-1", pin_enabled: true }))
      .mockResolvedValueOnce(jsonResponse({ id: "room-1", pin_enabled: false }))
      .mockResolvedValueOnce(jsonResponse({ id: "room-1", is_locked: true }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await campaignApi.createCampaign("gm-token", "Баровия", "neutral");
    await campaignApi.issueInvite("gm-token", "room-1");
    await campaignApi.rotateInvite("gm-token", "room-1");
    await campaignApi.revokeInvites("gm-token", "room-1");
    await campaignApi.updateRoomAccess("gm-token", "room-1", { pin: "4821" });
    await campaignApi.updateRoomAccess("gm-token", "room-1", { remove_pin: true });
    await campaignApi.updateRoomAccess("gm-token", "room-1", { is_locked: true });
    await campaignApi.removeParticipant("gm-token", "room-1", "participant-1");

    expect(fetchMock.mock.calls).toEqual([
      mutation("/api/v1/campaigns", "POST", { name: "Баровия", system_id: "neutral" }),
      mutation("/api/v1/rooms/room-1/invites", "POST", { expires_in_minutes: 1440 }),
      mutation("/api/v1/rooms/room-1/invites/rotate", "POST", { expires_in_minutes: 1440 }),
      mutation("/api/v1/rooms/room-1/invites", "DELETE"),
      mutation("/api/v1/rooms/room-1/access", "PATCH", { pin: "4821" }),
      mutation("/api/v1/rooms/room-1/access", "PATCH", { remove_pin: true }),
      mutation("/api/v1/rooms/room-1/access", "PATCH", { is_locked: true }),
      mutation("/api/v1/rooms/room-1/participants/participant-1", "DELETE"),
    ]);
  });
});

function mutation(path: string, method: string, body?: object) {
  return [path, {
    method,
    credentials: "same-origin",
    headers: {
      Authorization: "Bearer gm-token",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  }];
}

function jsonResponse(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
