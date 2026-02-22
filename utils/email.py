"""Send email via Resend."""
import os
import logging
import resend

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Send email via Resend. Requires RESEND_API_KEY and FROM_EMAIL."""
    api_key = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("FROM_EMAIL", "Sous Chef <onboarding@resend.dev>")
    if not api_key:
        logger.warning("RESEND_API_KEY not set; skipping send_email.")
        return False
    try:
        resend.api_key = api_key
        params = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "text": body_text,
        }
        if body_html:
            params["html"] = body_html
        resend.Emails.send(params)
        logger.info(f"Email sent to {to_email} ({subject})")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
