import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CampaignHome, GuestJoin } from "./CampaignExperience";
import { CampaignApiError, type CampaignApi, type GuestApi, type GuestSession, type RoomSummary } from "./api";

describe("scene integration callbacks", () => {
  const room: RoomSummary = { id: "room-open", campaign_id: "campaign-open", name: "Открываем стол",
    is_locked: false, pin_enabled: false, can_manage: false, created_at: "2026-10-11T00:00:00Z" };
  const session: GuestSession = { room, participant: { id: "guest-open", campaign_id: room.campaign_id,
    room_id: room.id, role: "player", display_name: "Гость", user_id: null, guest_session_id: "session-open",
    joined_at: "2026-10-11T00:00:00Z", removed_at: null } };

  it("passes the selected authorized room without deriving a new role", async () => {
    const onOpenRoom = vi.fn();
    const api = { listCampaigns: vi.fn().mockResolvedValue([{ id: room.campaign_id,
      owner_user_id: "owner", name: "Кампания", system_id: "neutral", status: "active",
      created_at: room.created_at, rooms: [room] }]) } as unknown as CampaignApi;
    render(<CampaignHome accessToken="account" api={api} onOpenRoom={onOpenRoom} />);
    fireEvent.click(await screen.findByRole("button", { name: "Открыть стол Открываем стол" }));
    expect(onOpenRoom).toHaveBeenCalledWith(room);
  });

  it("passes a restored guest session to the scene without changing the join flow", async () => {
    const onSession = vi.fn();
    const api = { restoreGuest: vi.fn().mockResolvedValue(session), joinGuest: vi.fn(), joinRegistered: vi.fn() };
    render(<GuestJoin inviteToken="local-invite" api={api} onSession={onSession} />);
    await waitFor(() => expect(onSession).toHaveBeenCalledWith(session));
    expect(api.restoreGuest).toHaveBeenCalledWith("local-invite", undefined);
  });
});

