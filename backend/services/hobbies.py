from __future__ import annotations

import json
import re
from collections import Counter
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import HobbyCityPair, HobbyTag, User, UserHobby
from services.ai import openrouter_client

_WORD_SPLIT = re.compile(r"[,;\n]+")


def _heuristic_tags(raw_text: str) -> list[str]:
    tags: list[str] = []
    for part in _WORD_SPLIT.split(raw_text.lower()):
        normalized = " ".join(part.split()).strip(" .")
        if 2 <= len(normalized) <= 32 and normalized not in tags:
            tags.append(normalized)
    return tags[:12]


def parse_hobby_tags(raw_text: str) -> list[str]:
    prompt = (
        "Extract up to 12 concise hobby tags from this text. "
        "Return valid JSON array of lowercase strings only. Text:\n"
        f"{raw_text}"
    )
    parsed_from_ai = openrouter_client.chat(prompt=prompt, system_prompt="Return strict JSON only.")
    if parsed_from_ai:
        try:
            candidate = json.loads(parsed_from_ai)
            if isinstance(candidate, list):
                cleaned = [str(item).strip().lower() for item in candidate if str(item).strip()]
                return list(dict.fromkeys(cleaned))[:12]
        except json.JSONDecodeError:
            pass
    return _heuristic_tags(raw_text)


def _get_or_create_hobby_tag(db: Session, tag_name: str) -> HobbyTag:
    existing = db.scalar(select(HobbyTag).where(HobbyTag.tag_name == tag_name))
    if existing:
        return existing
    hobby_tag = HobbyTag(tag_name=tag_name, search_prompt=f"Find upcoming {tag_name} events in {{city}} this week")
    db.add(hobby_tag)
    db.flush()
    return hobby_tag


def upsert_hobby_city_pairs(db: Session, city: str, tags: Iterable[str]) -> None:
    city_normalized = city.strip().lower()
    counts = Counter(tags)
    for tag_name, count in counts.items():
        hobby_tag = _get_or_create_hobby_tag(db, tag_name)
        pair = db.scalar(
            select(HobbyCityPair).where(HobbyCityPair.hobby_tag_id == hobby_tag.id, HobbyCityPair.city == city_normalized)
        )
        if pair:
            pair.frequency += count
        else:
            db.add(HobbyCityPair(hobby_tag_id=hobby_tag.id, city=city_normalized, frequency=count))


def parse_and_store_user_hobbies(db: Session, user_id: UUID) -> list[str]:
    user = db.get(User, user_id)
    if not user:
        return []

    latest_hobbies = db.scalars(
        select(UserHobby).where(UserHobby.user_id == user_id).order_by(UserHobby.created_at.desc())
    ).first()
    if not latest_hobbies:
        return []

    tags = parse_hobby_tags(latest_hobbies.raw_text)
    latest_hobbies.parsed_tags = tags
    upsert_hobby_city_pairs(db, user.city, tags)
    db.commit()
    return tags
