from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from core.config import get_settings

CSRF_COOKIE_NAME = "itk_csrf"
CSRF_HEADER_NAME = "x-csrf-token"
SESSION_COOKIE_NAME = "itk_session"


def generate_random_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def make_signed_value(value: str, ttl_seconds: int = 60 * 60 * 24 * 7) -> str:
    settings = get_settings()
    expires_at = int((datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds)).timestamp())
    payload = f"{value}.{expires_at}"
    digest = hmac.new(settings.session_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return f"{payload}.{signature}"


def verify_signed_value(signed_value: str) -> str | None:
    settings = get_settings()
    try:
        value, expires_at_raw, signature = signed_value.rsplit(".", 2)
        payload = f"{value}.{expires_at_raw}"
        expected_digest = hmac.new(settings.session_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
        expected_signature = base64.urlsafe_b64encode(expected_digest).decode("utf-8").rstrip("=")
        if not hmac.compare_digest(signature, expected_signature):
            return None

        if int(expires_at_raw) < int(datetime.now(tz=timezone.utc).timestamp()):
            return None
        return value
    except ValueError:
        return None


def ensure_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
