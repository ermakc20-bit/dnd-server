from __future__ import annotations


class CampaignError(Exception):
    code = "campaign_error"
    status_code = 400


class ForbiddenError(CampaignError):
    code = "forbidden"
    status_code = 403


class ResourceNotFoundError(CampaignError):
    code = "not_found"
    status_code = 404


class InvalidInviteError(CampaignError):
    code = "invalid_invite"
    status_code = 404


class RoomLockedError(CampaignError):
    code = "room_locked"
    status_code = 423


class InvalidPinError(CampaignError):
    code = "invalid_pin"
    status_code = 403


class RateLimitedError(CampaignError):
    code = "rate_limited"
    status_code = 429


class GuestSessionError(CampaignError):
    code = "invalid_guest_session"
    status_code = 401
