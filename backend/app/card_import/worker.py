"""One bounded process per document. Never emits document text on failure."""

import json
import logging
import os
import resource
import sys
import threading
import time

from app.card_import.models import MAX_BYTES, ParseFailure
from app.card_import.parser import parse


def main() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    limit = 768 * 1024 * 1024
    if sys.platform == "darwin":
        # Darwin does not implement RLIMIT_AS/DATA; ru_maxrss is bytes on Darwin.
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
        result = parse(sys.stdin.buffer.read(MAX_BYTES + 1), sys.argv[1])
        sys.stdout.write(json.dumps({"draftset": result.model_dump(mode="json")}))
    except ParseFailure as error:
        sys.stdout.write(json.dumps({"diagnostics": [d.model_dump() for d in error.diagnostics]}))
    except Exception:
        sys.stdout.write('{"failed":true}')


if __name__ == "__main__":
    main()
