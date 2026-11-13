from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.models import HobbyCityPair, Newsletter, User
from itk.security import verify_signed_value
from itk.seed import seed
from itk.services import newsletter as newsletter_service
from itk.services.llm import parse_json_array, parse_json_object
from itk.services.newsletter import (
    clean_intro,
    clean_subject,
    draft_newsletter_for_user,
    draft_newsletters,
    merge_events,
    reply_to_address,
    send_newsletters,
)
from itk.services.newsletter_template import infer_category, price_indicator


def _user(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


@pytest.fixture
def seeded(db: Session) -> Session:
    assert seed(db) == 3
    assert seed(db) == 0  # idempotent
    return db


def test_draft_uses_subscribers_own_interests_first(seeded: Session) -> None:
    maya = _user(seeded, "maya.torres@example.com")
    issue = draft_newsletter_for_user(seeded, maya)
    assert issue is not None

    names = [event["name"] for event in issue.events_included]
    assert names[0] == "Hollow Pines Album Release"  # venue calendar leads
    assert {"Skin-Contact Flight Night", "Wheel Throwing Drop-In", "Sunrise Greenbelt 5 Miler"} <= set(names)
    assert "Late Set at the Blue Lantern" not in names  # other city

    assert issue.subject.startswith("Austin: ")  # offline fallback subject
    assert "Maya Torres, your week in Austin" in issue.html_content
    assert "Book a wheel" in issue.html_content  # per-event CTA survives
    assert "Two hours on the wheel" in issue.html_content  # description is rendered


def test_unsubscribe_link_in_issue_is_signed_for_the_recipient(seeded: Session) -> None:
    devin = _user(seeded, "devin.park@example.com")
    issue = draft_newsletter_for_user(seeded, devin)
    assert issue is not None
    token = issue.html_content.split("/api/unsubscribe?token=", 1)[1].split('"', 1)[0]
    assert verify_signed_value(token.replace("%3A", ":")) == str(devin.id)


def test_no_events_means_no_issue(db: Session) -> None:
    user = User(name="Lee", email="lee@example.com", address="x", city="Austin", onboarding_token="t")
    db.add(user)
    db.commit()
    assert draft_newsletter_for_user(db, user) is None
    assert draft_newsletters(db) == 0


def test_model_copy_is_used_and_html_escaped(seeded: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    prompts: list[str] = []

    def fake_write(prompt: str, **_: Any) -> str:
        prompts.append(prompt)
        return '```json\n{"subject": "Wheel day, wine night", "intro": "Lowkey your best week yet. Trust."}\n```'

    monkeypatch.setattr(newsletter_service.llm, "write", fake_write)
    pair = seeded.scalars(select(HobbyCityPair).where(HobbyCityPair.city == "san antonio")).first()
    assert pair is not None
    pair.cached_results = [{**pair.cached_results[0], "name": "<script>alert(1)</script>"}]
    seeded.commit()

    devin = _user(seeded, "devin.park@example.com")
    issue = draft_newsletter_for_user(seeded, devin)
    assert issue is not None
    assert issue.subject == "Wheel day, wine night"
    assert "Lowkey your best week yet." in issue.html_content
    assert "Trust." not in issue.html_content  # intro is clamped to one sentence
    assert "<script>" not in issue.html_content
    assert "date_night_spots" in prompts[0]
    assert "jazz, food trucks, film photography" in prompts[0]


def test_send_delivers_to_outbox_and_skips_unsubscribed(seeded: Session, outbox: Path) -> None:
    assert draft_newsletters(seeded) == 3
    priya = _user(seeded, "priya.shah@example.com")
    priya.is_subscribed = False
    seeded.commit()

    assert send_newsletters(seeded) == 2
    assert len(list(outbox.glob("*.html"))) == 2
    unsent = seeded.scalars(select(Newsletter).where(Newsletter.sent_at.is_(None))).all()
    assert [issue.user_id for issue in unsent] == [priya.id]
    assert send_newsletters(seeded) == 0  # nothing left to send


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("  Jazz,   tacos and a darkroom  ", "Jazz, tacos and a darkroom"),
        ("What's actually worth leaving the house for", "Austin: Porchlight Sessions"),
        ("", "Austin: Porchlight Sessions"),
    ],
)
def test_clean_subject(subject: str, expected: str) -> None:
    assert clean_subject(subject, "Austin", [{"name": "Porchlight Sessions"}]) == expected


@pytest.mark.parametrize(
    ("intro", "expected"),
    [
        ("This week goes stupid hard. More below!", "This week goes stupid hard."),
        ("Yo this fits your vibe", "This week in Austin has a few legit standouts that are actually worth your time."),
        ("no punctuation here", "no punctuation here."),
        ("Doors at 7.30 sharp tonight", "Doors at 7.30 sharp tonight."),
    ],
)
def test_clean_intro(intro: str, expected: str) -> None:
    assert clean_intro(intro, "Austin") == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Free", "Free"), ("$0", "Free"), ("$12", "$"), ("$25-$40", "$$"), ("$75", "$$$"), ("$1,200", "$$$$"),
     ("$$", "$$"), ("", "$$"), (None, "$$")],
)  # fmt: skip
def test_price_indicator(raw: object, expected: str) -> None:
    assert price_indicator(raw) == expected


def test_infer_category() -> None:
    assert infer_category({"category": "outdoors"}) == "Outdoors"
    assert infer_category({"name": "Gallery opening night"}) == "Arts"
    assert infer_category({"name": "Something"}) == "Featured"


def test_merge_events_dedupes() -> None:
    a = {"name": "Show", "date": "Fri", "location": "Hall"}
    assert merge_events([a], [{**a, "name": " show "}], [{"name": ""}]) == [a]


def test_reply_to_is_plus_addressed() -> None:
    issue_id = UUID("12345678-1234-5678-1234-567812345678")
    assert reply_to_address(issue_id) == f"reply+{issue_id}@itk.test"


def test_json_helpers_tolerate_model_formatting() -> None:
    assert parse_json_array('Sure! Here you go:\n```json\n["a", "b"]\n```') == ["a", "b"]
    assert parse_json_array("[1, 2] trailing prose") == [1, 2]
    assert parse_json_array("nothing here") == []
    assert parse_json_object('Result: {"intent": "feedback"} done') == {"intent": "feedback"}
    assert parse_json_object("[]") == {}
