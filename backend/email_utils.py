import asyncio
import enum
import logging
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
