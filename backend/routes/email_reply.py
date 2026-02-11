from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from core.config import get_settings
from db.session import get_db
from services.reply_agent import process_inbound_reply_payload

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _validate_inbound_secret(provided: str | None) -> None:
    settings = get_settings()
    expected = settings.resend_inbound_webhook_secret
    if not expected:
        return
    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="Unauthorized webhook request")


@router.post("/email-reply")
async def handle_email_reply_webhook(
    request: Request,
    x_resend_signature: str | None = Header(default=None),
    x_webhook_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    # Resend can send signatures; we allow either explicit webhook secret or signature passthrough
    # for lightweight verification in this service.
    _validate_inbound_secret(x_webhook_secret or x_resend_signature)

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc

    result = process_inbound_reply_payload(db, payload if isinstance(payload, dict) else {})

    from_email = get_settings().resend_from_email.lower()
    if "resend.dev" in from_email:
        result["inbound_note"] = (
            "Resend inbound replies require a verified custom domain inbox. "
            "onboarding@resend.dev is fine for outbound testing but not inbound production routing."
        )

    return result
