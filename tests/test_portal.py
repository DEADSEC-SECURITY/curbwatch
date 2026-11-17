import os
import json
from pathlib import Path
import shutil
import subprocess
import pytest

from backend.portal import SyracusePortal, PortalError, normalize_ticket

SIM_URL = os.environ.get("PARKING_SIMULATION_URL")


@pytest.fixture(scope="module", autouse=True)
def local_portal_simulation():
    global SIM_URL
    if SIM_URL:
        yield
        return
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed for the local portal HTTP simulation")
    script = Path(__file__).resolve().parents[1] / "postman" / "mocks" / "syracuse" / "default.js"
    process = subprocess.Popen(
        [node, str(script)], env={**os.environ, "PORT": "0"}, stdout=subprocess.PIPE, text=True
    )
    try:
        ready = json.loads(process.stdout.readline())
        SIM_URL = f"http://127.0.0.1:{ready['port']}"
        yield
    finally:
        process.terminate()
        process.wait(timeout=5)
        SIM_URL = None


def test_real_http_client_handles_multiple_single_and_empty_results():
    with SyracusePortal(SIM_URL) as portal:
        tickets = portal.search("MULTI123")
        assert len(tickets) == 2
        assert tickets[0]["ticket_number"] == "SIM001"
        single = portal.search("SINGLE123")[0]
        assert single["ticket_number"] == "SIM003"
        assert normalize_ticket(single)["fine_cents"] == 2500
        assert portal.search("EMPTY123") == []


def test_unknown_html_is_a_failure_instead_of_no_tickets():
    with SyracusePortal(SIM_URL) as portal:
        with pytest.raises(PortalError, match="page instead"):
            portal.search("BROKEN123")


def test_http_500_is_retried_then_reported_as_failure():
    with SyracusePortal(SIM_URL) as portal:
        with pytest.raises(PortalError, match="unavailable"):
            portal.search("ERROR123")


def test_json_error_containing_empty_result_words_is_not_an_empty_result():
    with SyracusePortal(SIM_URL) as portal:
        with pytest.raises(PortalError, match="unrecognized"):
            portal.search("JSONERR1")


def test_preview_then_save_uses_the_real_http_adapter_against_local_simulation(client, monkeypatch):
    monkeypatch.setattr("backend.main.SyracusePortal", lambda: SyracusePortal(SIM_URL))
    response = client.post("/api/plate-lookups", json={"plate": "MULTI123"})
    assert response.status_code == 200
    assert response.json()["ticket_count"] == 2
    assert client.get("/api/cars").json() == []
    saved = client.post("/api/cars", json={"plate": "MULTI123", "lookup_id": response.json()["id"]})
    assert saved.status_code == 201
    assert client.get("/api/cars").json()[0]["ticket_count"] == 2


def test_failed_http_preview_cannot_authorize_a_new_car(client, monkeypatch):
    monkeypatch.setattr("backend.main.SyracusePortal", lambda: SyracusePortal(SIM_URL))
    response = client.post("/api/plate-lookups", json={"plate": "BROKEN123"})
    assert response.status_code == 503
    assert client.get("/api/cars").json() == []
