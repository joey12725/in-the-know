"""Inbound reply handling: readers can just answer the newsletter.

Each reply is classified into one of four intents and acted on:

- `add_interests`:    append to the subscriber's interests and re-parse tags
- `remove_interests`: drop matching tags and remember the preference
- `unsubscribe`:      stop sending
- `feedback`:         store a context-rich rewrite ("User doesn't want rodeo events in
                      their San Antonio issue; they were shown ...") that the copywriter
                      sees when drafting the next issue
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.models import Newsletter, NewsletterFeedback, User, UserHobby
from itk.services.hobbies import latest_hobbies, parse_and_store_user_hobbies
from itk.services.llm import llm, parse_json_object
from itk.services.mailer import extract_address

Intent = Literal["add_interests", "remove_interests", "unsubscribe", "feedback"]
INTENTS: set[str] = {"add_interests", "remove_interests", "unsubscribe", "feedback"}
FEEDBACK_TYPES = {"positive", "negative", "preference", "suggestion"}

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


@dataclass
class ReplyClassification:
    intent: Intent
    feedback_type: str
    rewritten_feedback: str
    add_interests: list[str] = field(default_factory=list)
    remove_interests: list[str] = field(default_factory=list)


@dataclass
class InboundReply:
    sender: str
    recipients: list[str]
    text: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "InboundReply":
        """Accept both Resend's `{"type": ..., "data": {...}}` envelope and a flat payload."""
        envelope = payload.get("data")
        data: dict[str, Any] = envelope if isinstance(envelope, dict) else payload
        recipients: list[str] = []
        for key in ("to", "cc", "delivered_to", "envelope_to"):
            value = data.get(key)
            if isinstance(value, str):
                recipients.extend(item.strip() for item in value.split(",") if item.strip())
            elif isinstance(value, list):
                recipients.extend(str(item).strip() for item in value if str(item).strip())

        text = str(data.get("text") or data.get("text_body") or data.get("reply") or "").strip()
        if not text:
            html = str(data.get("html") or data.get("html_body") or "")
            text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
        return cls(sender=extract_address(str(data.get("from") or "")).lower(), recipients=recipients, text=text)

    def newsletter_id(self) -> UUID | None:
        """Issues are sent with reply-to `reply+<newsletter-id>@domain`."""
        for recipient in self.recipients:
            if match := UUID_RE.search(recipient):
                return UUID(match.group(0))
        return None


def heuristic_classification(reply_text: str) -> ReplyClassification:
    text = f" {reply_text.lower()} "
    if any(token in text for token in (" unsubscribe", " stop ", " remove me", " no longer")):
        return ReplyClassification("unsubscribe", "preference", "User asked to unsubscribe from ITK newsletter emails.")

    wants_less = any(token in text for token in (" less ", " no ", " don't", "do not", "remove", "without"))
    wants_more = any(token in text for token in (" more ", " add ", " include", "also", "into"))
    if wants_more and not wants_less:
        return ReplyClassification(
            "add_interests", "preference", "User asked to add new interests based on this reply."
        )
    if wants_less and not wants_more:
        return ReplyClassification(
            "remove_interests", "preference", "User asked to remove specific interests based on this reply."
        )

    negative = any(token in text for token in (" not ", " didn't", "didnt", "bad", "hate"))
    return ReplyClassification(
        "feedback", "negative" if negative else "suggestion", f"User feedback summary: {reply_text.strip()}"
    )


def _clean_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items = [str(item).strip().lower() for item in value if str(item).strip()]
    return list(dict.fromkeys(items))[:12]


