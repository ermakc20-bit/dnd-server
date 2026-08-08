from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import jwt
from jwt import PyJWKClient
from pydantic import BaseModel


class AuthenticationError(Exception):
    """Raised when a bearer token cannot establish an identity."""


class AuthIdentity(BaseModel):
    user_id: UUID
    email: str | None = None
    session_id: UUID | None = None
    audience: str
    expires_at: datetime


SigningKeyResolver = Callable[[str], Any]


class SupabaseJWTVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str | None = None,
        signing_key_resolver: SigningKeyResolver | None = None,
    ) -> None:
        if signing_key_resolver is None and jwks_url is None:
            raise ValueError("jwks_url or signing_key_resolver is required")

        self._issuer = issuer.rstrip("/")
        self._audience = audience
        if signing_key_resolver is not None:
            self._resolve_signing_key = signing_key_resolver
        else:
            client = PyJWKClient(str(jwks_url), cache_keys=True, lifespan=600)
            self._resolve_signing_key = lambda token: client.get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> AuthIdentity:
        try:
            key = self._resolve_signing_key(token)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["ES256", "RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["aud", "exp", "iat", "iss", "sub"]},
            )
            expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=UTC)
            return AuthIdentity(
                user_id=UUID(str(claims["sub"])),
                email=claims.get("email"),
                session_id=UUID(str(claims["session_id"])) if claims.get("session_id") else None,
                audience=str(claims["aud"]),
                expires_at=expires_at,
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError("invalid bearer token") from exc