describe("CampaignHome", () => {
  it("keeps first-run input after a quota error and opens the created authorized room on retry", async () => {
    const room = { id: "new-room", campaign_id: "new-campaign", name: "Первый стол", is_locked: false,
      pin_enabled: false, can_manage: true, created_at: "2026-10-14T00:00:00Z" };
    const api = { listCampaigns: vi.fn().mockResolvedValue([]), createCampaign: vi.fn()
      .mockRejectedValueOnce(new CampaignApiError("Достигнут лимит кампаний. Попробуйте позже.", 409, "quota_exceeded"))
      .mockResolvedValue({ id: room.campaign_id, name: "Моя кампания", rooms: [room], status: "draft", system_id: "neutral" }) };
    const onOpenRoom = vi.fn();
    render(<CampaignHome accessToken="account" api={api as unknown as CampaignApi} onOpenRoom={onOpenRoom} />);
    fireEvent.click(await screen.findByRole("button", { name: "Создать кампанию" }));
    fireEvent.change(screen.getByLabelText("Название кампании"), { target: { value: "Моя кампания" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить кампанию" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Достигнут лимит кампаний");
    expect(screen.getByLabelText("Название кампании")).toHaveValue("Моя кампания");
    expect(onOpenRoom).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить кампанию" }));
    await waitFor(() => expect(onOpenRoom).toHaveBeenCalledWith(room));
  });
  it("offers campaign ZIP recovery before a first campaign exists", async () => {
    const api = { listCampaigns: vi.fn().mockResolvedValue([]), createCampaign: vi.fn() };
    render(<CampaignHome accessToken="registered-token" api={api as unknown as CampaignApi} />);
    await screen.findByRole("heading", { name: "Создайте первый стол" });
    expect(screen.getByRole("button", { name: "Импортировать кампанию" })).toBeInTheDocument();
  });
  it("offers the Russian first-run campaign action when the list is empty", async () => {
    const api = {
      listCampaigns: vi.fn().mockResolvedValue([]),
      createCampaign: vi.fn(),
    };

    render(<CampaignHome accessToken="registered-token" api={api as unknown as CampaignApi} />);

    expect(await screen.findByRole("heading", { name: "Создайте первый стол" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Создать кампанию" })).toBeInTheDocument();
  });

  it("runs every GM mutation with exact arguments and renders its result", async () => {
    const room = {
      id: "room-1", campaign_id: "campaign-1", name: "Основной стол",
      is_locked: false, pin_enabled: false, created_at: "2026-09-03T00:00:00Z",
      can_manage: true,
    };
    const campaign = {
      id: "campaign-1", owner_user_id: "gm-1", name: "Баровия", system_id: "neutral",
      status: "draft" as const, created_at: "2026-09-03T00:00:00Z",
      rooms: [room],
    };
    const player = {
      id: "player-1", campaign_id: campaign.id, room_id: room.id, role: "player" as const,
      display_name: "Ирина", user_id: null, guest_session_id: "guest-1",
      joined_at: "2026-09-03T00:00:00Z", removed_at: null,
    };
    let roomState = room;
    let completeAccessUpdate!: (updatedRoom: RoomSummary) => void;
    const api = {
      listCampaigns: vi.fn().mockResolvedValue([campaign]),
      issueInvite: vi.fn().mockResolvedValue({ room_id: room.id, token: "first", expires_at: "x" }),
      rotateInvite: vi.fn().mockResolvedValue({ room_id: room.id, token: "second", expires_at: "x" }),
      revokeInvites: vi.fn().mockResolvedValue(undefined),
      updateRoomAccess: vi.fn().mockImplementation((_token, _room, change) => {
        roomState = {
          ...roomState,
          is_locked: change.is_locked ?? roomState.is_locked,
          pin_enabled: change.remove_pin ? false : change.pin ? true : roomState.pin_enabled,
        };
        return new Promise<RoomSummary>((resolve) => { completeAccessUpdate = resolve; });
      }),
      listParticipants: vi.fn().mockResolvedValueOnce([player]).mockResolvedValueOnce([]),
      removeParticipant: vi.fn().mockResolvedValue(undefined),
    } as unknown as CampaignApi;
    render(<CampaignHome accessToken="gm-token" api={api} />);

    await screen.findByRole("region", { name: "Управление комнатой Основной стол" });
    expect(screen.getByRole("status")).toHaveTextContent("Комната открыта · PIN выключен");

    fireEvent.click(screen.getByRole("button", { name: "Выпустить приглашение" }));
    await screen.findByText(/\/join\/first$/);
    expect(api.issueInvite).toHaveBeenCalledWith("gm-token", room.id);

    fireEvent.click(screen.getByRole("button", { name: "Перевыпустить" }));
    await screen.findByText(/\/join\/second$/);
    expect(api.rotateInvite).toHaveBeenCalledWith("gm-token", room.id);

    fireEvent.click(screen.getByRole("button", { name: "Отозвать" }));
    await waitFor(() => expect(screen.queryByText(/\/join\/second$/)).not.toBeInTheDocument());
    expect(api.revokeInvites).toHaveBeenCalledWith("gm-token", room.id);

    fireEvent.change(screen.getByLabelText("PIN комнаты"), { target: { value: "4821" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить PIN" }));
    await waitFor(() => expect(api.updateRoomAccess).toHaveBeenCalledWith(
      "gm-token", room.id, { pin: "4821" },
    ));
    expect(screen.getByRole("status")).toHaveTextContent("Комната открыта · PIN выключен");
    completeAccessUpdate(roomState);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("PIN включён"));

    fireEvent.click(screen.getByRole("button", { name: "Убрать PIN" }));
    await waitFor(() => expect(api.updateRoomAccess).toHaveBeenCalledWith(
      "gm-token", room.id, { remove_pin: true },
    ));
    expect(screen.getByRole("status")).toHaveTextContent("Комната открыта · PIN включён");
    completeAccessUpdate(roomState);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("PIN выключен"));

    fireEvent.click(screen.getByRole("button", { name: "Закрыть комнату" }));
    await waitFor(() => expect(api.updateRoomAccess).toHaveBeenCalledWith(
      "gm-token", room.id, { is_locked: true },
    ));
    expect(screen.getByRole("status")).toHaveTextContent("Комната открыта · PIN выключен");
    completeAccessUpdate(roomState);
    expect(await screen.findByRole("button", { name: "Открыть комнату" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Комната закрыта"));

    fireEvent.click(screen.getByRole("button", { name: "Открыть комнату" }));
    await waitFor(() => expect(api.updateRoomAccess).toHaveBeenCalledWith(
      "gm-token", room.id, { is_locked: false },
    ));
    expect(screen.getByRole("status")).toHaveTextContent("Комната закрыта · PIN выключен");
    completeAccessUpdate(roomState);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Комната открыта · PIN выключен"));
    expect(screen.getByRole("button", { name: "Закрыть комнату" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Показать участников" }));
    await screen.findByText(/Ирина/);
    expect(api.listParticipants).toHaveBeenCalledWith("gm-token", room.id);
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    await waitFor(() => expect(api.removeParticipant).toHaveBeenCalledWith(
      "gm-token", room.id, player.id,
    ));
    await waitFor(() => expect(screen.queryByText(/Ирина/)).not.toBeInTheDocument());
  });

  it("renders administration only for rooms with a server-projected capability", async () => {
    const api = {
      listCampaigns: vi.fn().mockResolvedValue([{
        id: "campaign-1", owner_user_id: "gm-1", name: "Баровия", system_id: "neutral",
        status: "active", created_at: "2026-09-03T00:00:00Z",
        rooms: [
          { id: "room-1", campaign_id: "campaign-1", name: "Разрешённый стол",
            is_locked: false, pin_enabled: false, created_at: "2026-09-03T00:00:00Z",
            can_manage: true },
          { id: "room-2", campaign_id: "campaign-1", name: "Чужой стол",
            is_locked: false, pin_enabled: false, created_at: "2026-09-03T00:00:00Z",
            can_manage: false },
        ],
      }]),
    } as unknown as CampaignApi;
    render(<CampaignHome accessToken="room-gm-token" api={api} />);
    await screen.findByText("Баровия");
    expect(screen.getByRole("region", {
      name: "Управление комнатой Разрешённый стол",
    })).toBeInTheDocument();
    expect(screen.queryByRole("region", {
      name: "Управление комнатой Чужой стол",
    })).not.toBeInTheDocument();
  });

  it("creates a draft campaign through the server API", async () => {
    const campaign = {
      id: "campaign-1",
      owner_user_id: "owner-1",
      name: "Туманы Баровии",
      system_id: "neutral",
      status: "draft" as const,
      created_at: "2026-09-03T00:00:00Z",
      rooms: [],
    };
    const api = {
      listCampaigns: vi.fn().mockResolvedValue([]),
      createCampaign: vi.fn().mockResolvedValue(campaign),
    };
    render(<CampaignHome accessToken="registered-token" api={api as unknown as CampaignApi} />);
    await screen.findByRole("heading", { name: "Создайте первый стол" });
    fireEvent.click(screen.getByRole("button", { name: "Создать кампанию" }));

    fireEvent.change(screen.getByLabelText("Название кампании"), {
      target: { value: "Туманы Баровии" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить кампанию" }));

    await waitFor(() => {
      expect(api.createCampaign).toHaveBeenCalledWith(
        "registered-token",
        "Туманы Баровии",
        "neutral",
      );
    });
    expect(await screen.findByText("Туманы Баровии")).toBeInTheDocument();
  });

  it("does not create two campaigns while the first save is pending", async () => {
    const api = {
      listCampaigns: vi.fn().mockResolvedValue([]),
      createCampaign: vi.fn().mockReturnValue(new Promise(() => {})),
    };
    render(<CampaignHome accessToken="registered-token" api={api as unknown as CampaignApi} />);
    fireEvent.click(await screen.findByRole("button", { name: "Создать кампанию" }));
    fireEvent.change(screen.getByLabelText("Название кампании"), {
      target: { value: "Туманы Баровии" },
    });
    const save = screen.getByRole("button", { name: "Сохранить кампанию" });
    fireEvent.click(save);
    fireEvent.click(save);

    expect(api.createCampaign).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Сохраняем…" })).toBeDisabled();
  });
});

describe("GuestJoin", () => {
  it("does not reveal a campaign when an invite is invalid", async () => {
    const api = {
      restoreGuest: vi.fn().mockRejectedValue(new CampaignApiError("Сессия отсутствует", 401)),
      joinGuest: vi.fn().mockRejectedValue(new Error("Приглашение недействительно или истекло")),
      joinRegistered: vi.fn(),
    };
    render(<GuestJoin inviteToken="expired-token" api={api as GuestApi} />);
    await screen.findByRole("heading", { name: "Вход за игровой стол" });

    fireEvent.change(screen.getByLabelText("Ваше имя"), { target: { value: "Ирина" } });
    fireEvent.click(screen.getByRole("button", { name: "Войти в комнату" }));

    expect(
      await screen.findByText("Приглашение недействительно или истекло"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/кампания/i)).not.toBeInTheDocument();
  });

  it("uses the preserved invite for registered join and restores it after refresh", async () => {
    const session = {
      participant: {
        id: "p1", campaign_id: "c1", room_id: "r1", role: "player" as const,
        display_name: "Ирина", user_id: "u1", guest_session_id: null,
        joined_at: "2026-09-03T00:00:00Z", removed_at: null,
      },
      room: { id: "r1", campaign_id: "c1", name: "Основной стол", is_locked: false,
        pin_enabled: false, created_at: "2026-09-03T00:00:00Z", can_manage: false },
    };
    const api = {
      restoreGuest: vi.fn().mockRejectedValueOnce(new CampaignApiError("Нет участия", 403))
        .mockResolvedValueOnce(session),
      joinGuest: vi.fn(),
      joinRegistered: vi.fn().mockResolvedValue(session),
    } as GuestApi;
    const first = render(<GuestJoin inviteToken="kept-invite" accessToken="account-token" api={api} />);
    await screen.findByRole("heading", { name: "Вход за игровой стол" });
    fireEvent.change(screen.getByLabelText("Ваше имя"), { target: { value: "Ирина" } });
    fireEvent.click(screen.getByRole("button", { name: "Войти в комнату" }));
    await screen.findByRole("heading", { name: "Основной стол" });
    expect(api.joinRegistered).toHaveBeenCalledWith(
      "account-token", "kept-invite", "Ирина", undefined,
    );
    first.unmount();
    render(<GuestJoin inviteToken="kept-invite" accessToken="account-token" api={api} />);
    await screen.findByRole("heading", { name: "Основной стол" });
    expect(api.restoreGuest).toHaveBeenLastCalledWith("kept-invite", "account-token");
  });
});
