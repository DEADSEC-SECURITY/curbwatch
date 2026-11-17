"""Exercise production imports without pytest's OIDC imports masking registration."""

import os
from pathlib import Path
import subprocess
import sys


def test_fresh_application_registers_oidc_routes(tmp_path):
    program = """
from fastapi.testclient import TestClient
from backend.main import app
with TestClient(app) as client:
    start = client.get('/api/auth/oidc/start', follow_redirects=False)
    assert start.status_code == 303
    assert start.headers['location'].endswith('sso_disabled')
    callback = client.get('/api/auth/oidc/callback', follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers['location'].endswith('sso_failed')
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PARKING_DATA_DIR": str(tmp_path),
            "PARKING_FETCH_STREETS_ON_START": "false",
            "PARKING_OIDC_ENABLED": "false",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
