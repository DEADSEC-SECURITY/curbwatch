import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.db import init_db
from backend.main import app


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    for name in (
        "PARKING_OIDC_ISSUER",
        "PARKING_BOOTSTRAP_ADMIN_EMAIL",
        "PARKING_AUTH_KEY",
        "PARKING_AUTH_KEY_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    import os

    for name in list(os.environ):
        if name.startswith(("PARKING_SMTP_", "PARKING_EMAIL_", "PARKING_OIDC_")):
            monkeypatch.delenv(name, raising=False)
    init_db(seed=False)
    return config.DB_PATH


@pytest.fixture
def client(database):
    # Prevent app startup from adding the user's real plates to test databases.
    import backend.main

    original = backend.main.init_db
    original_portal = backend.main.SyracusePortal

    class EmptyPortal:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def search(self, plate):
            return []

    backend.main.init_db = lambda: init_db(seed=False)
    backend.main.SyracusePortal = EmptyPortal
    try:
        from backend.auth import create_admin

        create_admin("admin@example.com", "Testing-password-123!")
        with TestClient(app) as test:
            session = test.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "password": "Testing-password-123!"},
            ).json()
            test.headers["X-CSRF-Token"] = session["csrf_token"]
            # Include JSON content type for bodyless authenticated mutations, like the browser helper.
            test.headers["Content-Type"] = "application/json"
            yield test
    finally:
        backend.main.init_db = original
        backend.main.SyracusePortal = original_portal


@pytest.fixture
def raw_ticket():
    return {
        "ticket_number": "TEST001",
        "plate_number": "TEST123",
        "tstatusid": 19,
        "issue_date": {"$date": {"$numberLong": "1730730600000"}},
        "location": {"locationid": 39, "description": "WAVERLY AVE"},
        "balance": {"$numberDecimal": "0.00"},
        "violation": {
            "amount": {"$numberDecimal": "25.00"},
            "type": {"display_text": "Parking violation"},
        },
        "surcharges": [],
    }


@pytest.fixture(autouse=True)
def street_geometry(monkeypatch):
    from pathlib import Path
    from backend.streets import clear_street_cache

    monkeypatch.setattr(
        config, "STREETS_PATH", Path(__file__).parent / "fixtures" / "streets.geojson"
    )
    clear_street_cache()
    yield
    clear_street_cache()
