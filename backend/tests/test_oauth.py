from collections.abc import Callable
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.db import utcnow
from itk.models import OAuthToken, User
from itk.security import make_signed_value
from itk.services.oauth import get_access_token, get_cipher, store_token

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


@pytest.fixture
def user(db: Session) -> User:
    user = User(name="Devin Park", email="devin@example.com", address="2 Sample St", city="San Antonio",
                onboarding_token="onboard-token")  # fmt: skip
    db.add(user)
    db.commit()
    return user


def _state_for(user: User) -> str:
    return make_signed_value(f"{user.id}:{user.onboarding_token}:nonce", ttl_seconds=600)


@pytest.mark.parametrize(
    ("provider", "host", "expected"),
    [
        ("google", "accounts.google.com", {"access_type": "offline", "prompt": "consent"}),
        ("spotify", "accounts.spotify.com", {"scope": "user-read-recently-played user-top-read"}),
    ],
)
def test_start_redirects_to_provider_with_signed_state(
    client: TestClient, user: User, provider: str, host: str, expected: dict[str, str]
) -> None:
    response = client.get(f"/api/auth/{provider}", params={"token": user.onboarding_token}, follow_redirects=False)
    assert response.status_code == 307
    location = urlparse(response.headers["location"])
    query = {key: values[0] for key, values in parse_qs(location.query).items()}
    assert location.hostname == host
    assert query["redirect_uri"] == f"https://api.test/api/auth/{provider}/callback"
    assert query["client_id"] == f"{provider}-client-id"
    assert query["state"].startswith(f"{user.id}:{user.onboarding_token}:")
    assert expected.items() <= query.items()


def test_start_rejects_unknown_user_and_provider(client: TestClient, user: User) -> None:
    assert client.get("/api/auth/google", params={"token": "nope"}).status_code == 404
    assert client.get("/api/auth/myspace", params={"token": user.onboarding_token}).status_code == 404


def test_start_reports_unconfigured_provider(
    client: TestClient, user: User, override_settings: Callable[..., None]
) -> None:
    override_settings(SPOTIFY_CLIENT_SECRET=None)
    response = client.get("/api/auth/spotify", params={"token": user.onboarding_token})
    assert response.status_code == 503


@respx.mock
def test_callback_exchanges_code_and_stores_encrypted_tokens(client: TestClient, db: Session, user: User) -> None:
    token_route = respx.post(GOOGLE_TOKEN_URL).respond(
        json={"access_token": "ya29.access", "refresh_token": "1//refresh", "expires_in": 3600}
    )
    response = client.get(
        "/api/auth/google/callback", params={"code": "auth-code", "state": _state_for(user)}, follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"] == "https://app.test/onboarding?token=onboard-token&google=connected"
    sent = parse_qs(token_route.calls.last.request.content.decode())
    assert sent["code"] == ["auth-code"]
    assert sent["grant_type"] == ["authorization_code"]
    assert sent["redirect_uri"] == ["https://api.test/api/auth/google/callback"]

    stored = db.scalar(select(OAuthToken).where(OAuthToken.user_id == user.id))
    assert stored is not None and stored.provider == "google"
    assert "ya29" not in stored.access_token  # encrypted at rest
    assert get_cipher().decrypt(stored.access_token) == "ya29.access"
    assert stored.refresh_token and get_cipher().decrypt(stored.refresh_token) == "1//refresh"


def test_callback_rejects_forged_state(client: TestClient, user: User) -> None:
    forged = _state_for(user)[:-2] + "xx"
    response = client.get("/api/auth/google/callback", params={"code": "c", "state": forged})
    assert response.status_code == 400


def test_callback_handles_user_denial(client: TestClient, user: User) -> None:
    response = client.get(
        "/api/auth/spotify/callback",
        params={"error": "access_denied", "state": _state_for(user)},
        follow_redirects=False,
    )
    assert response.headers["location"].endswith("spotify=denied")


@respx.mock
def test_callback_handles_failed_exchange(client: TestClient, db: Session, user: User) -> None:
    respx.post(SPOTIFY_TOKEN_URL).respond(400, json={"error": "invalid_grant"})
    response = client.get(
        "/api/auth/spotify/callback", params={"code": "bad", "state": _state_for(user)}, follow_redirects=False
    )
    assert response.headers["location"].endswith("spotify=error")
    assert db.scalar(select(OAuthToken)) is None


def _expire(db: Session, user: User, provider: str) -> None:
    store_token(db, user_id=user.id, provider=provider, access_token="old", refresh_token="refresh-1", expires_in=60)
    token = db.scalar(select(OAuthToken).where(OAuthToken.provider == provider))
    assert token is not None
    token.expires_at = utcnow() - timedelta(minutes=5)
    db.commit()


def test_fresh_token_is_returned_without_refresh(db: Session, user: User) -> None:
    store_token(db, user_id=user.id, provider="spotify", access_token="live", refresh_token=None, expires_in=3600)
    with respx.mock:  # any HTTP call would fail the test
        assert get_access_token(db, user.id, "spotify") == "live"
    assert get_access_token(db, user.id, "google") is None


@respx.mock
def test_expired_token_is_refreshed_and_refresh_token_preserved(db: Session, user: User) -> None:
    _expire(db, user, "spotify")
    route = respx.post(SPOTIFY_TOKEN_URL).respond(json={"access_token": "new", "expires_in": 3600})

    assert get_access_token(db, user.id, "spotify") == "new"
    assert parse_qs(route.calls.last.request.content.decode())["grant_type"] == ["refresh_token"]
    token = db.scalar(select(OAuthToken))
    assert token is not None and token.refresh_token
    assert get_cipher().decrypt(token.refresh_token) == "refresh-1"
    assert get_access_token(db, user.id, "spotify") == "new"  # now fresh, no second call
    assert route.call_count == 1


@respx.mock
def test_failed_refresh_means_no_context(db: Session, user: User) -> None:
    _expire(db, user, "google")
    respx.post(GOOGLE_TOKEN_URL).mock(side_effect=httpx.ConnectError("down"))
    assert get_access_token(db, user.id, "google") is None
