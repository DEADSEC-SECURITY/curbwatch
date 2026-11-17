import json
from pathlib import Path

PLATE_STATES = json.loads((Path(__file__).parent / "resources" / "plate-states.json").read_text())


def normalize_plate_state(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Choose a valid US plate state or territory")
    code = value.strip().upper()
    if not code:
        return None
    if code not in PLATE_STATES:
        raise ValueError("Choose a valid US plate state or territory")
    return code
