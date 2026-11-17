import json
import os
from pathlib import Path
import subprocess
import sys

from backend import config
from backend.db import connect, init_db
from backend.runtime import public_config_script


def test_new_install_has_no_personal_cars(database):
    init_db()
    with connect() as db:
        assert db.execute("SELECT count(*) FROM cars").fetchone()[0] == 0


def test_runtime_script_allowlist_never_exposes_deployment_secrets(client, monkeypatch):
    monkeypatch.setenv("PARKING_SMTP_PASSWORD", "PRIVATE_SMTP_SECRET")
    monkeypatch.setenv("PARKING_OIDC_CLIENT_SECRET", "PRIVATE_OIDC_SECRET")
    monkeypatch.setattr(config, "TIMEZONE", "Europe/London")
    monkeypatch.setattr(config, "DEFAULT_HISTORY_DAYS", 180)
    response = client.get("/runtime-config.js")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert "Europe/London" in response.text and "180" in response.text
    assert (
        "PRIVATE_" not in response.text
        and "password" not in response.text
        and "client_secret" not in response.text
    )
    assert response.text == public_config_script()


def test_process_env_overrides_file_and_secret_files_are_supported(tmp_path):
    env_file = tmp_path / "configuration.env"
    env_file.write_text(
        "PARKING_PORT=8123\nPARKING_DEFAULT_HISTORY_DAYS=180\nPARKING_TIMEZONE=Europe/London\n"
    )
    secret = tmp_path / "broker-secret"
    secret.write_text("redis://example.invalid:6379/9\n")
    environment = {
        **os.environ,
        "PARKING_ENV_FILE": str(env_file),
        "PARKING_DATA_DIR": str(tmp_path / "data"),
        "PARKING_PORT": "8456",
        "CELERY_BROKER_URL_FILE": str(secret),
    }
    code = "from backend import config as c; import json; print(json.dumps([c.PORT,c.DEFAULT_HISTORY_DAYS,c.TIMEZONE,c.BROKER_URL]))"
    result = subprocess.run(
        [sys.executable, "-c", code], env=environment, capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout) == [
        8456,
        180,
        "Europe/London",
        "redis://example.invalid:6379/9",
    ]


def test_geometry_refreshes_after_missing_first_start_file(tmp_path, monkeypatch):
    from backend.streets import street_data, street_index

    path = tmp_path / "streets.geojson"
    monkeypatch.setattr(config, "STREETS_PATH", path)
    assert street_data()["features"] == []
    assert street_index() == {}
    path.write_text((Path(__file__).parent / "fixtures" / "streets.geojson").read_text())
    assert "WAVERLY AVE" in street_index()
    assert street_data()["features"]


def test_external_encryption_key_can_be_mounted_readonly(database, tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from backend.auth import encryption

    path = tmp_path / "external-auth-key"
    path.write_bytes(Fernet.generate_key())
    path.chmod(0o444)
    monkeypatch.setenv("PARKING_AUTH_KEY_FILE", str(path))
    encrypted = encryption().encrypt(b"configuration-secret")
    assert encryption().decrypt(encrypted) == b"configuration-secret"
