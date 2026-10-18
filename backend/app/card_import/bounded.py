import asyncio
import json
import os
import sys
from pathlib import Path

from app.card_import.models import (
    MAX_BYTES,
    PARSER_TIMEOUT,
    Diagnostic,
    DraftSet,
    ParseFailure,
    fail,
)

_slots = asyncio.Semaphore(2)
_pythonpath = str(Path(__file__).resolve().parents[2])


async def parse_bounded(data: bytes, format: str) -> DraftSet:
    if not 0 < len(data) <= MAX_BYTES:
        raise fail("file_size", "Разрешены файлы до 5 МБ")
    async with _slots:
        environment = {"PATH": os.defpath, "PYTHONPATH": _pythonpath}
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.card_import.worker",
            format,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(data), timeout=PARSER_TIMEOUT)
        except (TimeoutError, asyncio.CancelledError):
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise fail("parse_timeout", "Обработка прервана: превышен лимит времени") from None
        if process.returncode != 0 or len(stdout) > 10 * MAX_BYTES:
            raise fail("parse_limit", "Обработка прервана: документ слишком сложный")
        result = json.loads(stdout)
        if "diagnostics" in result:
            raise ParseFailure([Diagnostic.model_validate(d) for d in result["diagnostics"]])
        if "draftset" not in result:
            raise fail("corrupt_file", "Файл повреждён или не поддерживается")
        return DraftSet.model_validate(result["draftset"])
