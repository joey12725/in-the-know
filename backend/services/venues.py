from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import CityVenue
from services.ai import openrouter_client

PILOT_CITIES = ("austin", "san antonio")


def normalize_city(value: str) -> str:
    normalized = " ".join(value.strip().lower().replace(".", "").split())
    if "," in normalized:
        normalized = normalized.split(",", 1)[0].strip()
    for suffix in (", tx", ", texas", " tx", " texas"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
            break
    return normalized


def _fallback_venues(city: str) -> list[dict[str, str]]:
    if city == "austin":
        return [
            {"venue_name": "Mohawk Austin", "address": "912 Red River St, Austin, TX", "website": "https://mohawkaustin.com"},
            {"venue_name": "ACL Live at The Moody Theater", "address": "310 W Willie Nelson Blvd, Austin, TX", "website": "https://acllive.com"},
            {"venue_name": "Stubb's Waller Creek Amphitheater", "address": "801 Red River St, Austin, TX", "website": "https://www.stubbsaustin.com"},
            {"venue_name": "Emo's Austin", "address": "2015 E Riverside Dr, Austin, TX", "website": "https://www.emosaustin.com"},
            {"venue_name": "Scoot Inn", "address": "1308 E 4th St, Austin, TX", "website": "https://www.scootinnaustin.com"},
        ]
    if city == "san antonio":
        return [
            {"venue_name": "The Aztec Theatre", "address": "104 N St Mary's St, San Antonio, TX", "website": "https://www.aztectheatre.com"},
            {"venue_name": "Tobin Center for the Performing Arts", "address": "100 Auditorium Cir, San Antonio, TX", "website": "https://www.tobincenter.org"},
            {"venue_name": "Paper Tiger", "address": "2410 N St Mary's St, San Antonio, TX", "website": "https://papertigersa.com"},
            {"venue_name": "Sam's Burger Joint", "address": "330 E Grayson St, San Antonio, TX", "website": "https://samsburgerjoint.com"},
            {"venue_name": "Stable Hall", "address": "307 Pearl Pkwy, San Antonio, TX", "website": "https://stablehall.com"},
        ]
    return []


def _parse_json_list(payload: str) -> list[dict[str, Any]]:
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []

    cleaned: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, str):
            name = item.strip()
            if name:
                cleaned.append({"venue_name": name})
            continue
        if isinstance(item, dict):
            name = str(item.get("venue_name", "")).strip()
            if not name:
                continue
            cleaned.append(
                {
                    "venue_name": name,
                    "address": str(item.get("address", "")).strip() or None,
                    "website": str(item.get("website", "")).strip() or None,
                }
            )
    return cleaned


def discover_major_music_venues(db: Session, city: str, force_refresh: bool = False) -> int:
    normalized_city = normalize_city(city)
    if normalized_city not in PILOT_CITIES:
        return 0

    now = datetime.now(tz=timezone.utc)
    existing = db.scalars(select(CityVenue).where(CityVenue.city == normalized_city, CityVenue.venue_type == "music")).all()
    if existing and not force_refresh:
        newest_search = max((venue.last_searched for venue in existing if venue.last_searched), default=None)
        if newest_search and newest_search > now - timedelta(days=30):
            return 0

    result = openrouter_client.chat(
        prompt=(
            f"List major live music venues in {normalized_city.title()}, Texas.\n"
            "Return strict JSON array of objects with keys: venue_name, address, website.\n"
            "Keep only established venues with frequent live shows."
        ),
        system_prompt="Return strict JSON only.",
    )
    parsed_venues = _parse_json_list(result)
    if not parsed_venues:
        parsed_venues = _fallback_venues(normalized_city)

    existing_by_name = {venue.venue_name.strip().lower(): venue for venue in existing}
    touched = 0
    for venue_data in parsed_venues:
        venue_name = str(venue_data.get("venue_name", "")).strip()
        if not venue_name:
            continue
        key = venue_name.lower()
        existing_row = existing_by_name.get(key)
        if existing_row:
            existing_row.address = venue_data.get("address")
            existing_row.website = venue_data.get("website")
            existing_row.last_searched = now
            touched += 1
            continue

        db.add(
            CityVenue(
                city=normalized_city,
                venue_name=venue_name,
                venue_type="music",
                address=venue_data.get("address"),
                website=venue_data.get("website"),
                last_searched=now,
                cached_events=[],
            )
        )
        touched += 1

    db.commit()
    return touched


