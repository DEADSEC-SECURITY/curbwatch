"""The frontend receives an allowlist, never the process environment or saved settings."""

import json
from . import config


def public_config_script():
    values = {
        "timezone": config.TIMEZONE,
        "timezoneLabel": config.TIMEZONE_LABEL,
        "locationLabel": config.LOCATION_LABEL,
        "mapStyleUrl": config.MAP_STYLE_URL,
        "mapCenter": [config.MAP_LONGITUDE, config.MAP_LATITUDE],
        "mapZoom": config.MAP_ZOOM,
        "streetsAttribution": config.STREETS_ATTRIBUTION,
        "defaultHistoryDays": config.DEFAULT_HISTORY_DAYS,
        "checkIntervalSeconds": config.CHECK_INTERVAL_SECONDS,
    }
    return "window.CURBWATCH_CONFIG = " + json.dumps(values) + ";\n"
