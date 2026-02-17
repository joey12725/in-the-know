from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User
from services.email import draft_newsletters, send_newsletters
from services.events import search_events_for_pairs
from services.hobbies import parse_and_store_user_hobbies
from services.venues import discover_pilot_city_venues, search_venue_events


def run_weekly_pipeline(db: Session) -> dict:
    errors = []
    
    # Parse user hobbies
    users = []
    parsed_count = 0
    try:
        users = db.scalars(select(User)).all()
        for user in users:
            tags = parse_and_store_user_hobbies(db, user.id)
            if tags:
                parsed_count += 1
    except Exception as e:
        errors.append(f"parse_hobbies: {str(e)}")

    # Search event pairs
    pairs_processed = 0
    try:
        pairs_processed = search_events_for_pairs(db)
    except Exception as e:
        errors.append(f"search_pairs: {str(e)}")

    # Discover venues
    discovered_venues = 0
    try:
        discovered_venues = discover_pilot_city_venues(db)
    except Exception as e:
        errors.append(f"discover_venues: {str(e)}")

    # Search venue events
    searched_venue_events = 0
    try:
        searched_venue_events = search_venue_events(db)
    except Exception as e:
        errors.append(f"search_venue_events: {str(e)}")

    # Draft newsletters
    drafted = 0
    try:
        drafted = draft_newsletters(db)
    except Exception as e:
        errors.append(f"draft_newsletters: {str(e)}")

    # Send newsletters
    sent = 0
    try:
        sent = send_newsletters(db)
    except Exception as e:
        errors.append(f"send_newsletters: {str(e)}")

    result = {
        "users_seen": len(users),
        "parsed_hobbies": parsed_count,
        "searched_pairs": pairs_processed,
        "discovered_venues": discovered_venues,
        "searched_venue_events": searched_venue_events,
        "drafted_newsletters": drafted,
        "sent_newsletters": sent,
    }
    
    if errors:
        result["errors"] = errors
    
    return result
