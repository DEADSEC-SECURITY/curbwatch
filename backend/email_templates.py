"""Table-based email layouts, inline styles, no remote images or tracking pixels."""

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .config import TIMEZONE, PAYMENT_URL, TIMEZONE_LABEL

NY = ZoneInfo(TIMEZONE)
PAY_URL = PAYMENT_URL
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif"


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str


def money(value):
    value = int(value or 0)
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value) // 100:,}.{abs(value) % 100:02d}"


def issued_details(ticket, at):
    if not ticket.get("issued_at"):
        return "Issue date unavailable", "Age unavailable"
    if ticket.get("time_source") != "ticket_issue_date":
        return "Issue date unverified", "Age unverified"
    try:
        issued = datetime.fromisoformat(ticket["issued_at"].replace("Z", "+00:00"))
        issued = issued.replace(tzinfo=NY) if issued.tzinfo is None else issued.astimezone(NY)
        days = (at.astimezone(NY).date() - issued.date()).days
        if days < 0:
            return "Issue date needs review", "Age unavailable"
        age = "Today" if not days else f"{days} day{'s' if days != 1 else ''} ago"
        return issued.strftime("%b %-d, %Y · %-I:%M%p").replace("AM", "am").replace(
            "PM", "pm"
        ) + " " + TIMEZONE_LABEL, age
    except (ValueError, TypeError):
        return "Issue date unavailable", "Age unavailable"


def plate_label(ticket):
    return str(ticket["plate"]) + (
        f" · {ticket['plate_state']}" if ticket.get("plate_state") else ""
    )


def vehicle_label(ticket):
    return f"{ticket.get('car_name') or ticket['plate']} · {plate_label(ticket)}"


def detail_row(label, value):
    return f"""<tr><td style="padding:12px 0;border-bottom:1px solid #e4e8e1;color:#849087;font-size:13px;vertical-align:top;width:36%">{escape(label)}</td><td style="padding:12px 0;border-bottom:1px solid #e4e8e1;color:#25342d;font-size:13px;text-align:right;overflow-wrap:anywhere">{escape(str(value))}</td></tr>"""