def discover_pilot_city_venues(db: Session, force_refresh: bool = False) -> int:
    total = 0
    for city in PILOT_CITIES:
        total += discover_major_music_venues(db, city=city, force_refresh=force_refresh)
    return total


def _fallback_venue_events(city: str, venue_name: str) -> list[dict[str, str]]:
    return [
        {
            "name": f"{venue_name} Weekly Showcase",
            "date": "This week",
            "location": f"{venue_name}, {city.title()}",
            "price": "$$",
            "why": "Popular local venue with frequent lineups worth checking before plans fill up.",
            "url": "https://itk-so.vercel.app",
            "category": "Music",
        }
    ]


def _parse_events(payload: str, city: str, venue_name: str) -> list[dict[str, str]]:
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []

    events: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        event_name = str(item.get("name", "")).strip()
        if not event_name:
            continue
        events.append(
            {
                "name": event_name,
                "date": str(item.get("date", "")).strip() or "Date TBA",
                "location": str(item.get("location", "")).strip() or f"{venue_name}, {city.title()}",
                "price": str(item.get("price", "")).strip() or "$$",
                "why": str(item.get("why", "")).strip() or "Lineup worth checking.",
                "url": str(item.get("url", "")).strip() or "https://itk-so.vercel.app",
                "category": str(item.get("category", "")).strip() or "Music",
            }
        )
    return events


def search_venue_events_for_city(db: Session, city: str, force_refresh: bool = False) -> int:
    normalized_city = normalize_city(city)
    if normalized_city not in PILOT_CITIES:
        return 0

    venues = db.scalars(
        select(CityVenue).where(CityVenue.city == normalized_city, CityVenue.venue_type == "music").order_by(CityVenue.venue_name.asc())
    ).all()
    if not venues:
        discover_major_music_venues(db, normalized_city, force_refresh=False)
        venues = db.scalars(
            select(CityVenue)
            .where(CityVenue.city == normalized_city, CityVenue.venue_type == "music")
            .order_by(CityVenue.venue_name.asc())
        ).all()

    now = datetime.now(tz=timezone.utc)
    processed = 0
    for venue in venues:
        if (
            not force_refresh
            and venue.last_events_searched
            and venue.last_events_searched > now - timedelta(days=6)
            and venue.cached_events
        ):
            continue

        result = openrouter_client.chat(
            prompt=(
                f"List upcoming events at {venue.venue_name} in {normalized_city.title()}, Texas for the next 14 days.\n"
                "Return strict JSON array with keys: name, date, location, price, why, url, category.\n"
                "If exact data is uncertain, still return best known likely events with concise notes."
            ),
            system_prompt="Return strict JSON only.",
        )
        parsed_events = _parse_events(result, normalized_city, venue.venue_name)
        if not parsed_events:
            parsed_events = _fallback_venue_events(normalized_city, venue.venue_name)

        venue.cached_events = parsed_events[:6]
        venue.last_events_searched = now
        processed += 1

    db.commit()
    return processed


def search_venue_events(db: Session, city: str | None = None, force_refresh: bool = False) -> int:
    if city:
        return search_venue_events_for_city(db, city=city, force_refresh=force_refresh)

    total = 0
    for pilot_city in PILOT_CITIES:
        total += search_venue_events_for_city(db, city=pilot_city, force_refresh=force_refresh)
    return total


def get_cached_venue_events_for_city(db: Session, city: str, limit: int = 8) -> list[dict]:
    normalized_city = normalize_city(city)
    venues = db.scalars(
        select(CityVenue).where(CityVenue.city == normalized_city, CityVenue.venue_type == "music").order_by(CityVenue.venue_name.asc())
    ).all()

    events: list[dict] = []
    for venue in venues:
        for event in venue.cached_events[:3]:
            if not isinstance(event, dict):
                continue
            enriched = dict(event)
            if not enriched.get("location"):
                enriched["location"] = f"{venue.venue_name}, {normalized_city.title()}"
            if not enriched.get("category"):
                enriched["category"] = "Music"
            events.append(enriched)
            if len(events) >= limit:
                return events
    return events
