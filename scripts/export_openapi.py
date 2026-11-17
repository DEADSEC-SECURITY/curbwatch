"""Export contracts without opening a database or starting background services."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app
from backend.shared import app as shared

folder = Path(__file__).resolve().parents[1] / "docs" / "api"
folder.mkdir(parents=True, exist_ok=True)
for name, application in [("openapi.json", app), ("shared-openapi.json", shared)]:
    (folder / name).write_text(json.dumps(application.openapi(), indent=2) + "\n")
