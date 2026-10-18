import importlib.util
from pathlib import Path

# Reuse the established public HTTP/command integration fixture, not a second fake service.
spec = importlib.util.spec_from_file_location(
    "card_import_shared_fixture", Path(__file__).parents[1] / "cards" / "conftest.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
table = module.table
