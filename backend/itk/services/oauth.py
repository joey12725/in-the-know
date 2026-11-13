"""OAuth providers, encrypted token storage, and refresh-on-read.

Google Calendar and Spotify share one code path. Adding another provider means adding an
`OAuthProvider` entry to `PROVIDERS`; the routes in `itk/routes/oauth.py` pick it up by name.
"""

import base64
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.config import Settings, get_settings
from itk.db import as_utc, utcnow
from itk.models import OAuthToken

log = logging.getLogger(__name__)

REFRESH_SKEW = timedelta(seconds=60)


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    authorize_url: str
    token_url: str
    scopes: str
    extra_authorize_params: dict[str, str] = field(default_factory=dict)

    def credentials(self, settings: Settings) -> tuple[str | None, str | None]:
        return (
            getattr(settings, f"{self.name}_client_id", None),
            getattr(settings, f"{self.name}_client_secret", None),
        )

    def is_configured(self, settings: Settings) -> bool:
        return all(self.credentials(settings))

    def callback_url(self, settings: Settings) -> str:
        return f"{settings.backend_api_url.rstrip('/')}/api/auth/{self.name}/callback"

    def authorization_redirect(self, settings: Settings, state: str) -> str:
        client_id, _ = self.credentials(settings)
        query = {
            "client_id": client_id or "",
            "redirect_uri": self.callback_url(settings),
            "response_type": "code",
            "scope": self.scopes,
            "state": state,
            **self.extra_authorize_params,
        }
        return f"{self.authorize_url}?{urlencode(query)}"


PROVIDERS: dict[str, OAuthProvider] = {
    "google": OAuthProvider(
        name="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes="https://www.googleapis.com/auth/calendar.readonly",
        # offline + consent guarantees a refresh token on every connect.
        extra_authorize_params={"access_type": "offline", "prompt": "consent"},
    ),
    "spotify": OAuthProvider(
        name="spotify",
        authorize_url="https://accounts.spotify.com/authorize",
        token_url="https://accounts.spotify.com/api/token",
        scopes="user-read-recently-played user-top-read",
        extra_authorize_params={"show_dialog": "true"},
    ),
}


class TokenCipher:
    """Fernet encryption keyed from TOKEN_ENCRYPTION_KEY (or SESSION_SECRET as a fallback)."""

    def __init__(self, secret_material: str) -> None:
        digest = hashlib.sha256(secret_material.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")


@lru_cache(maxsize=1)
def get_cipher() -> TokenCipher:
    settings = get_settings()
    return TokenCipher(settings.token_encryption_key or settings.session_secret)


def _decrypt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return get_cipher().decrypt(value)
    except InvalidToken:
        log.warning("Stored OAuth token could not be decrypted; was TOKEN_ENCRYPTION_KEY rotated?")
        return None


def exchange_code(provider: OAuthProvider, code: str) -> dict[str, Any]:
    settings = get_settings()
    client_id, client_secret = provider.credentials(settings)
    response = httpx.post(
        provider.token_url,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": provider.callback_url(settings),
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def store_token(
    db: Session,
    *,
    user_id: UUID,
    provider: str,
    access_token: str,
    refresh_token: str | None,
    expires_in: int | None,
) -> OAuthToken:
    """Insert or update the user's token row for `provider`, encrypting both tokens."""
    cipher = get_cipher()
    token = db.scalar(select(OAuthToken).where(OAuthToken.user_id == user_id, OAuthToken.provider == provider))
    if token is None:
        token = OAuthToken(user_id=user_id, provider=provider, access_token="")
        db.add(token)
    token.access_token = cipher.encrypt(access_token)
    # Providers often omit the refresh token on re-consent; keep the one we already have.
    if refresh_token:
        token.refresh_token = cipher.encrypt(refresh_token)
    token.expires_at = utcnow() + timedelta(seconds=expires_in) if expires_in else None
    db.commit()
    return token


def _is_expired(token: OAuthToken) -> bool:
    expires_at = as_utc(token.expires_at)
    return expires_at is not None and expires_at <= utcnow() + REFRESH_SKEW


def _refresh(db: Session, token: OAuthToken, provider: OAuthProvider) -> str | None:
    refresh_token = _decrypt(token.refresh_token)
    settings = get_settings()
    client_id, client_secret = provider.credentials(settings)
    if not refresh_token or not client_id or not client_secret:
        return None

    try:
        response = httpx.post(
            provider.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=20,
        )
    except httpx.HTTPError:
        log.warning("Token refresh request to %s failed", provider.name)
        return None
    if response.status_code >= 400:
        log.info("%s refresh rejected for user %s; they need to reconnect", provider.name, token.user_id)
        return None

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        return None
    store_token(
        db,
        user_id=token.user_id,
        provider=provider.name,
        access_token=access_token,
        refresh_token=payload.get("refresh_token"),
        expires_in=payload.get("expires_in"),
    )
    return str(access_token)


def get_access_token(db: Session, user_id: UUID, provider_name: str) -> str | None:
    """Return a usable access token for the user, refreshing it if it has expired.

    Returns None when the user never connected the provider or the refresh failed; callers
    treat that as "no context" rather than an error.
    """
    provider = PROVIDERS[provider_name]
    token = db.scalar(select(OAuthToken).where(OAuthToken.user_id == user_id, OAuthToken.provider == provider_name))
    if token is None:
        return None
    if _is_expired(token):
        return _refresh(db, token, provider)
    return _decrypt(token.access_token)