def frame(preheader, eyebrow, title, intro, body, at):
    stamp = (
        at.astimezone(NY).strftime("%b %-d, %Y at %-I:%M%p").replace("AM", "am").replace("PM", "pm")
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{escape(title)}</title>
<style>@media(max-width:620px){{.email-pad{{padding:28px 22px!important}}.email-title{{font-size:29px!important}}.outer-pad{{padding:16px 10px!important}}}}</style></head>
<body style="margin:0;padding:0;background:#f6f7f4;color:#25342d;font-family:{FONT}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;mso-hide:all">{escape(preheader)}</div>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f6f7f4"><tr><td class="outer-pad" align="center" style="padding:40px 16px">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="width:100%;max-width:600px;border:1px solid #e4e8e1;border-radius:18px;overflow:hidden;background:#fffffc">
<tr><td style="padding:26px 32px;background:#203d31"><table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td style="width:36px;height:36px;border-radius:9px;background:#deedb2;color:#203d31;text-align:center;font-size:27px;font-weight:700">P</td><td style="padding-left:12px;font-size:25px;font-weight:650;letter-spacing:-1px;color:#fffffc">curbwatch<span style="color:#deedb2">.</span></td></tr></table></td></tr>
<tr><td class="email-pad" style="padding:36px 32px 32px"><p style="margin:0 0 14px;color:#7e9269;font-size:10px;letter-spacing:2px;font-weight:600">{escape(eyebrow)}</p>
<h1 class="email-title" style="margin:0 0 16px;font-size:34px;line-height:1.18;font-weight:550;letter-spacing:-1px;color:#25342d">{escape(title)}</h1>
<p style="margin:0 0 26px;color:#7c8c70;font-size:14px;line-height:1.8">{escape(intro)}</p>
{body}
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:28px 0 18px"><tr><td style="border-radius:8px;background:#203d31;mso-padding-alt:16px 28px"><a href="{PAY_URL}" target="_blank" rel="noopener noreferrer" style="display:inline-block;padding:16px 28px;color:#fffffc;text-decoration:none;font-size:14px;font-weight:600;border:1px solid #203d31;border-radius:8px">Pay tickets <span aria-hidden="true">↗</span></a></td></tr></table>
<p style="margin:0;font-size:12px;line-height:1.8;color:#8a987e">Opens the City of Syracuse’s payment portal. Search for your plate or ticket number to review and pay.</p>
</td></tr><tr><td style="padding:22px 32px;border-top:1px solid #e4e8e1;background:#f8faf3;color:#8a987e;font-size:11px;line-height:1.8">
Prepared {escape(stamp)} {escape(TIMEZONE_LABEL)}.<br>Balances reflect the latest successful ticket check; confirm the final amount in the city portal.<br>Sent for a vehicle tracked in Curbwatch. Ask your garage administrator to update its email address or notification settings.
</td></tr></table><p style="margin:20px 0 0;color:#9aa48e;font-size:11px">Your parking, a little clearer.</p></td></tr></table></body></html>'''


def metric(total, label, caption=""):
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#edf3e3;border:1px solid #dce7ce;border-radius:10px;margin:0 0 24px"><tr><td style="padding:22px 24px"><p style="margin:0 0 8px;color:#70875b;font-size:12px">{escape(label)}</p><p style="margin:0;color:#294632;font-size:38px;font-weight:550;letter-spacing:-1px">{money(total)}</p>{f'<p style="margin:10px 0 0;color:#7c8c70;font-size:12px">{escape(caption)}</p>' if caption else ""}</td></tr></table>"""


def new_ticket_email(ticket, at):
    issued, age = issued_details(ticket, at)
    total = sum(
        ticket.get(key, 0) or 0
        for key in ("fine_cents", "surcharge_cents", "additional_fees_cents")
    )
    label = vehicle_label(ticket)
    rows = [
        ("Vehicle", label),
        ("Ticket number", ticket["ticket_number"]),
        ("Location", ticket["location_name"]),
        ("Violation", ticket["description"]),
        ("Issued", f"{issued} · {age}"),
        ("Total ticket charges", money(total)),
        ("Current status", ticket["status"]),
    ]
    body = metric(
        ticket["balance_cents"],
        "Outstanding on this ticket",
        "No balance due" if ticket["balance_cents"] <= 0 else "",
    )
    body += (
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%">'
        + "".join(detail_row(*row) for row in rows)
        + "</table>"
    )
    subject = (
        f"New parking ticket · {plate_label(ticket)} · {money(ticket['balance_cents'])} outstanding"
    )
    text = f"A new ticket was recorded for {label}.\n\nOutstanding on this ticket: {money(ticket['balance_cents'])}\n"
    text += "\n".join(f"{key}: {value}" for key, value in rows)
    text += f"\n\nPay tickets: {PAY_URL}\nBalances reflect our latest successful check. Confirm the final amount in the city portal."
    return EmailContent(
        subject,
        text,
        frame(
            f"Ticket {ticket['ticket_number']}: {money(ticket['balance_cents'])} outstanding.",
            "KEEPING AN EYE ON YOUR CAR",
            "A new ticket, on your radar.",
            f"We found a new ticket for {label}. Here’s the detail, all in one place.",
            body,
            at,
        ),
    )


def monthly_email(tickets, period, at):
    month = datetime.strptime(period, "%Y-%m").strftime("%B %Y")
    total = sum(ticket["balance_cents"] for ticket in tickets)
    grouped = OrderedDict()
    for ticket in tickets:
        grouped.setdefault(ticket["car_id"], []).append(ticket)
    body = metric(
        total,
        "Total outstanding balance",
        f"{len(tickets)} outstanding ticket{'s' if len(tickets) != 1 else ''} across {len(grouped)} vehicle{'s' if len(grouped) != 1 else ''}",
    )
    text = f"{month} outstanding-ticket report\nAs of {at.astimezone(NY).strftime('%b %-d, %Y')}\nTotal outstanding: {money(total)}\n"
    for records in grouped.values():
        label = vehicle_label(records[0])
        body += f'<h2 style="margin:28px 0 12px;color:#25342d;font-size:17px;font-weight:600">{escape(label)}</h2>'
        text += f"\n{label}\n"
        for ticket in records:
            issued, age = issued_details(ticket, at)
            body += f"""<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-top:1px solid #e4e8e1"><tr><td style="padding:17px 0 5px;color:#25342d;font-size:14px;font-weight:600;overflow-wrap:anywhere">Ticket {escape(str(ticket["ticket_number"]))}</td><td style="padding:17px 0 5px;text-align:right;color:#294632;font-size:17px;font-weight:600;white-space:nowrap">{money(ticket["balance_cents"])}</td></tr><tr><td colspan="2" style="padding:0 0 8px;color:#7c8c70;font-size:12px;line-height:1.7">{escape(str(ticket["location_name"]))}<br><strong style="font-weight:600;color:#617d48">{escape(age)}</strong> · {escape(issued)}</td></tr></table>"""
            text += f"  Ticket {ticket['ticket_number']}: {money(ticket['balance_cents'])}\n  {ticket['location_name']}\n  {issued} · {age}\n"
    text += f"\nPay tickets: {PAY_URL}\nIncludes all currently outstanding tickets, regardless of issue month. Balances reflect our latest successful check; confirm the final amount in the city portal."
    body += '<p style="margin:22px 0 0;color:#8a987e;font-size:12px;line-height:1.7">This report includes all currently outstanding tickets, including tickets issued before this month.</p>'
    return EmailContent(
        f"Your {month} parking summary · {money(total)} outstanding",
        text,
        frame(
            f"{money(total)} outstanding across {len(tickets)} tickets.",
            month.upper() + " · YOUR PARKING SUMMARY",
            "A clear view of what’s due.",
            "A monthly check-in on your outstanding tickets, with each balance and how long it’s been since issue.",
            body,
            at,
        ),
    )


def sample_tickets(at):
    from datetime import timedelta

    base = dict(
        car_id=1,
        car_name="Everyday car",
        plate="DEMO123",
        plate_state="NY",
        time_source="ticket_issue_date",
        location_name="WAVERLY AVE",
        description="Parking violation",
        fine_cents=3500,
        surcharge_cents=0,
        additional_fees_cents=0,
        status="Outstanding",
    )
    return [
        {
            **base,
            "ticket_number": "SAMPLE-1042",
            "issued_at": (at - timedelta(days=12)).isoformat(),
            "balance_cents": 3500,
        },
        {
            **base,
            "ticket_number": "SAMPLE-1028",
            "issued_at": (at - timedelta(days=43)).isoformat(),
            "balance_cents": 6500,
            "location_name": "MARSHALL ST",
        },
    ]


def test_email(at):
    body = metric(
        0, "SMTP delivery is connected", "This is a test email. No payment is due for this message."
    )
    return EmailContent(
        "Your Curbwatch email is connected",
        f"Curbwatch SMTP test. No payment is due. Payment portal: {PAY_URL}",
        frame(
            "Your Curbwatch email is connected.",
            "A QUICK CONNECTION CHECK",
            "You’re connected.",
            "New ticket alerts and monthly summaries will use this same look. This test contains no real ticket or vehicle details.",
            body,
            at,
        ),
    )
