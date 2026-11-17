"""Validated runtime configuration. Process environment overrides an optional .env file."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(os.environ.get("PARKING_ENV_FILE", ROOT / ".env"), override=False)


def secret(name, default=""):
    path = os.environ.get(name + "_FILE")
    return Path(path).read_text().rstrip("\r\n") if path else os.environ.get(name, default)


def integer(name, default, low, high):
    value = int(os.environ.get(name, default))
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def number(name, default, low, high):
    value = float(os.environ.get(name, default))
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def flag(name, default=False):
    value = os.environ.get(name, str(default)).lower()
    if value not in ("true", "false", "1", "0"):
        raise ValueError(f"{name} must be true or false")
    return value in ("true", "1")


DATA_DIR = Path(os.environ.get("PARKING_DATA_DIR", ROOT / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("PARKING_DATABASE_PATH", DATA_DIR / "parking.sqlite3")).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
HOST = os.environ.get("PARKING_HOST", "127.0.0.1")
PORT = integer("PARKING_PORT", 8000, 1, 65535)
SHARE_HOST = os.environ.get("PARKING_SHARE_HOST", HOST)
SHARE_PORT = integer("PARKING_SHARE_PORT", 8002, 1, 65535)
BROKER_URL = secret("CELERY_BROKER_URL", "redis://127.0.0.1:6381/0")
TASK_QUEUE = os.environ.get("PARKING_TASK_QUEUE", "parking_checker")
CHECK_INTERVAL_SECONDS = integer("PARKING_CHECK_INTERVAL_SECONDS", 3600, 30, 604800)
COLLECTOR_DELAY_SECONDS = number("PARKING_COLLECTOR_DELAY_SECONDS", 1.1, 0, 60)
PORTAL_URL = os.environ.get("PARKING_PORTAL_URL", "https://mvb.syr.gov").rstrip("/")
PORTAL_TIMEOUT_SECONDS = number("PARKING_PORTAL_TIMEOUT_SECONDS", 25, 1, 120)
PORTAL_RETRIES = integer("PARKING_PORTAL_RETRIES", 3, 1, 10)
TIMEZONE = os.environ.get("PARKING_TIMEZONE", "America/New_York")
ZoneInfo(TIMEZONE)  # Reject a misspelled zone before starting a service.
TIMEZONE_LABEL = os.environ.get(
    "PARKING_TIMEZONE_LABEL", "Eastern time" if TIMEZONE == "America/New_York" else TIMEZONE
)
SHARE_BASE_URL = os.environ.get("PARKING_SHARE_BASE_URL", f"http://127.0.0.1:{SHARE_PORT}").rstrip(
    "/"
)
AUTH_BASE_URL = os.environ.get("PARKING_BASE_URL", f"http://127.0.0.1:{PORT}").rstrip("/")
AUTH_COOKIE_SECURE = AUTH_BASE_URL.startswith("https://") or flag("PARKING_COOKIE_SECURE")
AUTH_SESSION_HOURS = integer("PARKING_SESSION_HOURS", 8, 1, 168)
AUTH_SSO_SESSION_HOURS = integer("PARKING_SSO_SESSION_HOURS", 720, 1, 2160)
INVITE_TTL_HOURS = integer("PARKING_INVITE_TTL_HOURS", 168, 1, 720)
LOOKUP_TTL_SECONDS = integer("PARKING_LOOKUP_TTL_SECONDS", 600, 60, 3600)
CORS_ORIGINS = [
    v.strip()
    for v in os.environ.get(
        "PARKING_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173"
        if AUTH_BASE_URL.startswith("http://")
        else "",
    ).split(",")
    if v.strip()
]
SMTP_TIMEOUT_SECONDS = number("PARKING_SMTP_TIMEOUT_SECONDS", 10, 1, 120)
EMAIL_INTERVAL_SECONDS = integer("PARKING_EMAIL_INTERVAL_SECONDS", 60, 10, 3600)
EMAIL_BATCH_SIZE = integer("PARKING_EMAIL_BATCH_SIZE", 5, 1, 100)
EMAIL_MAX_ATTEMPTS = integer("PARKING_EMAIL_MAX_ATTEMPTS", 5, 1, 20)
STREETS_PATH = Path(os.environ.get("PARKING_STREETS_FILE", DATA_DIR / "streets.geojson")).resolve()
STREETS_SOURCE_URL = os.environ.get(
    "PARKING_STREETS_SOURCE_URL",
    "https://services6.arcgis.com/bdPqSfflsdgFRVVM/ArcGIS/rest/services/Syracuse_Ratings_Open_Data_Copy_2023/FeatureServer/0",
).rstrip("/")
FETCH_STREETS_ON_START = flag("PARKING_FETCH_STREETS_ON_START", True)
MAP_STYLE_URL = os.environ.get(
    "PARKING_MAP_STYLE_URL", "https://tiles.openfreemap.org/styles/positron"
)
MAP_LATITUDE = number("PARKING_MAP_LATITUDE", 43.039, -90, 90)
MAP_LONGITUDE = number("PARKING_MAP_LONGITUDE", -76.135, -180, 180)
MAP_ZOOM = number("PARKING_MAP_ZOOM", 13.5, 1, 19)
LOCATION_LABEL = os.environ.get("PARKING_LOCATION_LABEL", "Syracuse, New York")
STREETS_ATTRIBUTION = os.environ.get("PARKING_STREETS_ATTRIBUTION", "City of Syracuse")
PAYMENT_URL = os.environ.get("PARKING_PAYMENT_URL", "https://mvb.syr.gov/")
DEFAULT_HISTORY_DAYS = integer("PARKING_DEFAULT_HISTORY_DAYS", 90, 0, 365)
if DEFAULT_HISTORY_DAYS not in (0, 7, 30, 90, 180, 365):
    raise ValueError("PARKING_DEFAULT_HISTORY_DAYS must be 0, 7, 30, 90, 180 or 365")
# New installations start empty. Real garage records belong in SQLite, never in source.
SEED_CARS = []
