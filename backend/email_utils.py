import logging
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .config import settings

log = logging.getLogger("cym.email")

# Seconds to wait for each stage of the SMTP conversation.  Fastmail
# on port 465 (implicit TLS) typically responds in <2s; if Railway or
# the network is blocking the port, we'll find out quickly rather than
# hanging for 60s (the aiosmtplib default).
SMTP_TIMEOUT = 15


async def send_confirmation_email(
    to_email: str,
    display_id: str,
    lookup_token: str,
    title: str,
    ticket_type: str,
    app: str,
    urgency: str,
):
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        log.warning("SMTP not configured — skipping email to %s", to_email)
        return

    ticket_url = f"{settings.BASE_URL}/ticket/{lookup_token}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your ticket {display_id} has been submitted"
    msg["From"] = settings.FROM_EMAIL
    msg["To"] = to_email

    text_body = f"""Hi,

Your ticket has been submitted successfully.

Ticket ID:  {display_id}
Title:      {title}
Type:       {ticket_type}
App:        {app}
Urgency:    {urgency}

Track your ticket status:
{ticket_url}

Thanks for the feedback!
"""

    html_body = f"""<html><body style="font-family:sans-serif;color:#1a1a18;max-width:560px;margin:32px auto;padding:0 16px">
<h2 style="color:#2563eb">Ticket submitted ✓</h2>
<p>Your ticket has been submitted successfully.</p>
<table style="border-collapse:collapse;margin:16px 0;font-size:14px">
  <tr><td style="padding:4px 20px 4px 0;font-weight:600;color:#6b6b65">Ticket ID</td><td><strong>{display_id}</strong></td></tr>
  <tr><td style="padding:4px 20px 4px 0;font-weight:600;color:#6b6b65">Title</td><td>{title}</td></tr>
  <tr><td style="padding:4px 20px 4px 0;font-weight:600;color:#6b6b65">Type</td><td>{ticket_type}</td></tr>
  <tr><td style="padding:4px 20px 4px 0;font-weight:600;color:#6b6b65">App</td><td>{app}</td></tr>
  <tr><td style="padding:4px 20px 4px 0;font-weight:600;color:#6b6b65">Urgency</td><td>{urgency}</td></tr>
</table>
<p><a href="{ticket_url}" style="color:#2563eb">Track your ticket status →</a></p>
<p style="color:#6b6b65;font-size:13px">Thanks for the feedback!</p>
</body></html>"""

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    log.info("Sending confirmation for %s to %s via %s:%s",
             display_id, to_email, settings.SMTP_HOST, settings.SMTP_PORT)
    await aiosmtplib.send(
        msg,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        use_tls=True,
        timeout=SMTP_TIMEOUT,
    )
    log.info("Confirmation sent for %s", display_id)
