from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User
from services.email import draft_newsletters, send_newsletters
from services.events import search_events_for_pairs
from services.hobbies import parse_and_store_user_hobbies
from services.venues import discover_pilot_city_venues, search_venue_events


def run_weekly_pipeline(db: Session) -> dict:
    users = db.scalars(select(User)).all()
    parsed_count = 0
    for user in users:
        tags = parse_and_store_user_hobbies(db, user.id)
        if tags:
            parsed_count += 1

    pairs_processed = search_events_for_pairs(db)
    discovered_venues = discover_pilot_city_venues(db)
    searched_venue_events = search_venue_events(db)
    drafted = draft_newsletters(db)
    sent = send_newsletters(db)

    return {
        "users_seen": len(users),
        "parsed_hobbies": parsed_count,
        "searched_pairs": pairs_processed,
        "discovered_venues": discovered_venues,
        "searched_venue_events": searched_venue_events,
        "drafted_newsletters": drafted,
        "sent_newsletters": sent,
    }
