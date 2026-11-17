from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
import json
import ssl
import time

from fastapi.testclient import TestClient
import pytest

from backend import config
from backend.auth import create_admin
from backend.collector import collect, reserve_run
from backend.db import connect, now, upsert_ticket
from backend.email_templates import NY, monthly_email, new_ticket_email, sample_tickets
from backend.mail_config import MailSettings, mail_settings, save_mail_settings
from backend.main import app
from backend.notifications import (
    claim_delivery,
    deliver_pending,
    insert_delivery,
    notification_policy,
    queue_monthly_reports,
    queue_ticket,
)
from smtp_sink import Sink

AT = datetime(2026, 11, 16, 9, 15, tzinfo=NY)


@pytest.fixture
def sink():
    server = Sink()
    try:
        yield server
    finally:
        server.close()


def configure(sink, **updates):
    body = dict(
        enabled=True,
        host="127.0.0.1",
        port=sink.server_address[1],
        security="none",
        from_email="parking@example.com",
    )
    body.update(updates)
    save_mail_settings(MailSettings(**body))
    return notification_policy()


def add_car(email="owner@example.com", name="Everyday car", plate="TEST123", active=1):
    with connect() as db:
        return db.execute(
            "INSERT INTO cars(name,plate,email,active,created_at) VALUES (?,?,?,?,?)",
            (name, plate, email, active, now()),
        ).lastrowid


def add_ticket(car_id, number="TICKET1", balance=3500, age=12, hour=11, **updates):
    ticket = dict(
        ticket_number=number,
        issued_at=(AT - timedelta(days=age)).replace(hour=hour).isoformat(),
        time_source="ticket_issue_date",
        description="Parking violation",
        location_name="WAVERLY AVE",
        location_id="39",
        street_key="WAVERLY AVE",
        fine_cents=3500,
        balance_cents=balance,
        surcharge_cents=0,
        additional_fees_cents=0,
        status_id=16,
        status="Outstanding",
        raw_payload="{}",
    )
    ticket.update(updates)
    with connect() as db:
        upsert_ticket(db, car_id, ticket)
        return db.execute("SELECT id FROM tickets WHERE ticket_number=?", (number,)).fetchone()[0]


def outbox():
    with connect() as db:
        return [
            dict(row) for row in db.execute("SELECT * FROM email_outbox ORDER BY created_at,id")
        ]


def decode(message):
    parsed = BytesParser(policy=policy.default).parsebytes(message)
    return (
        parsed,
        parsed.get_body(preferencelist=("plain",)).get_content(),
        parsed.get_body(preferencelist=("html",)).get_content(),
    )


def test_new_ticket_mime_one_message_per_event_no_duplicates(database, sink):
    settings = configure(sink)
    car = add_car()
    ticket_id = add_ticket(car)
    with connect() as db:
        assert queue_ticket(db, ticket_id, settings)
        assert queue_ticket(db, ticket_id, settings) is None
    assert deliver_pending(at=AT) == 1
    assert deliver_pending(at=AT) == 0
    assert len(sink.messages) == 1 and outbox()[0]["status"] == "sent"
    message, text, html = decode(sink.messages[0])
    assert message["To"] == "owner@example.com"
    assert str(message["From"]) == "Curbwatch <parking@example.com>"
    assert "$35.00 outstanding" in message["Subject"]
    assert "12 days ago" in text and "12 days ago" in html
    assert "https://mvb.syr.gov/" in text and 'href="https://mvb.syr.gov/"' in html
    assert "#203d31" in html and "#deedb2" in html
    assert "TEST123" in html and "TICKET1" in html
    assert "<script" not in html and "<img" not in html
    assert message["Message-ID"] == outbox()[0]["message_id"]


def test_collector_enqueues_only_new_records_and_payment_updates_do_not_repeat(
    database, sink, raw_ticket
):
    configure(sink)
    add_car()
    raw_ticket["tstatusid"] = 16
    raw_ticket["balance"] = {"$numberDecimal": "35"}

    class Portal:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def search(self, plate):
            return [raw_ticket]

    run, _ = reserve_run()
    collect(run, Portal, delay=0)
    assert len(outbox()) == 1
    raw_ticket["balance"] = {"$numberDecimal": "0"}
    run, _ = reserve_run()
    collect(run, Portal, delay=0)
    assert len(outbox()) == 1
    assert deliver_pending(at=AT) == 1
    assert "No balance due" in decode(sink.messages[0])[2]


