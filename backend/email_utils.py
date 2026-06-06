import asyncio
import enum
import html as html_lib
import logging
from datetime import datetime
from typing import Optional
import resend
from .config import settings

log = logging.getLogger("cym.email")

# Resend's Python SDK is synchronous — run the blocking call in a thread
# so we don't block the event loop. The send itself is ~200-400ms.
SEND_TIMEOUT_SECONDS = 15


def _display(value):
    """Coerce SQLAlchemy/Python enum values to their string for templating.
    In Python 3.11+ str(SomeEnum.member) returns "SomeEnum.member" rather
    than the member's value, which looks terrible in a user-facing email.
    """
    if isinstance(value, enum.Enum):
        return value.value
    return value


async def send_confirmation_email(
    to_email: str,
    display_id: str,
    lookup_token: str,
    title: str,
    ticket_type: str,
    app_label: str,
    urgency: str,
):
    if not settings.RESEND_API_KEY:
        log.warning("RESEND_API_KEY not set — skipping email to %s", to_email)
        return
    if not settings.FROM_EMAIL:
        log.warning("FROM_EMAIL not set — skipping email to %s", to_email)
        return

    ticket_type = _display(ticket_type)
    urgency = _display(urgency)

    ticket_url = f"{settings.BASE_URL}/ticket/{lookup_token}"

    text_body = f"""Hi,

Your ticket has been received.

Ticket ID:  {display_id}
Title:      {title}
Type:       {ticket_type}
App:        {app_label}
Urgency:    {urgency}

Track your ticket status:
{ticket_url}

Thanks for reaching out!
"""

    html_body = f"""<html><body style="font-family:sans-serif;color:#1a1a18;max-width:560px;margin:32px auto;padding:0 16px">
<h2 style="color:#2563eb">Ticket received &#10003;</h2>
<table style="border-collapse:collapse;margin:16px 0;font-size:14px">
  <tr><td style="padding:4px 20px 4px 0;font-weight:600;color:#6b6b65">Ticket ID</td><td><strong>{display_id}</strong></td></tr>
  <tr><td style="padding:4px 20px 4px 0;font-weight:600;color:#6b6b65">Title</td><td>{title}</td></tr>
  <tr><td style="padding:4px 20px 4px 0;font-weight:600;color:#6b6b65">Type</td><td>{ticket_type}</td></tr>
  <tr><td style="padding:4px 20px 4px 0;font-weight:600;color:#6b6b65">App</td><td>{app_label}</td></tr>
  <tr><td style="padding:4px 20px 4px 0;font-weight:600;color:#6b6b65">Urgency</td><td>{urgency}</td></tr>
</table>
<p><a href="{ticket_url}" style="color:#2563eb">Track your ticket status &rarr;</a></p>
<p style="color:#6b6b65;font-size:13px">Thanks for reaching out!</p>
</body></html>"""

    # Build the From header. When FROM_NAME is set, include a display
    # name so clients render "Could You Make <tickets@...>".
    if settings.FROM_NAME:
        from_header = f"{settings.FROM_NAME} <{settings.FROM_EMAIL}>"
    else:
        from_header = settings.FROM_EMAIL

    payload = {
        "from": from_header,
        "to": [to_email],
        "subject": f"Your ticket {display_id} has been received",
        "html": html_body,
        "text": text_body,
    }
    if settings.REPLY_TO:
        payload["reply_to"] = settings.REPLY_TO

    resend.api_key = settings.RESEND_API_KEY

    log.info("Sending confirmation for %s to %s via Resend", display_id, to_email)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(resend.Emails.send, payload),
            timeout=SEND_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("Resend send timed out after %ds for %s", SEND_TIMEOUT_SECONDS, display_id)
        raise

    msg_id = result.get("id") if isinstance(result, dict) else None
    if msg_id:
        log.info("Confirmation sent for %s (resend id=%s)", display_id, msg_id)
    else:
        log.error("Unexpected Resend response for %s: %r", display_id, result)


def _from_header() -> str:
    if settings.FROM_NAME:
        return f"{settings.FROM_NAME} <{settings.FROM_EMAIL}>"
    return settings.FROM_EMAIL


async def _send_via_resend(payload: dict, display_id: str, kind: str) -> None:
    resend.api_key = settings.RESEND_API_KEY
    log.info("Sending %s for %s via Resend", kind, display_id)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(resend.Emails.send, payload),
            timeout=SEND_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("Resend %s send timed out after %ds for %s", kind, SEND_TIMEOUT_SECONDS, display_id)
        raise

    msg_id = result.get("id") if isinstance(result, dict) else None
    if msg_id:
        log.info("%s sent for %s (resend id=%s)", kind.capitalize(), display_id, msg_id)
    else:
        log.error("Unexpected Resend response for %s %s: %r", kind, display_id, result)


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC")


