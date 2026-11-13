import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

# Configure before anything imports itk (the app reads settings at import time).
_TMP = Path(tempfile.mkdtemp(prefix="itk-tests-"))
TEST_ENV = {
    "ENVIRONMENT": "test",
    # SQLite by default; set TEST_DATABASE_URL to run the suite against Postgres instead.
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}"),
    "SESSION_SECRET": "test-session-secret",
    "API_CRON_SECRET": "test-cron-secret",
    "TOKEN_ENCRYPTION_KEY": "test-token-key",
    "EMAIL_OUTBOX_DIR": str(_TMP / "outbox"),
    "NEXT_PUBLIC_APP_URL": "https://app.test",
    "BACKEND_API_URL": "https://api.test",
    "GOOGLE_CLIENT_ID": "google-client-id",
    "GOOGLE_CLIENT_SECRET": "google-client-secret",
    "SPOTIFY_CLIENT_ID": "spotify-client-id",
    "SPOTIFY_CLIENT_SECRET": "spotify-client-secret",
    "RESEND_REPLY_TO_EMAIL": "reply@itk.test",
    "RATE_LIMIT_SIGNUP": "1000/minute",
}
os.environ.update(TEST_ENV)
for key in ("OPENROUTER_API_KEY", "RESEND_API_KEY", "RESEND_INBOUND_WEBHOOK_SECRET"):
    os.environ.pop(key, None)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from itk.config import get_settings  # noqa: E402
from itk.db import Base, get_engine, get_sessionmaker  # noqa: E402
from itk.main import app  # noqa: E402
from itk.services.oauth import get_cipher  # noqa: E402

CRON_HEADERS = {"X-Cron-Secret": TEST_ENV["API_CRON_SECRET"]}


@pytest.fixture(autouse=True)
def _fresh_database() -> Iterator[None]:
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean_outbox() -> Iterator[Path]:
    outbox = Path(TEST_ENV["EMAIL_OUTBOX_DIR"])
    for item in outbox.glob("*.html"):
        item.unlink()
    yield outbox


@pytest.fixture
def outbox(_clean_outbox: Path) -> Path:
    return _clean_outbox


@pytest.fixture
def db() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def csrf_client(client: TestClient) -> TestClient:
    """A client holding a CSRF cookie whose token is sent on every request."""
    token = client.get("/api/csrf-token").json()["csrf_token"]
    client.headers["x-csrf-token"] = token
    return client


@pytest.fixture
def override_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Change environment-backed settings for one test: `override_settings(KEY="value")`."""

    def apply(**values: str | None) -> None:
        for key, value in values.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        get_cipher.cache_clear()

    yield apply
    monkeypatch.undo()
    get_settings.cache_clear()
    get_cipher.cache_clear()