def test_disabled_policy_and_missing_email_never_generate_alerts(database, sink):
    settings = configure(sink, enabled=False)
    car = add_car(email=None)
    ticket_id = add_ticket(car)
    with connect() as db:
        assert queue_ticket(db, ticket_id, settings) is None
    settings = configure(sink)
    with connect() as db:
        assert queue_ticket(db, ticket_id, settings) is None
    with connect() as db:
        db.execute("UPDATE cars SET email=?", ("owner@example.com",))
    settings = configure(sink, ticket_alerts=False)
    with connect() as db:
        assert queue_ticket(db, ticket_id, settings) is None
    assert not outbox() and deliver_pending(at=AT) == 0


def test_initial_lookup_and_import_do_not_send_historical_batches(client, sink, raw_ticket):
    configure(sink)
    lookup = client.post("/api/plate-lookups", json={"plate": "TEST123"}).json()
    car = client.post(
        "/api/cars",
        json={
            "plate": "TEST123",
            "email": "owner@example.com",
            "lookup_id": lookup["id"],
            "confirm_no_tickets": True,
        },
    ).json()
    response = client.post(
        "/api/import",
        json={
            "format": "json",
            "car_id": car["id"],
            "content": json.dumps(
                [
                    {
                        "Ticket Number": "OLD1",
                        "Issue Date": "2024-01-01",
                        "Balance": "25",
                        "Fine": "25",
                    }
                ]
            ),
        },
    )
    assert response.status_code == 200
    assert outbox() == []


def test_monthly_groups_case_insensitive_recipients_all_cars_and_only_outstanding(database, sink):
    configure(sink)
    first = add_car(email="Owner@Example.com")
    second = add_car(email="owner@example.com", name="Weekend car", plate="TEST456", active=0)
    no_email = add_car(email=None, plate="NOEMAIL")
    other = add_car(email="other@example.com", plate="OTHER1")
    add_ticket(first, "FIRST", balance=3500, age=12)
    add_ticket(second, "SECOND", balance=6500, age=400)
    add_ticket(first, "PAID", balance=0)
    add_ticket(no_email, "MISSING", balance=2000)
    add_ticket(other, "OTHER", balance=0)
    assert queue_monthly_reports(AT) == 1
    assert queue_monthly_reports(AT) == 0
    assert deliver_pending(at=AT) == 1
    assert len(sink.messages) == 1
    message, text, html = decode(sink.messages[0])
    assert "$100.00 outstanding" in message["Subject"]
    assert "12 days ago" in text and "400 days ago" in text
    assert "FIRST" in html and "SECOND" in html and "Weekend car" in html
    assert "PAID" not in html and "MISSING" not in html and "OTHER1" not in html
    assert "$35.00" in html and "$65.00" in html


def test_monthly_due_time_catchup_and_zero_balance_suppression(database, sink):
    configure(sink)
    car = add_car()
    assert (
        queue_monthly_reports(datetime(2026, 11, 1, 14, 14, tzinfo=timezone.utc)) == 0
    )  # 09:14 EST
    assert queue_monthly_reports(datetime(2026, 11, 1, 14, 15, tzinfo=timezone.utc)) == 0
    add_ticket(car)
    assert (
        queue_monthly_reports(AT) == 0
    )  # Empty first-of-month run is still one completed monthly batch.
    assert queue_monthly_reports(AT.replace(month=12)) == 1
    # Sending an obsolete monthly report in a later month is suppressed.
    assert deliver_pending(at=AT.replace(month=12, day=2)) == 1
    assert queue_monthly_reports(AT.replace(year=2027, month=1)) == 1
    assert deliver_pending(at=AT.replace(year=2027, month=2)) == 0
    assert outbox()[-1]["status"] == "cancelled"


def test_delivery_uses_current_balance_and_cancels_removed_recipients(database, sink):
    settings = configure(sink)
    car = add_car()
    ticket_id = add_ticket(car)
    with connect() as db:
        queue_ticket(db, ticket_id, settings)
    with connect() as db:
        db.execute("UPDATE cars SET email=? WHERE id=?", ("replacement@example.com", car))
    assert deliver_pending(at=AT) == 0
    assert outbox()[0]["status"] == "cancelled"
    assert queue_monthly_reports(AT) == 1
    with connect() as db:
        db.execute("UPDATE tickets SET balance_cents=0")
    assert deliver_pending(at=AT) == 0 and len(sink.messages) == 0


def test_retry_backoff_then_acceptance_keeps_stable_message_id(database, sink):
    configure(sink)
    car = add_car()
    ticket_id = add_ticket(car)
    with connect() as db:
        queue_ticket(db, ticket_id, notification_policy())
    sink.reject_data = 451
    assert deliver_pending(at=AT) == 0
    row = outbox()[0]
    assert (
        row["status"] == "queued" and row["attempts"] == 1 and row["next_attempt_at"] > time.time()
    )
    assert deliver_pending(at=AT) == 0  # Backoff isn't bypassed.
    sink.reject_data = 0
    with connect() as db:
        db.execute("UPDATE email_outbox SET next_attempt_at=0")
    assert deliver_pending(at=AT) == 1
    assert outbox()[0]["message_id"] == row["message_id"]
    assert len(sink.messages) == 1