async def send_status_email(
    to_email: str,
    display_id: str,
    lookup_token: str,
    title: str,
    status: str,
    description: str,
    submitted_at: datetime,
    thread: list[dict],
):
    """Notify the submitter when a ticket transitions to a closed status
    (Done or Won't Fix). The caller is responsible for gating this on
    closed_notified_at so reopen → re-close doesn't re-email.

    The email body reflects what the submitter actually saw during the
    ticket's life: their original submission plus the admin↔submitter
    message thread, in chronological order. Internal fields
    (`clarifying_notes`, AI drafts, level_of_effort, admin_priority)
    are deliberately NOT included — they're triage context, not
    customer-facing resolution context.

    `thread` is a list of `{"direction": "admin"|"submitter", "body": str,
    "created_at": datetime}` dicts. Caller loads it from ticket_messages
    inside the request handler — we don't open a new DB session inside
    the email send.
    """
    if not settings.RESEND_API_KEY or not settings.FROM_EMAIL:
        log.warning("Email not configured — skipping status email for %s to %s", display_id, to_email)
        return

    status = _display(status)
    ticket_url = f"{settings.BASE_URL}/ticket/{lookup_token}"

    # -- text body --------------------------------------------------------
    text_lines = [
        "Hi,",
        "",
        f'Your ticket {display_id} ("{title}") has been marked {status}.',
        "",
        "Here is the conversation history for your reference:",
        "",
        f"You · Original submission · {_fmt_dt(submitted_at)}",
        description.strip(),
    ]
    for msg in thread:
        sender = "Erik" if msg["direction"] == "admin" else "You"
        text_lines.extend([
            "",
            f"{sender} · {_fmt_dt(msg['created_at'])}",
            (msg["body"] or "").strip(),
        ])
    text_lines.extend([
        "",
        f"View the full ticket: {ticket_url}",
        "",
    ])
    text_body = "\n".join(text_lines)

    # -- html body --------------------------------------------------------
    def _entry_html(sender: str, ts: datetime, body: str, is_admin: bool, *, marker: str = "") -> str:
        bg = "#e8f0fe" if is_admin else "#f6f6f3"
        border = "#2563eb" if is_admin else "#6b6b65"
        meta = f"{html_lib.escape(sender)}"
        if marker:
            meta += f" · {html_lib.escape(marker)}"
        meta += f" · {_fmt_dt(ts)}"
        return (
            f'<div style="background:{bg};border-left:3px solid {border};'
            f'padding:10px 14px;border-radius:4px;margin-bottom:8px;font-size:14px">'
            f'<div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;'
            f'color:#6b6b65;margin-bottom:4px">{meta}</div>'
            f'<div style="white-space:pre-wrap">{html_lib.escape(body or "")}</div>'
            f'</div>'
        )

    thread_html = _entry_html(
        "You", submitted_at, description, is_admin=False, marker="Original submission"
    )
    for msg in thread:
        thread_html += _entry_html(
            "Erik" if msg["direction"] == "admin" else "You",
            msg["created_at"],
            msg["body"],
            is_admin=(msg["direction"] == "admin"),
        )

    html_body = f"""<html><body style="font-family:sans-serif;color:#1a1a18;max-width:560px;margin:32px auto;padding:0 16px">
<h2 style="color:#2563eb">Ticket {display_id}: {status}</h2>
<p>Your request <strong>"{html_lib.escape(title)}"</strong> has been marked <strong>{status}</strong>.</p>
<p style="color:#6b6b65;font-size:13px">For your reference, the conversation:</p>
{thread_html}
<p><a href="{ticket_url}" style="color:#2563eb">View the full ticket &rarr;</a></p>
</body></html>"""

    payload = {
        "from": _from_header(),
        "to": [to_email],
        "subject": f"Ticket {display_id}: {status}",
        "html": html_body,
        "text": text_body,
    }
    if settings.REPLY_TO:
        payload["reply_to"] = settings.REPLY_TO

    await _send_via_resend(payload, display_id, "status email")


async def send_message_email(
    to_email: str,
    display_id: str,
    lookup_token: str,
    title: str,
    message_body: str,
):
    """Notify the submitter that the admin posted a message on their ticket.
    The email surfaces the message inline so the submitter can read it
    without clicking, then directs them to the in-app reply page.
    Replies happen in CYM, not via email reply — REPLY_TO is preserved for
    submitters who reply anyway, but the canonical channel is the link."""
    if not settings.RESEND_API_KEY or not settings.FROM_EMAIL:
        log.warning("Email not configured — skipping message email for %s to %s", display_id, to_email)
        return

    reply_url = f"{settings.BASE_URL}/ticket/{lookup_token}"

    text_body = f"""Hi,

We have a message for you about your ticket {display_id} ("{title}"):

{message_body}

Reply in CYM (this keeps the conversation attached to your ticket):
{reply_url}
"""
    html_body = f"""<html><body style="font-family:sans-serif;color:#1a1a18;max-width:560px;margin:32px auto;padding:0 16px">
<h2 style="color:#2563eb">New message on ticket {display_id}</h2>
<p>We have a message for you about your request <strong>"{title}"</strong>:</p>
<blockquote style="margin:16px 0;padding:12px 16px;border-left:4px solid #2563eb;background:#f6f6f3;white-space:pre-wrap;font-size:14px">{message_body}</blockquote>
<p><a href="{reply_url}" style="display:inline-block;background:#2563eb;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none;font-weight:600">View &amp; reply &rarr;</a></p>
<p style="color:#6b6b65;font-size:13px">Replying in CYM keeps the conversation attached to your ticket — much easier for both of us to keep track than email back-and-forth.</p>
</body></html>"""

    payload = {
        "from": _from_header(),
        "to": [to_email],
        "subject": f"New message on your ticket {display_id}",
        "html": html_body,
        "text": text_body,
    }
    if settings.REPLY_TO:
        payload["reply_to"] = settings.REPLY_TO

    await _send_via_resend(payload, display_id, "message email")
