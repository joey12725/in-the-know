"""Outbound email. Resend in production; a local `.outbox/` folder everywhere else."""

import logging
import re
from datetime import datetime

import httpx

from itk.config import get_settings

log = logging.getLogger(__name__)

RESEND_EMAILS_URL = "https://api.resend.com/emails"


def extract_address(value: str) -> str:
    """`"ITK <hello@example.com>"` -> `hello@example.com`."""
    match = re.search(r"<([^>]+)>", value)
    return (match.group(1) if match else value).strip()


def _write_to_outbox(to: str, subject: str, html: str) -> None:
    outbox = get_settings().email_outbox_dir
    outbox.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", f"{to}-{subject}".lower()).strip("-")[:80]
    path = outbox / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{slug}.html"
    path.write_text(html, encoding="utf-8")
    log.info("Email to %s written to %s", to, path)


def send_email(
    to: str,
    subject: str,
    html: str,
    *,
    reply_to: str | None = None,
    headers: dict[str, str] | None = None,
) -> bool:
    """Send one email. Returns True if it was delivered (or written to the dev outbox)."""
    settings = get_settings()
    if not settings.resend_api_key:
        if settings.is_production:
            log.error("RESEND_API_KEY is not set; dropping email to %s", to)
            return False
        _write_to_outbox(to, subject, html)
        return True

    payload: dict[str, object] = {"from": settings.resend_from_email, "to": [to], "subject": subject, "html": html}
    if reply_to:
        payload["reply_to"] = [reply_to]
    if headers:
        payload["headers"] = headers
    response = httpx.post(
        RESEND_EMAILS_URL,
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json=payload,
        timeout=20,
    )
    response.raise_for_status()
    return True
