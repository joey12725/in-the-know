"""Turn a subscriber's free-text interests into shared hobby tags and (tag, city) pairs."""

import re
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.cities import normalize_city
from itk.models import HobbyCityPair, HobbyTag, User, UserHobby
from itk.services.llm import llm, parse_json_array

MAX_TAGS = 12
_SPLIT = re.compile(r"[,;\n]+")


def heuristic_tags(raw_text: str) -> list[str]:
    """Offline fallback: split on commas/semicolons/newlines and keep short phrases."""
    tags: list[str] = []
    for part in _SPLIT.split(raw_text.lower()):
        normalized = " ".join(part.split()).strip(" .")
        if 2 <= len(normalized) <= 32 and normalized not in tags:
            tags.append(normalized)
    return tags[:MAX_TAGS]


def parse_hobby_tags(raw_text: str) -> list[str]:
    reply = llm.chat(
        prompt=(
            f"Extract up to {MAX_TAGS} concise hobby tags from this text. "
            f"Return valid JSON array of lowercase strings only. Text:\n{raw_text}"
        ),
        system_prompt="Return strict JSON only.",
    )
    cleaned = [str(item).strip().lower() for item in parse_json_array(reply) if str(item).strip()]
    if cleaned:
        return list(dict.fromkeys(cleaned))[:MAX_TAGS]
    return heuristic_tags(raw_text)


def get_or_create_hobby_tag(db: Session, tag_name: str) -> HobbyTag:
    existing = db.scalar(select(HobbyTag).where(HobbyTag.tag_name == tag_name))
    if existing:
        return existing
    tag = HobbyTag(tag_name=tag_name, search_prompt=f"Find upcoming {tag_name} events in {{city}} this week")
    db.add(tag)
    db.flush()
    return tag


def upsert_hobby_city_pairs(db: Session, city: str, tags: Iterable[str]) -> None:
    city_key = normalize_city(city)
    for tag_name in dict.fromkeys(tags):
        tag = get_or_create_hobby_tag(db, tag_name)
        pair = db.scalar(
            select(HobbyCityPair).where(HobbyCityPair.hobby_tag_id == tag.id, HobbyCityPair.city == city_key)
        )
        if pair:
            pair.frequency += 1
        else:
            db.add(HobbyCityPair(hobby_tag_id=tag.id, city=city_key, frequency=1, cached_results=[]))
    db.flush()


def latest_hobbies(db: Session, user_id: UUID) -> UserHobby | None:
    return db.scalars(
        select(UserHobby).where(UserHobby.user_id == user_id).order_by(UserHobby.created_at.desc())
    ).first()


def parse_and_store_user_hobbies(db: Session, user_id: UUID) -> list[str]:
    """Parse the user's newest hobby text (once) and count any new tags toward city pairs."""
    user = db.get(User, user_id)
    if not user:
        return []
    history = db.scalars(
        select(UserHobby).where(UserHobby.user_id == user_id).order_by(UserHobby.created_at.desc()).limit(2)
    ).all()
    if not history:
        return []
    current = history[0]
    if current.parsed_tags:
        return list(current.parsed_tags)

    tags = parse_hobby_tags(current.raw_text)
    previous_tags = set(history[1].parsed_tags) if len(history) > 1 else set()
    current.parsed_tags = tags
    upsert_hobby_city_pairs(db, user.city, [tag for tag in tags if tag not in previous_tags])
    db.commit()
    return tags
