"""Bounded archive validation process; application secrets are never inherited."""

import json
import logging
import os
import resource
import sys
import threading
import time

from app.campaign_transfer.archive import validate_archive
from app.campaign_transfer.models import MAX_ZIP, TransferFailure


def main() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    limit = 768 * 1024 * 1024
    if sys.platform == "darwin":

        def guard_memory() -> None:
            while True:
                if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > limit:
                    os._exit(70)
                time.sleep(0.01)

        threading.Thread(target=guard_memory, daemon=True).start()
    else:
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    logging.disable(logging.CRITICAL)
    try:
        sys.stdout.write(
            json.dumps({"documents": validate_archive(sys.stdin.buffer.read(MAX_ZIP + 1))})
        )
    except TransferFailure as error:
        sys.stdout.write(json.dumps({"error": error.code}))
    except Exception:
        sys.stdout.write('{"error":"invalid_archive"}')


if __name__ == "__main__":
    main()
