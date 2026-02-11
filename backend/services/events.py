from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import HobbyCityPair
from services.ai import openrouter_client


def _fallback_events(city: str, hobby: str) -> list[dict]:
    return [
        {
            "name": f"Local {hobby.title()} Meetup",
            "date": "TBD",
            "location": city.title(),
            "why": f"Matches your interest in {hobby}",
            "url": "https://itk-so.vercel.app/sample-event",
        }
    ]


def search_events_for_pair(db: Session, pair: HobbyCityPair) -> list[dict]:
    now = datetime.now(tz=timezone.utc)
    if pair.last_searched and pair.last_searched > (now - timedelta(days=7)) and pair.cached_results:
        return pair.cached_results

    hobby = pair.hobby_tag.tag_name
    city = pair.city
    prompt = (
        "List 5 real upcoming local events as JSON array with keys "
        "name,date,location,why,url for this hobby/city: "
        f"{hobby} in {city}. Keep concise."
    )
    result = openrouter_client.chat(prompt=prompt, system_prompt="Return strict JSON only.")

    events: list[dict]
    try:
        parsed = json.loads(result) if result else []
        if isinstance(parsed, list) and parsed:
            events = [item for item in parsed if isinstance(item, dict)]
        else:
            events = _fallback_events(city, hobby)
    except json.JSONDecodeError:
        events = _fallback_events(city, hobby)

    pair.cached_results = events
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
