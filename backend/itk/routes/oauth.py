"""OAuth connect + callback for every provider in `itk.services.oauth.PROVIDERS`.

    GET /api/auth/{provider}?token=<onboarding token>   -> redirect to the provider
    GET /api/auth/{provider}/callback?code=&state=      -> store tokens, back to onboarding

The `state` parameter is an HMAC-signed, ten-minute token carrying the user ID and the
onboarding token, so the callback needs no server-side session.
"""

import logging
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.config import get_settings
from itk.db import get_db
from itk.models import User
from itk.security import generate_random_token, make_signed_value, verify_signed_value
from itk.services.oauth import PROVIDERS, OAuthProvider, exchange_code, store_token

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["oauth"])

STATE_TTL_SECONDS = 600


def _provider(name: str) -> OAuthProvider:
    provider = PROVIDERS.get(name)
    if provider is None:
        raise HTTPException(status_code=404, detail="Unknown OAuth provider")
    return provider


def _back_to_onboarding(onboarding_token: str, provider: str, status: str) -> RedirectResponse:
    query = urlencode({"token": onboarding_token, provider: status})
    return RedirectResponse(f"{get_settings().app_url.rstrip('/')}/onboarding?{query}")


@router.get("/{provider_name}")
def start_oauth(provider_name: str, token: str = Query(...), db: Session = Depends(get_db)) -> RedirectResponse:
    provider = _provider(provider_name)
    settings = get_settings()
    if not provider.is_configured(settings):
        raise HTTPException(status_code=503, detail=f"{provider_name.title()} OAuth is not configured")

    user = db.scalar(select(User).where(User.onboarding_token == token))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    state = make_signed_value(f"{user.id}:{token}:{generate_random_token(8)}", ttl_seconds=STATE_TTL_SECONDS)
    return RedirectResponse(provider.authorization_redirect(settings, state))


@router.get("/{provider_name}/callback")
def finish_oauth(
    provider_name: str,
    state: str = Query(...),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    provider = _provider(provider_name)
    decoded = verify_signed_value(state)
    if not decoded:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    try:
        user_id_raw, onboarding_token, _nonce = decoded.split(":", 2)
        user_id = UUID(user_id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state payload") from exc

    if error or not code:
        # The user clicked "Cancel" on the consent screen.
        return _back_to_onboarding(onboarding_token, provider_name, "denied")
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        payload = exchange_code(provider, code)
    except httpx.HTTPError:
        log.warning("%s code exchange failed for user %s", provider_name, user_id)
        return _back_to_onboarding(onboarding_token, provider_name, "error")

    store_token(
        db,
        user_id=user_id,
        provider=provider_name,
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_in=payload.get("expires_in"),
    )
    return _back_to_onboarding(onboarding_token, provider_name, "connected")
