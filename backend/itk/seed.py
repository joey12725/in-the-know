"""Fabricated demo data: a handful of subscribers plus cached events, so the full
draft-and-send loop runs locally with no API keys. Every person, venue and event here
is made up."""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.cities import normalize_city
from itk.db import utcnow
from itk.models import CityVenue, Event, HobbyCityPair, User, UserGoal, UserHobby
from itk.security import generate_random_token
from itk.services.hobbies import get_or_create_hobby_tag


@dataclass(frozen=True)
class DemoSubscriber:
    name: str
    email: str
    city: str
    address: str
    hobbies: str
    tags: tuple[str, ...]
    goals: str
    goal_types: tuple[str, ...]
    dating_preference: str | None = None
    concision: str = "brief"


SUBSCRIBERS = (
    DemoSubscriber(
        name="Maya Torres",
        email="maya.torres@example.com",
        city="Austin",
        address="100 Example Ave, Austin, TX",
        hobbies="live indie music, natural wine, pottery classes, trail running on weekends",
        tags=("live indie music", "natural wine", "pottery", "trail running"),
        goals="Meet people who are also into running and find a pottery studio to join.",
        goal_types=("friends", "hobby-growth"),
    ),
    DemoSubscriber(
        name="Devin Park",
        email="devin.park@example.com",
        city="San Antonio",
        address="200 Sample St, San Antonio, TX",
        hobbies="jazz, food trucks, film photography, board game nights",
        tags=("jazz", "food trucks", "film photography", "board games"),
        goals="Good date night spots with my partner, and maybe a photo walk group.",
        goal_types=("dating", "community"),
        dating_preference="date_night_spots",
        concision="detailed",
    ),
    DemoSubscriber(
        name="Priya Shah",
        email="priya.shah@example.com",
        city="Austin",
        address="300 Placeholder Blvd, Austin, TX",
        hobbies="climbing, startup meetups, volunteering at animal shelters, salsa",
        tags=("climbing", "startup meetups", "volunteering", "salsa"),
        goals="New in town. I want to meet people and give back.",
        goal_types=("friends", "charity"),
    ),
)


def _event(days: int, hour: str, **fields: str) -> Event:
    day = utcnow() + timedelta(days=days)
    return {"date": f"{day:%a %b} {day.day}, {hour}", "price": "$15", "cta": "Get tickets", **fields}


# Interest -> city -> events found by the (simulated) weekly search.
PAIR_EVENTS: dict[tuple[str, str], list[Event]] = {
    ("live indie music", "austin"): [
        _event(2, "8:00 PM", name="Porchlight Sessions", location="The Cedar Room",
               description="Three local bands, short sets, and a patio that stays open late.",
               url="https://example.com/events/porchlight", category="Music"),
    ],
    ("natural wine", "austin"): [
        _event(3, "6:30 PM", name="Skin-Contact Flight Night", location="Lowland Wine Bar", price="$28",
               description="Six orange wines poured by the importer, with snacks from the bar's kitchen.",
               url="https://example.com/events/flight-night", category="Food", cta="Reserve"),
    ],
    ("pottery", "austin"): [
        _event(5, "2:00 PM", name="Wheel Throwing Drop-In", location="Kiln & Co. Studio", price="$45",
               description="Two hours on the wheel with an instructor. Pieces are fired and ready in two weeks.",
               url="https://example.com/events/wheel-drop-in", category="Arts", cta="Book a wheel"),
    ],
    ("trail running", "austin"): [
        _event(4, "7:00 AM", name="Sunrise Greenbelt 5 Miler", location="Oak Hollow Trailhead", price="Free",
               description="No-drop group run with a coffee stop at the end. All paces welcome.",
               url="https://example.com/events/sunrise-run", category="Outdoors", cta="RSVP"),
    ],
    ("jazz", "san antonio"): [
        _event(2, "9:00 PM", name="Late Set at the Blue Lantern", location="The Blue Lantern", price="$20",
               description="A quartet playing hard bop until midnight. Get there early for a booth.",
               url="https://example.com/events/late-set", category="Music"),
    ],
    ("food trucks", "san antonio"): [
        _event(3, "5:00 PM", name="River Lot Night Market", location="River Lot", price="Free",
               description="Twenty trucks, string lights and a cumbia DJ. Bring cash for the dessert stalls.",
               url="https://example.com/events/night-market", category="Food", cta="See vendors"),
    ],
    ("film photography", "san antonio"): [
        _event(6, "10:00 AM", name="Half-Frame Photo Walk", location="Mission Arts District", price="$10",
               description="A guided walk for film shooters, ending with a darkroom demo.",
               url="https://example.com/events/photo-walk", category="Arts", cta="Sign up"),
    ],
}  # fmt: skip

VENUE_EVENTS: dict[tuple[str, str], list[Event]] = {
    ("austin", "The Cedar Room"): [
        _event(1, "9:00 PM", name="Hollow Pines Album Release", location="The Cedar Room", price="$18",
               description="The local five-piece plays their new record front to back.",
               url="https://example.com/events/hollow-pines", category="Music"),
    ],
    ("san antonio", "The Blue Lantern"): [
        _event(4, "8:00 PM", name="Vinyl & Vermouth", location="The Blue Lantern", price="$12",
               description="Bring a record, the DJ plays it. Vermouth spritzes all night.",
               url="https://example.com/events/vinyl-vermouth", category="Music"),
    ],
}  # fmt: skip


def seed(db: Session) -> int:
    """Insert the demo data. Safe to run repeatedly; returns how many subscribers were added."""
    now = utcnow()
    added = 0
    for sub in SUBSCRIBERS:
        if db.scalar(select(User).where(User.email == sub.email)):
            continue
        user = User(
            name=sub.name,
            email=sub.email,
            address=sub.address,
            city=sub.city,
            concision_pref=sub.concision,
            dating_preference=sub.dating_preference,
            onboarding_token=generate_random_token(24),
        )
        db.add(user)
        db.flush()
        db.add(UserHobby(user_id=user.id, raw_text=sub.hobbies, parsed_tags=list(sub.tags)))
        db.add(UserGoal(user_id=user.id, raw_text=sub.goals, goal_types=list(sub.goal_types)))
        added += 1

    for (tag_name, city), events in PAIR_EVENTS.items():
        tag = get_or_create_hobby_tag(db, tag_name)
        pair = db.scalar(select(HobbyCityPair).where(HobbyCityPair.hobby_tag_id == tag.id, HobbyCityPair.city == city))
        if pair is None:
            pair = HobbyCityPair(hobby_tag_id=tag.id, city=city, frequency=1)
            db.add(pair)
        pair.cached_results = events
        pair.last_searched = now

    for (city, venue_name), events in VENUE_EVENTS.items():
        city_key = normalize_city(city)
        venue = db.scalar(select(CityVenue).where(CityVenue.city == city_key, CityVenue.venue_name == venue_name))
        if venue is None:
            venue = CityVenue(city=city_key, venue_name=venue_name, venue_type="music")
            db.add(venue)
        venue.cached_events = events
        venue.last_searched = now
        venue.last_events_searched = now

    db.commit()
    return added
