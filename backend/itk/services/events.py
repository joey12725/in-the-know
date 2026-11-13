"""Event research for (interest, city) pairs, cached per pair for 24 hours."""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.db import as_utc, utcnow
from itk.models import Event, HobbyCityPair
from itk.services.llm import llm, parse_json_array

PAIR_CACHE_TTL = timedelta(days=1)

EVENT_SEARCH_SYSTEM_PROMPT = (
    "You are a local events researcher. Return strict JSON arrays only. "
    "Only include real, currently-scheduled events with verifiable details. "
    "If you cannot verify an event exists, do not include it."
)


def normalize_event(raw: dict[str, Any], **defaults: str) -> Event | None:
    """Coerce a model-produced event into the shape the newsletter renderer expects.

    Older cache rows used `why` for the blurb; it is accepted as an alias of `description`.
    Returns None for entries without a name.
    """
    name = str(raw.get("name") or "").strip()
    if not name:
        return None

    def field(key: str, *aliases: str) -> str:
        for candidate in (key, *aliases):
            value = str(raw.get(candidate) or "").strip()
            if value:
                return value
        return defaults.get(key, "")

    event: Event = {
        "name": name,
        "date": field("date") or "Date TBA",
        "location": field("location", "venue"),
        "address": field("address"),
        "price": field("price", "cost"),
        "description": field("description", "why", "summary"),
        "url": field("url", "link"),
        "category": field("category", "type"),
        "cta": field("cta"),
    }
    return event


def parse_events(text: str, **defaults: str) -> list[Event]:
    events: list[Event] = []
    for item in parse_json_array(text):
        if isinstance(item, dict) and (event := normalize_event(item, **defaults)):
            events.append(event)
    return events


def build_search_prompt(hobby: str, city: str) -> str:
    return (
        f"List all of the upcoming events in {city.title()} related to {hobby}. "
        "Focus especially on ones happening in the next 7 days. Do not include "
        "events that have already passed or that are happening in the distant future.\n\n"
        "Include all relevant details about each event: name, exact date and time, "
        "ticket price or if it's free, description of what to expect, full venue "
        "name and address, and a direct link to tickets or event page.\n\n"
        "Return as a JSON array. Each object should have these keys:\n"
        "- name: event name\n"
        "- date: date and time as a string\n"
        "- location: venue name\n"
        "- address: full street address\n"
        "- price: ticket price or 'Free'\n"
        "- description: 1-2 sentence description of the event\n"
        "- url: direct link to event page or tickets\n"
        "- category: the category/interest this matches\n"
        "- cta: a short call-to-action label for the link button (e.g. 'Get tickets', 'RSVP', "
        "'Learn more', 'Sign up', 'Register'). Pick what fits the event type.\n\n"
        "Only include real, verified events. If you cannot find any, return an empty array []."
    )


def search_events_for_pair(db: Session, pair: HobbyCityPair, *, force_refresh: bool = False) -> list[Event]:
    now = utcnow()
    last_searched = as_utc(pair.last_searched)
    if not force_refresh and pair.cached_results and last_searched and last_searched > now - PAIR_CACHE_TTL:
        return pair.cached_results

    hobby = pair.hobby_tag.tag_name
    try:
        reply = llm.search(build_search_prompt(hobby, pair.city), system_prompt=EVENT_SEARCH_SYSTEM_PROMPT)
        events = parse_events(reply, category=hobby.title())
    except Exception:
        # A slow or failed search for one pair should not sink the whole run.
        events = []

    for event in events:
        event["source_hobby"] = hobby

    pair.cached_results = events
    pair.last_searched = now
    db.commit()
    return events


def search_events_for_pairs(db: Session, city: str | None = None, limit: int = 50) -> int:
    """Refresh the most popular pairs first, so shared interests are researched once for everyone."""
    query = select(HobbyCityPair).order_by(HobbyCityPair.frequency.desc()).limit(limit)
    if city:
        query = query.where(HobbyCityPair.city == city.strip().lower())
    pairs = db.scalars(query).all()
    for pair in pairs:
        search_events_for_pair(db, pair)
    return len(pairs)
