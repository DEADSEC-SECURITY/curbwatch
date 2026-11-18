"""Separate map-only ASGI service. Never mount the private app here."""

from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .activity import activity, HistoryDays
from .db import connect, init_db
from .sharing import require_share
from .streets import street_data


@asynccontextmanager
async def lifespan(app):
    init_db(seed=False)
    yield


app = FastAPI(
    title="Curbwatch shared map",
    version="0.3.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["Authorization"],
)


@app.middleware("http")
async def shared_response_headers(request, call_next):
    response = await call_next(request)
    response.headers.update(
        {
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "frame-ancestors 'none'; base-uri 'none'; object-src 'none'",
        }
    )
    return response


router = APIRouter(prefix="/api/shared", dependencies=[Depends(require_share)])
SUMMARY_FIELDS = (
    "street_key",
    "name",
    "total_tickets",
    "period_tickets",
    "sample_tickets",
    "distinct_days",
    "observed_days",
    "observed_day_fraction",
    "tickets_per_observed_day",
    "score",
    "level",
    "confidence",
    "basis",
    "mapped",
    "precision",
)


def safe_activity(result):
    def summary(value):
        return {key: value[key] for key in SUMMARY_FIELDS}

    # Allowlist nested properties too; never serialize ticket rows to viewers.
    return {
        key: result[key]
        for key in ("type", "hourly_counts", "date", "hour", "timezone", "period", "model")
    } | {
        "streets": [summary(street) for street in result["streets"]],
        "features": [
            {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": summary(feature["properties"]),
            }
            for feature in result["features"]
        ],
    }


@router.get("/activity")
def shared_activity(
    request: Request,
    day: date | None = None,
    hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    history_days: HistoryDays = config.DEFAULT_HISTORY_DAYS,
):
    if "car_id" in request.query_params:
        raise HTTPException(400, "Vehicle filtering is not available on shared maps")
    current = datetime.now(ZoneInfo(config.TIMEZONE))
    with connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT issued_at,time_source,street_key,location_name FROM tickets"
            )
        ]
    return safe_activity(
        activity(
            rows, day or current.date(), hour if hour is not None else current.hour, history_days
        )
    )


@router.get("/streets")
def shared_streets():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {key: feature["properties"][key] for key in ("name", "street_key")},
            }
            for feature in street_data()["features"]
        ],
    }


app.include_router(router)


@app.get("/runtime-config.js", include_in_schema=False)
def runtime_config():
    from .runtime import public_config_script

    return Response(
        public_config_script(),
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


dist = config.ROOT / "frontend" / "dist"
if dist.exists():

    @app.get("/share/", include_in_schema=False)
    def shared_page():
        return FileResponse(dist / "shared.html", headers={"Referrer-Policy": "no-referrer"})

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(dist / "favicon.svg")

    @app.get("/share/sw.js", include_in_schema=False)
    def shared_worker():
        return FileResponse(dist / "share" / "sw.js", media_type="application/javascript")

    app.mount("/icons", StaticFiles(directory=dist / "icons"), name="shared-icons")
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="shared-assets")
