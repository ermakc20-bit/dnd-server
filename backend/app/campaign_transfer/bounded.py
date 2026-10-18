import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.campaign_transfer.models import MAX_JSON, MAX_ZIP, TransferFailure

_slots = asyncio.Semaphore(2)
_pythonpath = str(Path(__file__).resolve().parents[2])


async def validate_bounded(data: bytes) -> dict[str, Any]:
    if not 0 < len(data) <= MAX_ZIP:
        raise TransferFailure("archive_limit")
    async with _slots:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.campaign_transfer.worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={
                "PATH": os.defpath,
                "PYTHONPATH": _pythonpath,
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(data), 60)
        except (TimeoutError, asyncio.CancelledError):
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise TransferFailure("validation_interrupted") from None
        if process.returncode != 0 or len(stdout) > MAX_JSON:
            raise TransferFailure("validation_limit")
        result = json.loads(stdout)
        if "error" in result:
            raise TransferFailure(result["error"])
        documents: dict[str, Any] = result["documents"]
        return documents
