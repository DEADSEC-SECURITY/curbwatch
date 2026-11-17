"""Street normalization and versioned geometry caches (safe across first-start downloads)."""

from functools import lru_cache
import json
import re
from . import config


def street_key(value):
    value = re.sub(r"\b(?:\d+[-–]?\d*|BLOCK|BLK|OF)\b", " ", str(value).upper())
    words = re.sub("[^A-Z0-9 ]", " ", value).split()
    aliases = {
        "STREET": "ST",
        "AVENUE": "AVE",
        "AV": "AVE",
        "BOULEVARD": "BLVD",
        "ROAD": "RD",
        "DRIVE": "DR",
        "LANE": "LN",
        "COURT": "CT",
        "PLACE": "PL",
        "TERRACE": "TER",
        "PARKWAY": "PKWY",
        "NORTH": "N",
        "SOUTH": "S",
        "EAST": "E",
        "WEST": "W",
    }
    return " ".join(aliases.get(word, word) for word in words)


def geometry_version():
    try:
        return str(config.STREETS_PATH), config.STREETS_PATH.stat().st_mtime_ns
    except FileNotFoundError:
        return str(config.STREETS_PATH), 0


@lru_cache(maxsize=2)
def _data(path, version):
    if not version:
        return {"type": "FeatureCollection", "features": []}
    from pathlib import Path

    data = json.loads(Path(path).read_text())
    for feature in data["features"]:
        feature["properties"]["street_key"] = street_key(feature["properties"]["name"])
    return data


def street_data():
    return _data(*geometry_version())


@lru_cache(maxsize=2)
def _index(path, version):
    index = {}
    for feature in _data(path, version)["features"]:
        index.setdefault(feature["properties"]["street_key"], []).append(feature)
    return index


def street_index():
    return _index(*geometry_version())


def clear_street_cache():
    _data.cache_clear()
    _index.cache_clear()


def matched_key(key):
    if key in street_index():
        return key
    choices = [name for name in street_index() if re.sub(r"^[NSEW] ", "", name) == key]
    return choices[0] if len(choices) == 1 else None
