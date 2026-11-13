"""Inbound email replies (Resend inbound webhook)."""

import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from itk.config import get_settings
from itk.db import get_db
from itk.security import verify_svix_signature
from itk.services.reply_agent import process_inbound_reply

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _authorize(body: bytes, headers: dict[str, str | None]) -> None:
    """Accept either a Svix signature (secret starts with `whsec_`, as Resend issues them)
    or a shared secret in `X-Webhook-Secret`. Unsigned requests are only allowed outside
    production when no secret is configured."""
    settings = get_settings()
    secret = settings.resend_inbound_webhook_secret
    if not secret:
        if settings.is_production:
            raise HTTPException(status_code=503, detail="Inbound webhook secret is not configured")
        return

    if secret.startswith("whsec_"):
        ok = verify_svix_signature(
            secret, body, headers["svix-id"], headers["svix-timestamp"], headers["svix-signature"]
        )
    else:
        provided = headers["x-webhook-secret"] or ""
        ok = bool(provided) and hmac.compare_digest(provided, secret)
    if not ok:
        raise HTTPException(status_code=401, detail="Unauthorized webhook request")


@router.post("/email-reply")
async def handle_email_reply(
    request: Request,
    svix_id: str | None = Header(default=None),
    svix_timestamp: str | None = Header(default=None),
    svix_signature: str | None = Header(default=None),
    x_webhook_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    body = await request.body()
    _authorize(
        body,
        {
            "svix-id": svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": svix_signature,
            "x-webhook-secret": x_webhook_secret,
        },
    )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload")
    return process_inbound_reply(db, payload)
