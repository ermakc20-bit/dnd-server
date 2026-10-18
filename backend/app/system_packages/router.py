from typing import Any

from fastapi import APIRouter, HTTPException

from app.scenes.models import SceneFailure
from app.system_packages.service import get_schema

router = APIRouter(prefix="/api/v1/system-packages", tags=["system-packages"])


@router.get("/{system_id}/{version}")
async def schema(system_id: str, version: int) -> dict[str, Any]:
    try:
        return get_schema(system_id, version)
    except SceneFailure as error:
        raise HTTPException(
            status_code=error.status_code, detail={"code": error.code, "message": error.message}
        ) from error
