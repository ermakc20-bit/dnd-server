from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_identity
from app.auth.jwt import AuthIdentity

router = APIRouter(prefix="/api/v1", tags=["identity"])


class MeResponse(BaseModel):
    user_id: str
    email: str | None


@router.get("/me", response_model=MeResponse)
def me(identity: Annotated[AuthIdentity, Depends(get_current_identity)]) -> MeResponse:
    return MeResponse(user_id=str(identity.user_id), email=identity.email)
