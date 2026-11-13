"""Venue-first event discovery for pilot cities.

Generic "music events in Austin" searches miss a lot. Instead, ITK keeps a list of each
pilot city's major venues (refreshed monthly) and searches each venue's calendar weekly.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.cities import normalize_city, pilot_cities
from itk.db import as_utc, utcnow
from itk.models import CityVenue, Event
from itk.services.events import EVENT_SEARCH_SYSTEM_PROMPT, parse_events
from itk.services.llm import llm, parse_json_array

VENUE_LIST_TTL = timedelta(days=30)
VENUE_EVENTS_TTL = timedelta(days=6)
MAX_EVENTS_PER_VENUE = 6

# Used when the venue-discovery model call is unavailable (no API key) or returns nothing.
# (city, venue name, address, website)
_SEED_VENUE_ROWS = (
    ("austin", "Mohawk Austin", "912 Red River St, Austin, TX", "https://mohawkaustin.com"),
    ("austin", "ACL Live at The Moody Theater", "310 W Willie Nelson Blvd, Austin, TX", "https://acllive.com"),
    ("austin", "Stubb's Waller Creek Amphitheater", "801 Red River St, Austin, TX", "https://www.stubbsaustin.com"),
    ("austin", "Emo's Austin", "2015 E Riverside Dr, Austin, TX", "https://www.emosaustin.com"),
    ("austin", "Scoot Inn", "1308 E 4th St, Austin, TX", "https://www.scootinnaustin.com"),
    ("san antonio", "The Aztec Theatre", "104 N St Mary's St, San Antonio, TX", "https://www.aztectheatre.com"),
    (
        "san antonio",
        "Tobin Center for the Performing Arts",
        "100 Auditorium Cir, San Antonio, TX",
        "https://www.tobincenter.org",
    ),
    ("san antonio", "Paper Tiger", "2410 N St Mary's St, San Antonio, TX", "https://papertigersa.com"),
    ("san antonio", "Sam's Burger Joint", "330 E Grayson St, San Antonio, TX", "https://samsburgerjoint.com"),
    ("san antonio", "Stable Hall", "307 Pearl Pkwy, San Antonio, TX", "https://stablehall.com"),
)
SEED_VENUES: dict[str, list[dict[str, str]]] = {}
for _city, _name, _address, _website in _SEED_VENUE_ROWS:
    SEED_VENUES.setdefault(_city, []).append({"venue_name": _name, "address": _address, "website": _website})


def _parse_venues(text: str) -> list[dict[str, Any]]:
    venues: list[dict[str, Any]] = []
    for item in parse_json_array(text):
        if isinstance(item, str) and item.strip():
            venues.append({"venue_name": item.strip()})
        elif isinstance(item, dict) and str(item.get("venue_name") or "").strip():
            venues.append(
                {
                    "venue_name": str(item["venue_name"]).strip(),
                    "address": str(item.get("address") or "").strip() or None,
                    "website": str(item.get("website") or "").strip() or None,
                }
            )
    return venues


def _music_venues(db: Session, city: str) -> list[CityVenue]:
    return list(
        db.scalars(
            select(CityVenue)
            .where(CityVenue.city == city, CityVenue.venue_type == "music")
            .order_by(CityVenue.venue_name.asc())
        ).all()
    )


def discover_major_music_venues(db: Session, city: str, force_refresh: bool = False) -> int:
    city_key = normalize_city(city)
    if city_key not in pilot_cities():
        return 0

    now = utcnow()
    existing = _music_venues(db, city_key)
    newest = max((dt for v in existing if (dt := as_utc(v.last_searched))), default=None)
    if existing and not force_refresh and newest and newest > now - VENUE_LIST_TTL:
        return 0

    try:
        reply = llm.chat(
            prompt=(
                f"List major live music venues in {city_key.title()}.\n"
                "Return strict JSON array of objects with keys: venue_name, address, website.\n"
                "Keep only established venues with frequent live shows."
            ),
            system_prompt="Return strict JSON only.",
        )
        discovered = _parse_venues(reply)
    except Exception:
        discovered = []
    discovered = discovered or SEED_VENUES.get(city_key, [])

    by_name = {venue.venue_name.strip().lower(): venue for venue in existing}
    touched = 0
    for data in discovered:
        name = data["venue_name"]
        venue = by_name.get(name.lower())
        if venue is None:
            venue = CityVenue(city=city_key, venue_name=name, venue_type="music", cached_events=[])
            db.add(venue)
            by_name[name.lower()] = venue
        venue.address = data.get("address")
        venue.website = data.get("website")
        venue.last_searched = now
        touched += 1

    db.commit()
    return touched


def discover_pilot_city_venues(db: Session, force_refresh: bool = False) -> int:
    return sum(discover_major_music_venues(db, city, force_refresh=force_refresh) for city in pilot_cities())


def search_venue_events_for_city(db: Session, city: str, force_refresh: bool = False) -> int:
    city_key = normalize_city(city)
    if city_key not in pilot_cities():
        return 0

    venues = _music_venues(db, city_key)
    if not venues:
        discover_major_music_venues(db, city_key)
        venues = _music_venues(db, city_key)

    now = utcnow()
    processed = 0
    for venue in venues:
        last = as_utc(venue.last_events_searched)
        if not force_refresh and venue.cached_events and last and last > now - VENUE_EVENTS_TTL:
            continue
        try:
            reply = llm.search(
                prompt=(
                    f"List upcoming events at {venue.venue_name} in {city_key.title()} for the next 14 days.\n"
                    "Return strict JSON array with keys: name, date, location, price, description, url, "
                    "category, cta."
                ),
                system_prompt=EVENT_SEARCH_SYSTEM_PROMPT,
            )
            events = parse_events(reply, location=f"{venue.venue_name}, {city_key.title()}", category="Music")
        except Exception:
            events = []

        venue.cached_events = events[:MAX_EVENTS_PER_VENUE]
        venue.last_events_searched = now
        processed += 1

    db.commit()
    return processed


def search_venue_events(db: Session, city: str | None = None, force_refresh: bool = False) -> int:
    cities = [city] if city else pilot_cities()
    return sum(search_venue_events_for_city(db, c, force_refresh=force_refresh) for c in cities)


def get_cached_venue_events_for_city(db: Session, city: str, limit: int = 8, per_venue: int = 3) -> list[Event]:
    city_key = normalize_city(city)
    events: list[Event] = []
    for venue in _music_venues(db, city_key):
        for event in venue.cached_events[:per_venue]:
            if not isinstance(event, dict):
                continue
            enriched = dict(event)
            enriched["location"] = enriched.get("location") or f"{venue.venue_name}, {city_key.title()}"
            enriched["category"] = enriched.get("category") or "Music"
            events.append(enriched)
            if len(events) >= limit:
                return events
    return events
