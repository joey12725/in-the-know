from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.models import NewsletterFeedback, User, UserHobby
from itk.seed import seed
from itk.services import reply_agent
from itk.services.newsletter import draft_newsletter_for_user, recent_feedback, reply_to_address

WEBHOOK = "/api/webhooks/email-reply"


@pytest.fixture
def devin(db: Session) -> User:
    seed(db)
    user = db.scalar(select(User).where(User.email == "devin.park@example.com"))
    assert user is not None
    return user


def _payload(sender: str, text: str, to: str = "reply@itk.test") -> dict[str, Any]:
    return {"type": "email.received", "data": {"from": f"Someone <{sender}>", "to": [to], "text": text}}


def test_webhook_requires_shared_secret_when_configured(
    client: TestClient, devin: User, override_settings: Callable[..., None]
) -> None:
    override_settings(RESEND_INBOUND_WEBHOOK_SECRET="hook-secret")
    payload = _payload(devin.email, "unsubscribe")
    assert client.post(WEBHOOK, json=payload).status_code == 401
    assert client.post(WEBHOOK, json=payload, headers={"X-Webhook-Secret": "wrong"}).status_code == 401
    assert client.post(WEBHOOK, json=payload, headers={"X-Webhook-Secret": "hook-secret"}).status_code == 200


def test_webhook_refuses_unsigned_requests_in_production(
    client: TestClient, override_settings: Callable[..., None]
) -> None:
    override_settings(ENVIRONMENT="production")
    assert client.post(WEBHOOK, json=_payload("x@example.com", "hi")).status_code == 503


def test_unsubscribe_reply(client: TestClient, db: Session, devin: User) -> None:
    result = client.post(WEBHOOK, json=_payload(devin.email, "Please unsubscribe me")).json()
    assert result["intent"] == "unsubscribe"
    db.refresh(devin)
    assert devin.is_subscribed is False


def test_unknown_sender_is_ignored(client: TestClient) -> None:
    assert client.post(WEBHOOK, json=_payload("stranger@example.com", "hi")).json()["processed"] is False


def test_feedback_reply_is_matched_to_issue_and_reaches_next_prompt(
    client: TestClient, db: Session, devin: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = draft_newsletter_for_user(db, devin)
    assert issue is not None
    rewritten = "User does not want rodeo events in their San Antonio issue."

    def fake_chat(prompt: str, **_: Any) -> str:
        assert issue.subject in prompt  # the classifier sees which issue was answered
        return f'{{"intent": "feedback", "feedback_type": "negative", "rewritten_feedback": "{rewritten}"}}'

    monkeypatch.setattr(reply_agent.llm, "chat", fake_chat)
    reply_to = reply_to_address(issue.id)
    assert reply_to is not None
    # Sent from a different address: the plus-addressed recipient still identifies the issue.
    result = client.post(WEBHOOK, json=_payload("alias@example.com", "less rodeo stuff please", to=reply_to)).json()

    assert result["newsletter_id"] == str(issue.id)
    feedback = db.scalar(select(NewsletterFeedback))
    assert feedback is not None and feedback.newsletter_id == issue.id
    assert recent_feedback(db, devin.id) == [rewritten]


def test_add_and_remove_interests(db: Session, devin: User, monkeypatch: pytest.MonkeyPatch) -> None:
    replies = iter(
        [
            '{"intent": "add_interests", "add_interests": ["Salsa Dancing"], "feedback_type": "preference"}',
            '{"intent": "remove_interests", "remove_interests": ["board games"], "feedback_type": "preference",'
            ' "rewritten_feedback": "Skip board game nights."}',
        ]
    )

    def fake_chat(prompt: str, **_: Any) -> str:
        # Reply classification gets the scripted answers; tag parsing falls back to heuristics.
        return next(replies) if "classify intent" in prompt else ""

    monkeypatch.setattr(reply_agent.llm, "chat", fake_chat)

    reply_agent.process_inbound_reply(db, _payload(devin.email, "add salsa dancing"))
    latest = db.scalars(
        select(UserHobby).where(UserHobby.user_id == devin.id).order_by(UserHobby.created_at.desc())
    ).first()
    assert latest is not None and "salsa dancing" in latest.parsed_tags

    reply_agent.process_inbound_reply(db, _payload(devin.email, "no more board games"))
    db.refresh(latest)
    assert "board games" not in latest.parsed_tags
    assert recent_feedback(db, devin.id) == ["Skip board game nights."]


@pytest.mark.parametrize(
    ("text", "intent"),
    [("stop sending these", "unsubscribe"), ("add more jazz", "add_interests"),
     ("less country music", "remove_interests"), ("this was great", "feedback")],
)  # fmt: skip
def test_heuristic_classifier(text: str, intent: str) -> None:
    assert reply_agent.heuristic_classification(text).intent == intent
