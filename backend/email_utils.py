import asyncio
import enum
import logging
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


async def send_status_email(
    to_email: str,
    display_id: str,
    lookup_token: str,
    title: str,
    status: str,
    clarifying_notes: Optional[str],
):
    """Notify the submitter when a ticket transitions to a closed status
    (Done or Won't Fix). The caller is responsible for gating this on
    closed_notified_at so reopen → re-close doesn't re-email."""
    if not settings.RESEND_API_KEY or not settings.FROM_EMAIL:
        log.warning("Email not configured — skipping status email for %s to %s", display_id, to_email)
        return

    status = _display(status)
    ticket_url = f"{settings.BASE_URL}/ticket/{lookup_token}"
    notes_section_text = f"\n\nResolution notes:\n{clarifying_notes}\n" if clarifying_notes else ""
    notes_section_html = (
        f'<p style="color:#1a1a18;white-space:pre-wrap;background:#f6f6f3;'
        f'padding:12px 16px;border-radius:6px;font-size:14px">{clarifying_notes}</p>'
        if clarifying_notes else ""
    )

    text_body = f"""Hi,

Your ticket {display_id} ("{title}") has been marked {status}.{notes_section_text}

View the full ticket: {ticket_url}
"""
    html_body = f"""<html><body style="font-family:sans-serif;color:#1a1a18;max-width:560px;margin:32px auto;padding:0 16px">
<h2 style="color:#2563eb">Ticket {display_id}: {status}</h2>
<p>Your request <strong>"{title}"</strong> has been marked <strong>{status}</strong>.</p>
{notes_section_html}
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


async def send_question_email(
    to_email: str,
    display_id: str,
    lookup_token: str,
    title: str,
    question: str,
):
    """Admin "ask the submitter a question" flow. Replies go to REPLY_TO
    (the configured Fastmail inbox) — manual threading at current volume."""
    if not settings.RESEND_API_KEY or not settings.FROM_EMAIL:
        log.warning("Email not configured — skipping question email for %s to %s", display_id, to_email)
        return

    ticket_url = f"{settings.BASE_URL}/ticket/{lookup_token}"

    text_body = f"""Hi,

We have a question about your ticket {display_id} ("{title}"):

{question}

You can reply directly to this email, or view the ticket here:
{ticket_url}
"""
    html_body = f"""<html><body style="font-family:sans-serif;color:#1a1a18;max-width:560px;margin:32px auto;padding:0 16px">
<h2 style="color:#2563eb">Question about ticket {display_id}</h2>
<p>We have a question about your request <strong>"{title}"</strong>:</p>
<blockquote style="margin:16px 0;padding:12px 16px;border-left:4px solid #2563eb;background:#f6f6f3;white-space:pre-wrap;font-size:14px">{question}</blockquote>
<p style="color:#6b6b65;font-size:13px">Reply directly to this email, or <a href="{ticket_url}" style="color:#2563eb">view the ticket</a>.</p>
</body></html>"""

    payload = {
        "from": _from_header(),
        "to": [to_email],
        "subject": f"Question about your ticket {display_id}",
        "html": html_body,
        "text": text_body,
    }
    if settings.REPLY_TO:
        payload["reply_to"] = settings.REPLY_TO

    await _send_via_resend(payload, display_id, "question email")
