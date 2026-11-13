import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from itk.cities import is_pilot_city, normalize_city, pilot_cities_label
from itk.security import make_signed_value, verify_signed_value, verify_svix_signature
from tests.conftest import CRON_HEADERS

CASES = json.loads((Path(__file__).resolve().parents[2] / "shared" / "city-normalization-cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[case["input"] or "<empty>" for case in CASES])
def test_normalize_city_matches_shared_cases(case: dict[str, str]) -> None:
    assert normalize_city(case["input"]) == case["expected"]


def test_pilot_city_gate() -> None:
    assert is_pilot_city("San Antonio, TX 78205")
    assert is_pilot_city("austin")
    assert not is_pilot_city("Portland, OR")
    assert pilot_cities_label() == "Austin & San Antonio"


def test_signed_values_round_trip_and_reject_tampering() -> None:
    signed = make_signed_value("user-123")
    assert verify_signed_value(signed) == "user-123"

    value, expiry, signature = signed.rsplit(".", 2)
    assert verify_signed_value(f"user-456.{expiry}.{signature}") is None
    assert verify_signed_value("not-a-signed-value") is None


def test_signed_values_expire() -> None:
    assert verify_signed_value(make_signed_value("user-123", ttl_seconds=-1)) is None


def _svix_sign(secret: str, msg_id: str, ts: str, body: bytes) -> str:
    key = base64.b64decode(secret.removeprefix("whsec_"))
    digest = hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def test_svix_signature_verification() -> None:
    secret = "whsec_" + base64.b64encode(b"super-secret-key").decode()
    body = b'{"type":"email.received"}'
    ts = str(int(time.time()))
    signature = _svix_sign(secret, "msg_1", ts, body)

    assert verify_svix_signature(secret, body, "msg_1", ts, f"v1,bogus {signature}")
    assert not verify_svix_signature(secret, body + b" ", "msg_1", ts, signature)
    assert not verify_svix_signature(secret, body, "msg_1", str(int(time.time()) - 3600), signature)
    assert not verify_svix_signature(secret, body, None, ts, signature)


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 401),
        ({"X-Cron-Secret": "wrong"}, 401),
        (CRON_HEADERS, 200),
        ({"Authorization": f"Bearer {CRON_HEADERS['X-Cron-Secret']}"}, 200),
    ],
)
def test_pipeline_endpoints_require_cron_secret(client: TestClient, headers: dict[str, str], status: int) -> None:
    response = client.post("/api/pipeline/draft-emails", json={}, headers=headers)
    assert response.status_code == status


def test_security_headers(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.json() == {"status": "ok"}
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