def test_permanent_rejection_and_ambiguous_handoff_are_not_automatically_resent(database, sink):
    configure(sink)
    car = add_car()
    ticket_id = add_ticket(car)
    with connect() as db:
        queue_ticket(db, ticket_id, notification_policy())
    sink.reject_data = 550
    assert deliver_pending(at=AT) == 0
    assert outbox()[0]["status"] == "failed"
    second = add_ticket(car, "SECOND")
    with connect() as db:
        queue_ticket(db, second, notification_policy())
    sink.reject_data = 0
    sink.disconnect_after_data = True
    assert deliver_pending(at=AT) == 0
    assert outbox()[1]["status"] == "uncertain"
    assert deliver_pending(at=AT) == 0 and len(sink.messages) == 1


def test_concurrent_claims_and_crashed_senders_do_not_duplicate(database, sink):
    configure(sink)
    car = add_car()
    ticket_id = add_ticket(car)
    with connect() as db:
        queue_ticket(db, ticket_id, notification_policy())
    claimed = claim_delivery(int(time.time()))
    assert claimed and claim_delivery(int(time.time())) is None
    with connect() as db:
        db.execute("UPDATE email_outbox SET lease_until=0")
    assert claim_delivery(int(time.time())) is None
    assert outbox()[0]["status"] == "uncertain" and len(sink.messages) == 0


def test_unknown_ages_and_html_values_are_safe():
    ticket = sample_tickets(AT)[0]
    ticket.update(
        car_name="<img src=x onerror=alert(1)>",
        description="<script>alert(1)</script>",
        issued_at=None,
    )
    content = new_ticket_email(ticket, AT)
    assert "&lt;img" in content.html and "<img" not in content.html
    assert "&lt;script" in content.html and "<script" not in content.html
    assert "Age unavailable" in content.html
    ticket["issued_at"] = AT.isoformat()
    ticket["time_source"] = "legacy_import_unverified"
    assert "Age unverified" in monthly_email([ticket], "2026-11", AT).html


