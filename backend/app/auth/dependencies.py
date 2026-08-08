from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt import AuthenticationError, AuthIdentity, SupabaseJWTVerifier
from app.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def build_verifier(issuer: str, audience: str, jwks_url: str) -> SupabaseJWTVerifier:
    return SupabaseJWTVerifier(issuer=issuer, audience=audience, jwks_url=jwks_url)


def get_verifier(settings: Annotated[Settings, Depends(get_settings)]) -> SupabaseJWTVerifier:
    if settings.supabase_issuer is None or settings.supabase_jwks_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication is not configured",
        )
    return build_verifier(
        settings.supabase_issuer,
        settings.supabase_jwt_audience,
        settings.supabase_jwks_url,
    )


def get_current_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    verifier = get_verifier(settings)
    try:
        return verifier.verify(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
