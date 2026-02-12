from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from models import HobbyCityPair
from services.ai import openrouter_client


def _build_search_prompt(hobby: str, city: str) -> str:
    return (
        f"List all of the upcoming events in {city.title()} related to {hobby}. "
        f"Focus especially on ones happening in the next 7 days. Do not include "
        f"events that have already passed or that are happening in the distant future.\n\n"
        f"Include all relevant details about each event: name, exact date and time, "
        f"ticket price or if it's free, description of what to expect, full venue "
        f"name and address, and a direct link to tickets or event page.\n\n"
        f"Return as a JSON array. Each object should have these keys:\n"
        f"- name: event name\n"
        f"- date: date and time as a string\n"
        f"- location: venue name\n"
        f"- address: full street address\n"
        f"- price: ticket price or 'Free'\n"
        f"- description: 1-2 sentence description of the event\n"
        f"- url: direct link to event page or tickets\n"
        f"- category: the category/interest this matches\n"
        f"- cta: a short call-to-action label for the link button (e.g. 'Get tickets', 'RSVP', 'Learn more', 'Sign up', 'Check it out', 'See menu', 'Register'). Pick what fits the event type.\n\n"
        f"Only include real, verified events. If you cannot find any, return an empty array []."
    )


def _extract_json(text: str) -> list[dict]:
    """Extract JSON array from text that may contain markdown fences or prose."""
    if not text:
        return []

    # Try direct parse first
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fence
    match = re.search(r"```(?:json)?\s*(\[.*?])\s*```", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        except json.JSONDecodeError:
            pass

    # Try finding first [ ... ] block
    match = re.search(r"\[.*]", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        except json.JSONDecodeError:
            pass

    return []


def search_events_for_pair(db: Session, pair: HobbyCityPair) -> list[dict]:
    now = datetime.now(tz=timezone.utc)
    if pair.last_searched and pair.last_searched > (now - timedelta(days=1)) and pair.cached_results:
        return pair.cached_results

    settings = get_settings()
    hobby = pair.hobby_tag.tag_name
    city = pair.city

    prompt = _build_search_prompt(hobby, city)
    result = openrouter_client.search(
        prompt=prompt,
        system_prompt=(
            "You are a local events researcher. Return strict JSON arrays only. "
            "Only include real, currently-scheduled events with verifiable details. "
            "If you cannot verify an event exists, do not include it."
        ),
    )

    events = _extract_json(result)

    # Tag each event with the hobby that found it
    for event in events:
        event["source_hobby"] = hobby

    pair.cached_results = events if events else []
    pair.last_searched = now
    db.commit()
    return events


def search_events_for_pairs(db: Session, city: str | None = None, limit: int = 50) -> int:
    query = select(HobbyCityPair).order_by(HobbyCityPair.frequency.desc()).limit(limit)
    if city:
        query = query.where(HobbyCityPair.city == city.strip().lower())

    pairs = db.scalars(query).all()
    for pair in pairs:
        search_events_for_pair(db, pair)
    return len(pairs)
