"""Signing, CSRF, webhook verification and other request-level security helpers."""

import base64
import hashlib
import hmac
import secrets
import time

import bleach
from fastapi import Header, HTTPException, Request
from slowapi import Limiter

from itk.config import get_settings

CSRF_COOKIE_NAME = "itk_csrf"
CSRF_HEADER_NAME = "x-csrf-token"

ONE_WEEK = 60 * 60 * 24 * 7
ONE_YEAR = 60 * 60 * 24 * 365


def generate_random_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def _sign(payload: str) -> str:
    key = get_settings().session_secret.encode("utf-8")
    digest = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_signed_value(value: str, ttl_seconds: int = ONE_WEEK) -> str:
    """Return `value.expiry.signature`, an HMAC-signed, expiring token."""
    payload = f"{value}.{int(time.time()) + ttl_seconds}"
    return f"{payload}.{_sign(payload)}"


def verify_signed_value(signed_value: str) -> str | None:
    """Return the original value if the signature is valid and unexpired, else None."""
    try:
        value, expires_at_raw, signature = signed_value.rsplit(".", 2)
        expires_at = int(expires_at_raw)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(f"{value}.{expires_at_raw}")):
        return None
    if expires_at < int(time.time()):
        return None
    return value


def ensure_csrf(request: Request) -> None:
    """Double-submit cookie check for state-changing public endpoints."""
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def sanitize_text(value: str) -> str:
    """Strip any HTML from user-provided text."""
    cleaned: str = bleach.clean(value, tags=[], attributes={}, strip=True)
    return cleaned


def client_ip(request: Request) -> str:
    """Rate-limit key. Behind Vercel/the Next.js proxy the socket peer is the proxy,
    so prefer the first hop recorded in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first_hop = forwarded.split(",", 1)[0].strip()
    if first_hop:
        return first_hop
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip)


def require_cron_secret(
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None),
) -> None:
    """Guard internal pipeline endpoints.

    Accepts `X-Cron-Secret: <secret>` or `Authorization: Bearer <secret>` (the header Vercel
    Cron sends when `CRON_SECRET` is configured on the project).
    """
    expected = get_settings().api_cron_secret
    provided = x_cron_secret
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


SVIX_TOLERANCE_SECONDS = 5 * 60


def verify_svix_signature(
    secret: str,
    body: bytes,
    msg_id: str | None,
    timestamp: str | None,
    signature_header: str | None,
    now: float | None = None,
) -> bool:
    """Verify a Svix-signed webhook (the scheme Resend uses for its webhooks)."""
    if not (msg_id and timestamp and signature_header):
        return False
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs((now or time.time()) - sent_at) > SVIX_TOLERANCE_SECONDS:
        return False

    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed_content = f"{msg_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode()

    for candidate in signature_header.split():
        version, _, signature = candidate.partition(",")
        if version == "v1" and hmac.compare_digest(signature, expected):
            return True
    return False
