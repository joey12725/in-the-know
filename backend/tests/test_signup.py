from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.models import User, UserGoal, UserHobby, WaitlistEntry
from itk.services.newsletter import unsubscribe_url

SIGNUP = {
    "name": "Maya Torres",
    "email": "Maya.Torres@example.com",
    "address": "100 Example Ave, Austin, TX",
    "city": "Austin",
    "hobbies_raw_text": "live music, <b>pottery</b>, trail running",
    "goals_raw_text": "meet runners",
    "goal_types": ["friends", "Friends", "hobby-growth"],
    "event_radius_miles": 20,
}


def test_signup_requires_csrf(client: TestClient) -> None:
    assert client.post("/api/signup", json=SIGNUP).status_code == 403


def test_signup_creates_subscriber_and_sends_welcome_email(csrf_client: TestClient, db: Session, outbox: Path) -> None:
    response = csrf_client.post("/api/signup", json=SIGNUP)
    assert response.status_code == 200
    token = response.json()["onboarding_token"]

    user = db.scalar(select(User).where(User.email == "maya.torres@example.com"))
    assert user is not None and user.onboarding_token == token and user.is_subscribed
    hobby = db.scalar(select(UserHobby).where(UserHobby.user_id == user.id))
    assert hobby is not None and hobby.raw_text == "live music, pottery, trail running"  # HTML stripped
    goal = db.scalar(select(UserGoal).where(UserGoal.user_id == user.id))
    assert goal is not None and goal.goal_types == ["friends", "hobby-growth"]

    emails = list(outbox.glob("*.html"))
    assert len(emails) == 1
    assert f"/onboarding?token={token}" in emails[0].read_text()


def test_signup_outside_pilot_is_rejected(csrf_client: TestClient) -> None:
    response = csrf_client.post("/api/signup", json={**SIGNUP, "city": "Portland, OR"})
    assert response.status_code == 409
    assert "Austin & San Antonio" in response.json()["detail"]


def test_resignup_updates_profile_and_rotates_token(csrf_client: TestClient, db: Session) -> None:
    first = csrf_client.post("/api/signup", json=SIGNUP).json()
    second = csrf_client.post("/api/signup", json={**SIGNUP, "city": "San Antonio", "name": "Maya T."}).json()
    assert first["user_id"] == second["user_id"]
    assert first["onboarding_token"] != second["onboarding_token"]
    user = db.get(User, UUID(second["user_id"]))
    assert user is not None and user.city == "San Antonio" and user.name == "Maya T."


def test_waitlist_upserts(csrf_client: TestClient, db: Session) -> None:
    entry = {"name": "Sam", "email": "sam@example.com", "address": "1 Main St", "city": "Denver"}
    assert csrf_client.post("/api/waitlist", json=entry).json()["joined"] is True
    assert csrf_client.post("/api/waitlist", json={**entry, "city": "Boulder"}).status_code == 200
    rows = db.scalars(select(WaitlistEntry)).all()
    assert [row.city for row in rows] == ["Boulder"]


def test_onboarding_status_and_steps(csrf_client: TestClient) -> None:
    token = csrf_client.post("/api/signup", json=SIGNUP).json()["onboarding_token"]
    for _ in range(2):  # idempotent
        assert csrf_client.post(f"/api/onboarding/{token}/step", json={"step_name": "hobbies"}).status_code == 200

    status = csrf_client.get(f"/api/onboarding/{token}").json()
    assert status["name"] == "Maya Torres"
    assert status["completed_steps"] == ["hobbies"]
    assert status["connected_providers"] == []
    assert csrf_client.get("/api/onboarding/nope").status_code == 404


def test_unsubscribe_link(csrf_client: TestClient, db: Session) -> None:
    user_id = csrf_client.post("/api/signup", json=SIGNUP).json()["user_id"]
    link = urlparse(unsubscribe_url(UUID(user_id)))
    token = parse_qs(link.query)["token"][0]

    assert csrf_client.get("/api/unsubscribe", params={"token": token}).status_code == 200
    assert csrf_client.get("/api/unsubscribe", params={"token": token + "x"}).status_code == 400
    user = db.scalar(select(User))
    assert user is not None and user.is_subscribed is False
