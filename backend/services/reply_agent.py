from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Newsletter, NewsletterFeedback, User, UserGoal, UserHobby
from services.ai import openrouter_client
from services.hobbies import parse_and_store_user_hobbies

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


@dataclass
class ReplyAgentResult:
    intent: str
    add_interests: list[str]
    remove_interests: list[str]
    feedback_type: str
    rewritten_feedback: str


def _extract_sender_email(raw_from: str) -> str:
    match = re.search(r"<([^>]+)>", raw_from or "")
    if match:
        return match.group(1).strip().lower()
    return (raw_from or "").strip().lower()


def _extract_recipient_candidates(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    candidates: list[str] = []
    for key in ("to", "cc", "delivered_to", "envelope_to"):
        value = data.get(key)
        if isinstance(value, str):
            candidates.extend(item.strip() for item in value.split(",") if item.strip())
        elif isinstance(value, list):
            candidates.extend(str(item).strip() for item in value if str(item).strip())
    return candidates


def _extract_newsletter_id_from_recipients(recipients: list[str]) -> UUID | None:
    for recipient in recipients:
        for match in UUID_RE.findall(recipient):
            try:
                return UUID(match)
            except ValueError:
                continue
    return None


def _extract_reply_text(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    raw_text = str(data.get("text") or data.get("text_body") or data.get("reply") or "").strip()
    if raw_text:
        return raw_text

    html = str(data.get("html") or data.get("html_body") or "").strip()
    if not html:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", html)
    collapsed = " ".join(without_tags.split())
    return collapsed


def _extract_json_dict(payload: str) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _heuristic_reply_result(reply_text: str) -> ReplyAgentResult:
    lowered = f" {reply_text.lower()} "
    if any(token in lowered for token in (" unsubscribe", " stop ", " remove me", " no longer")):
        return ReplyAgentResult(
            intent="unsubscribe",
            add_interests=[],
            remove_interests=[],
            feedback_type="preference",
            rewritten_feedback="User asked to unsubscribe from ITK newsletter emails.",
        )

    remove_intent = any(token in lowered for token in (" less ", " no ", " don't", "do not", "remove", "without"))
    add_intent = any(token in lowered for token in (" more ", " add ", " include", "also", "into"))

    if add_intent and not remove_intent:
        return ReplyAgentResult(
            intent="add_interests",
            add_interests=[],
            remove_interests=[],
            feedback_type="preference",
            rewritten_feedback="User asked to add new interests based on this reply.",
        )
    if remove_intent and not add_intent:
        return ReplyAgentResult(
            intent="remove_interests",
            add_interests=[],
            remove_interests=[],
            feedback_type="preference",
            rewritten_feedback="User asked to remove specific interests based on this reply.",
        )

    feedback_type = "negative" if any(token in lowered for token in (" not ", " didn't", "didnt", "bad", "hate")) else "suggestion"
    return ReplyAgentResult(
        intent="feedback",
        add_interests=[],
        remove_interests=[],
        feedback_type=feedback_type,
        rewritten_feedback=f"User feedback summary: {reply_text.strip()}",
    )


def classify_and_rewrite_reply(
    reply_text: str,
    newsletter: Newsletter | None = None,
    user: User | None = None,
) -> ReplyAgentResult:
    if not reply_text.strip():
        return ReplyAgentResult(
            intent="feedback",
            add_interests=[],
            remove_interests=[],
            feedback_type="suggestion",
            rewritten_feedback="User replied with minimal content and no explicit request.",
        )

    context_lines = []
    if user:
        context_lines.append(f"user_city={user.city}")
        context_lines.append(f"user_name={user.name}")
    if newsletter:
        context_lines.append(f"newsletter_id={newsletter.id}")
        context_lines.append(f"newsletter_subject={newsletter.subject}")
        context_lines.append(f"newsletter_events={newsletter.events_included[:5]}")

    prompt = (
        "Read an inbound newsletter reply and classify intent.\n"
        "Return strict JSON object with keys:\n"
        "- intent: one of add_interests, remove_interests, unsubscribe, feedback\n"
        "- add_interests: array of concise strings\n"
        "- remove_interests: array of concise strings\n"
        "- feedback_type: one of positive, negative, preference, suggestion\n"
        "- rewritten_feedback: a clear context-rich rewrite of user intent with newsletter/city details when relevant\n"
        "If intent is not feedback, still provide rewritten_feedback as a concise contextual summary.\n"
        f"Context: {' | '.join(context_lines) if context_lines else 'none'}\n"
        f"Raw reply:\n{reply_text}\n"
    )
    result = openrouter_client.chat(
        prompt=prompt,
        system_prompt="You are an email-reply intent classifier for ITK. Return strict JSON only.",
    )
    parsed = _extract_json_dict(result)
    if not parsed:
        return _heuristic_reply_result(reply_text)

    intent = str(parsed.get("intent", "")).strip().lower()
    if intent not in {"add_interests", "remove_interests", "unsubscribe", "feedback"}:
        return _heuristic_reply_result(reply_text)

    add_interests = [str(item).strip().lower() for item in parsed.get("add_interests", []) if str(item).strip()]
    remove_interests = [str(item).strip().lower() for item in parsed.get("remove_interests", []) if str(item).strip()]
    feedback_type = str(parsed.get("feedback_type", "suggestion")).strip().lower()
    if feedback_type not in {"positive", "negative", "preference", "suggestion"}:
        feedback_type = "suggestion"
    rewritten_feedback = str(parsed.get("rewritten_feedback", "")).strip() or _heuristic_reply_result(reply_text).rewritten_feedback

    return ReplyAgentResult(
        intent=intent,
        add_interests=list(dict.fromkeys(add_interests))[:12],
        remove_interests=list(dict.fromkeys(remove_interests))[:12],
        feedback_type=feedback_type,
        rewritten_feedback=rewritten_feedback,
    )


def _apply_add_interests(db: Session, user: User, interests: list[str]) -> int:
    if not interests:
        return 0

    latest_hobbies = db.scalars(select(UserHobby).where(UserHobby.user_id == user.id).order_by(UserHobby.created_at.desc())).first()
    existing_raw = latest_hobbies.raw_text if latest_hobbies else ""
    additions = ", ".join(interests)
    merged_raw = f"{existing_raw}\nAlso interested in: {additions}".strip()

    db.add(UserHobby(user_id=user.id, raw_text=merged_raw, parsed_tags=[]))
    db.flush()
    parse_and_store_user_hobbies(db, user.id)
    return len(interests)


def _apply_remove_interests(db: Session, user: User, interests: list[str]) -> int:
    if not interests:
        return 0
    summary = ", ".join(interests)
    db.add(
        UserGoal(
            user_id=user.id,
            raw_text=f"User asked to avoid or reduce these topics in recommendations: {summary}",
            goal_types=["avoid", "content_filter"],
        )
    )
    return len(interests)


def _resolve_user_and_newsletter(
    db: Session,
    sender_email: str,
    recipients: list[str],
) -> tuple[User | None, Newsletter | None]:
    newsletter = None
    newsletter_id = _extract_newsletter_id_from_recipients(recipients)
    if newsletter_id:
        newsletter = db.get(Newsletter, newsletter_id)
    if newsletter:
        user = db.get(User, newsletter.user_id)
        return user, newsletter

    user = db.scalar(select(User).where(User.email == sender_email.lower()))
    if not user:
        return None, None

    latest_newsletter = db.scalars(
        select(Newsletter).where(Newsletter.user_id == user.id).order_by(Newsletter.created_at.desc())
    ).first()
    return user, latest_newsletter


def process_inbound_reply_payload(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    sender_email = _extract_sender_email(str(data.get("from", "")))
    recipients = _extract_recipient_candidates(payload)
    raw_reply = _extract_reply_text(payload)

    user, newsletter = _resolve_user_and_newsletter(db, sender_email=sender_email, recipients=recipients)
    reply_result = classify_and_rewrite_reply(raw_reply, newsletter=newsletter, user=user)

    if not user:
        return {
            "processed": False,
            "detail": "No matching user found for inbound reply.",
            "sender_email": sender_email,
            "intent": reply_result.intent,
        }

    updates_applied = {"added_interests": 0, "removed_interests": 0, "unsubscribed": False, "feedback_saved": False}

    if reply_result.intent == "unsubscribe":
        user.is_subscribed = False
        updates_applied["unsubscribed"] = True

    if reply_result.intent == "add_interests":
        updates_applied["added_interests"] = _apply_add_interests(db, user, reply_result.add_interests)

    if reply_result.intent == "remove_interests":
        updates_applied["removed_interests"] = _apply_remove_interests(db, user, reply_result.remove_interests)

    if reply_result.intent == "feedback":
        db.add(
            NewsletterFeedback(
                user_id=user.id,
                newsletter_id=newsletter.id if newsletter else None,
                raw_reply=raw_reply or "(empty reply)",
                rewritten_feedback=reply_result.rewritten_feedback,
                feedback_type=reply_result.feedback_type,
            )
        )
        updates_applied["feedback_saved"] = True

    db.commit()
    return {
        "processed": True,
        "user_id": str(user.id),
        "newsletter_id": str(newsletter.id) if newsletter else None,
        "intent": reply_result.intent,
        "feedback_type": reply_result.feedback_type,
        "rewritten_feedback": reply_result.rewritten_feedback,
        "updates": updates_applied,
    }