def classify_reply(reply_text: str, user: User | None, newsletter: Newsletter | None) -> ReplyClassification:
    if not reply_text.strip():
        return ReplyClassification("feedback", "suggestion", "User replied with no content and no explicit request.")

    context = []
    if user:
        context += [f"user_city={user.city}", f"user_name={user.name}"]
    if newsletter:
        context += [
            f"newsletter_subject={newsletter.subject}",
            f"newsletter_sent={newsletter.sent_at or newsletter.created_at:%Y-%m-%d}",
            f"newsletter_events={[event.get('name') for event in newsletter.events_included[:5]]}",
        ]

    reply = llm.chat(
        prompt=(
            "Read an inbound newsletter reply and classify intent.\n"
            "Return strict JSON object with keys:\n"
            "- intent: one of add_interests, remove_interests, unsubscribe, feedback\n"
            "- add_interests: array of concise strings\n"
            "- remove_interests: array of concise strings\n"
            "- feedback_type: one of positive, negative, preference, suggestion\n"
            "- rewritten_feedback: a clear context-rich rewrite of user intent with newsletter/city details "
            "when relevant\n"
            f"Context: {' | '.join(context) or 'none'}\n"
            f"Raw reply:\n{reply_text}\n"
        ),
        system_prompt="You are an email-reply intent classifier for ITK. Return strict JSON only.",
    )
    parsed = parse_json_object(reply)
    intent = str(parsed.get("intent", "")).strip().lower()
    if intent not in INTENTS:
        return heuristic_classification(reply_text)

    feedback_type = str(parsed.get("feedback_type", "")).strip().lower()
    rewritten = str(parsed.get("rewritten_feedback", "")).strip()
    return ReplyClassification(
        intent=cast(Intent, intent),
        feedback_type=feedback_type if feedback_type in FEEDBACK_TYPES else "suggestion",
        rewritten_feedback=rewritten or heuristic_classification(reply_text).rewritten_feedback,
        add_interests=_clean_list(parsed.get("add_interests")),
        remove_interests=_clean_list(parsed.get("remove_interests")),
    )


def _resolve(db: Session, reply: InboundReply) -> tuple[User | None, Newsletter | None]:
    newsletter_id = reply.newsletter_id()
    newsletter = db.get(Newsletter, newsletter_id) if newsletter_id else None
    if newsletter:
        return db.get(User, newsletter.user_id), newsletter

    user = db.scalar(select(User).where(User.email == reply.sender))
    if not user:
        return None, None
    latest = db.scalars(
        select(Newsletter).where(Newsletter.user_id == user.id).order_by(Newsletter.created_at.desc())
    ).first()
    return user, latest


def _add_interests(db: Session, user: User, interests: list[str]) -> int:
    if not interests:
        return 0
    current = latest_hobbies(db, user.id)
    merged = "\n".join(filter(None, [current.raw_text if current else "", *interests]))
    db.add(UserHobby(user_id=user.id, raw_text=merged, parsed_tags=[]))
    db.flush()
    parse_and_store_user_hobbies(db, user.id)
    return len(interests)


def _remove_interests(db: Session, user: User, interests: list[str]) -> int:
    current = latest_hobbies(db, user.id)
    if not interests or not current:
        return 0
    unwanted = set(interests)
    current.parsed_tags = [tag for tag in current.parsed_tags if tag not in unwanted]
    return len(interests)


def process_inbound_reply(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    reply = InboundReply.from_payload(payload)
    user, newsletter = _resolve(db, reply)
    if not user:
        return {"processed": False, "detail": "No matching user found for inbound reply."}

    result = classify_reply(reply.text, user, newsletter)
    updates = {"added_interests": 0, "removed_interests": 0, "unsubscribed": False, "feedback_saved": False}

    if result.intent == "unsubscribe":
        user.is_subscribed = False
        updates["unsubscribed"] = True
    elif result.intent == "add_interests":
        updates["added_interests"] = _add_interests(db, user, result.add_interests)
    elif result.intent == "remove_interests":
        updates["removed_interests"] = _remove_interests(db, user, result.remove_interests)

    # Feedback and removals both become guidance for the next issue's copywriter.
    if result.intent in {"feedback", "remove_interests"}:
        db.add(
            NewsletterFeedback(
                user_id=user.id,
                newsletter_id=newsletter.id if newsletter else None,
                raw_reply=reply.text or "(empty reply)",
                rewritten_feedback=result.rewritten_feedback,
                feedback_type=result.feedback_type,
            )
        )
        updates["feedback_saved"] = True

    db.commit()
    return {
        "processed": True,
        "user_id": str(user.id),
        "newsletter_id": str(newsletter.id) if newsletter else None,
        "intent": result.intent,
        "feedback_type": result.feedback_type,
        "updates": updates,
    }