def test_settings_auth_secret_redaction_previews_and_test_delivery(client, sink, monkeypatch):
    body = dict(
        enabled=True,
        host="127.0.0.1",
        port=sink.server_address[1],
        security="none",
        username="smtp-user",
        password="TOP-SECRET-SMTP",
        from_email="parking@example.com",
    )
    response = client.put("/api/admin/email", json=body)
    assert response.status_code == 200, response.text
    assert "TOP-SECRET-SMTP" not in response.text
    assert response.json()["configuration"]["has_password"] is True
    with connect() as db:
        assert (
            "TOP-SECRET-SMTP"
            not in db.execute("SELECT value FROM app_meta WHERE key='mail_settings'").fetchone()[0]
        )
    response = client.put("/api/admin/email", json={**body, "password": None})
    assert (
        response.status_code == 200
        and mail_settings(secret=True)[0]["password"] == "TOP-SECRET-SMTP"
    )
    for kind in ("new_ticket", "monthly"):
        preview = client.get("/api/admin/email/preview?kind=" + kind)
        assert preview.status_code == 200 and "DEMO123" in preview.text
        assert preview.headers["cache-control"] == "no-store"
        assert "TOP-SECRET" not in preview.text
    assert (
        client.post("/api/admin/email/test", json={"recipient": "preview@example.com"}).status_code
        == 202
    )
    assert deliver_pending(at=AT) == 1 and len(sink.messages) == 1
    assert "AUTH" in sink.commands
    assert (
        client.put(
            "/api/admin/email", json={**body, "host": "remote.example.com", "security": "none"}
        ).status_code
        == 422
    )
    assert client.put("/api/admin/email", json={**body, "report_day": 31}).status_code == 422
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/admin/email").status_code == 401
        assert anonymous.get("/api/admin/email/preview").status_code == 401
    monkeypatch.setenv("PARKING_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("PARKING_SMTP_PASSWORD", "ENV-SECRET")
    assert client.get("/api/admin/email").json()["configuration"]["managed_by_environment"]
    assert "ENV-SECRET" not in client.get("/api/admin/email").text
    assert client.put("/api/admin/email", json=body).status_code == 409


def test_uncertain_retry_requires_acknowledgement_and_member_cannot_administer(client, sink):
    configure(sink)
    with connect() as db:
        delivery_id = insert_delivery(db, "test", "unique", "preview@example.com")
        db.execute("UPDATE email_outbox SET status='uncertain' WHERE id=?", (delivery_id,))
    url = f"/api/admin/email/deliveries/{delivery_id}/retry"
    assert client.post(url, json={}).status_code == 409
    assert client.post(url, json={"acknowledge_uncertain": True}).status_code == 202
    assert client.post(url, json={"acknowledge_uncertain": True}).status_code == 409
    create_admin("member@example.com", "Member-password-123")
    with connect() as db:
        db.execute("UPDATE users SET role='member' WHERE email='member@example.com'")
    with TestClient(app) as member:
        session = member.post(
            "/api/auth/login",
            json={"email": "member@example.com", "password": "Member-password-123"},
        ).json()
        member.headers["X-CSRF-Token"] = session["csrf_token"]
        assert member.get("/api/admin/email").status_code == 403
        assert (
            member.post(
                "/api/admin/email/test", json={"recipient": "preview@example.com"}
            ).status_code
            == 403
        )


@pytest.fixture
def tls_certificate(tmp_path):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import ipaddress

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certfile = tmp_path / "cert.pem"
    keyfile = tmp_path / "key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile, keyfile)
    return certfile, context


@pytest.mark.parametrize("mode", ["starttls", "tls"])
def test_real_verified_tls_delivery(database, tls_certificate, monkeypatch, mode):
    certfile, context = tls_certificate
    sink = Sink(mode, context)
    original = ssl.create_default_context
    monkeypatch.setattr(ssl, "create_default_context", lambda: original(cafile=str(certfile)))
    try:
        configure(sink, security=mode)
        with connect() as db:
            insert_delivery(db, "test", "tls-test", "preview@example.com")
        assert deliver_pending(at=AT) == 1
        assert len(sink.messages) == 1
        assert ("STARTTLS" in sink.commands) == (mode == "starttls")
    finally:
        sink.close()


def test_untrusted_tls_certificate_is_rejected_without_plaintext_fallback(
    database, tls_certificate
):
    _, context = tls_certificate
    sink = Sink("starttls", context)
    try:
        configure(sink, security="starttls")
        with connect() as db:
            insert_delivery(db, "test", "tls-test", "preview@example.com")
        assert deliver_pending(at=AT) == 0
        assert outbox()[0]["status"] == "failed" and outbox()[0]["error_code"] == "tls"
        assert not sink.messages and "DATA" not in sink.commands
    finally:
        sink.close()


def test_master_pause_type_suppression_and_retry_limit(database, sink):
    settings = configure(sink)
    car = add_car()
    ticket_id = add_ticket(car)
    with connect() as db:
        queue_ticket(db, ticket_id, settings)
    configure(sink, enabled=False)
    assert deliver_pending(at=AT) == 0 and outbox()[0]["status"] == "queued"
    configure(sink, ticket_alerts=False)
    assert deliver_pending(at=AT) == 0 and outbox()[0]["status"] == "cancelled"
    configure(sink)
    with connect() as db:
        insert_delivery(db, "test", "retry-limit", "preview@example.com")
    sink.reject_data = 451
    for _ in range(5):
        with connect() as db:
            db.execute("UPDATE email_outbox SET next_attempt_at=0")
        deliver_pending(at=AT)
    assert outbox()[1]["status"] == "failed" and outbox()[1]["attempts"] == 5
    assert len(sink.messages) == 0


def test_configuration_problems_are_visible_without_losing_queued_messages(database, sink):
    configure(sink, username="sender", password="protected-password")
    with connect() as db:
        insert_delivery(db, "test", "config-failure", "preview@example.com")
    (config.DATA_DIR / "auth.key").unlink()
    assert deliver_pending(at=AT) == 0
    assert outbox()[0]["status"] == "queued" and outbox()[0]["error_code"] == "configuration"
    from backend.notifications import delivery_status

    assert delivery_status()["configuration_error"]
    assert len(sink.messages) == 0


def test_email_writes_require_csrf_and_shared_links_never_open_settings(client, database):
    assert (
        client.put("/api/admin/email", json={}, headers={"X-CSRF-Token": "bad"}).status_code == 403
    )
    assert (
        client.post(
            "/api/admin/email/test",
            json={"recipient": "owner@example.com"},
            headers={"Origin": "https://wrong.example"},
        ).status_code
        == 403
    )
    from backend.shared import app as shared

    with TestClient(shared) as viewer:
        for path in ("/api/admin/email", "/api/admin/email/preview", "/api/admin/email/test"):
            assert viewer.get(path).status_code == 404
