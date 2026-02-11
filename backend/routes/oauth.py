from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from db.session import get_db
from models import OAuthToken, User
from services.token_crypto import cipher
from utils.security import make_signed_value, verify_signed_value

router = APIRouter(prefix="/api/auth", tags=["oauth"])


def _update_provider_token(
    db: Session,
    *,
    user_id,
    provider: str,
    access_token: str,
    refresh_token: str | None,
    expires_in: int | None,
) -> None:
    encrypted_access = cipher.encrypt(access_token)
    encrypted_refresh = cipher.encrypt(refresh_token) if refresh_token else None
    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in) if expires_in else None

    existing = db.scalar(select(OAuthToken).where(OAuthToken.user_id == user_id, OAuthToken.provider == provider))
    if existing:
        existing.access_token = encrypted_access
        existing.refresh_token = encrypted_refresh
        existing.expires_at = expires_at
    else:
        db.add(
            OAuthToken(
                user_id=user_id,
                provider=provider,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=expires_at,
            )
        )
    db.commit()


def _frontend_redirect(path: str) -> str:
    settings = get_settings()
    return f"{settings.app_url.rstrip('/')}{path}"


@router.get("/google")
def auth_google(token: str = Query(...), db: Session = Depends(get_db)) -> RedirectResponse:
    settings = get_settings()
    user = db.scalar(select(User).where(User.onboarding_token == token))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")

    state_raw = f"{user.id}:{token}:{secrets.token_urlsafe(8)}"
    signed_state = make_signed_value(state_raw, ttl_seconds=600)

    callback_url = f"{settings.backend_api_url.rstrip('/')}/api/auth/google/callback"
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/calendar.readonly",
            "access_type": "offline",
            "prompt": "consent",
            "state": signed_state,
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")


@router.get("/google/callback")
def auth_google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    decoded_state = verify_signed_value(state)
    if not decoded_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    try:
        user_id_raw, onboarding_token, _nonce = decoded_state.split(":", 2)
        user_id = UUID(user_id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state payload") from exc

    callback_url = f"{settings.backend_api_url.rstrip('/')}/api/auth/google/callback"
    with httpx.Client(timeout=20) as client:
        token_response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": callback_url,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_response.raise_for_status()
        payload = token_response.json()

    _update_provider_token(
        db,
        user_id=user_id,
        provider="google",
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_in=payload.get("expires_in"),
    )

    return RedirectResponse(_frontend_redirect(f"/onboarding?token={onboarding_token}&google=connected"))


@router.get("/spotify")
def auth_spotify(token: str = Query(...), db: Session = Depends(get_db)) -> RedirectResponse:
    settings = get_settings()
    user = db.scalar(select(User).where(User.onboarding_token == token))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise HTTPException(status_code=500, detail="Spotify OAuth is not configured")

    state_raw = f"{user.id}:{token}:{secrets.token_urlsafe(8)}"
    signed_state = make_signed_value(state_raw, ttl_seconds=600)

    callback_url = f"{settings.backend_api_url.rstrip('/')}/api/auth/spotify/callback"
    query = urlencode(
        {
            "client_id": settings.spotify_client_id,
            "response_type": "code",
            "redirect_uri": callback_url,
            "scope": "user-read-recently-played user-top-read",
            "state": signed_state,
            "show_dialog": "true",
        }
    )
    return RedirectResponse(f"https://accounts.spotify.com/authorize?{query}")


@router.get("/spotify/callback")
def auth_spotify_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    decoded_state = verify_signed_value(state)
    if not decoded_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    try:
        user_id_raw, onboarding_token, _nonce = decoded_state.split(":", 2)
        user_id = UUID(user_id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state payload") from exc

    callback_url = f"{settings.backend_api_url.rstrip('/')}/api/auth/spotify/callback"
    with httpx.Client(timeout=20) as client:
        token_response = client.post(
            "https://accounts.spotify.com/api/token",
            data={
                "code": code,
                "redirect_uri": callback_url,
                "grant_type": "authorization_code",
                "client_id": settings.spotify_client_id,
                "client_secret": settings.spotify_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_response.raise_for_status()
        payload = token_response.json()

    _update_provider_token(
        db,
        user_id=user_id,
        provider="spotify",
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_in=payload.get("expires_in"),
    )

    return RedirectResponse(_frontend_redirect(f"/onboarding?token={onboarding_token}&spotify=connected"))
