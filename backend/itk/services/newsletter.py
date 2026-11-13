"""Draft and send each subscriber's weekly issue.

Drafting gathers everything ITK knows about a subscriber (parsed interests, the raw
free-text they wrote, goals, recent reply feedback, Spotify listening, calendar busy
windows), merges cached venue and interest events for their city, asks the writing model
for a subject line and a one-sentence intro, and renders the HTML.
"""

import logging
from datetime import datetime
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.cities import normalize_city, pilot_cities_label
from itk.config import get_settings
from itk.db import utcnow
from itk.models import Event, HobbyCityPair, HobbyTag, Newsletter, NewsletterFeedback, User, UserGoal
from itk.security import ONE_YEAR, make_signed_value
from itk.services.hobbies import latest_hobbies
from itk.services.integrations import get_calendar_busy_windows, get_recent_tracks
from itk.services.llm import llm, parse_json_object
from itk.services.mailer import extract_address, send_email
from itk.services.newsletter_template import IssueLinks, render_newsletter_html, truncate
from itk.services.oauth import get_access_token
from itk.services.venues import get_cached_venue_events_for_city

log = logging.getLogger(__name__)

PAIRS_PER_ISSUE = 4
EVENTS_PER_PAIR = 2
RECENT_FEEDBACK_LIMIT = 6

BANNED_PHRASES = (
    "what's actually worth leaving the house for",
    "what's worth leaving the house for",
    "fits your vibe",
    "doom-scrolling",
    "doom scrolling",
)

COPYWRITER_SYSTEM_PROMPT = "You are ITK's newsletter copywriter. Return strict minified JSON only."
VOICE_GUIDE = (
    "- Subject: 4-9 words, specific, intriguing, tweet-energy.\n"
    "- Intro: exactly one sentence, <= 24 words.\n"
    "- Voice: sharp, social, friend-in-a-group-chat. Natural Gen Z tone only.\n"
    "- Never use: yo, vibe, doom-scrolling, fits your vibe, what's worth leaving the house for, fam.\n"
    "- Gen Z slang is welcome where it lands naturally (bet, no cap, lowkey, hits different, "
    "let them cook, IYKYK, say less). Use it sparingly; never force it.\n"
    "- Ground the writing in real details from the events, the hobbies text and the goals text.\n"
)


def unsubscribe_url(user_id: UUID) -> str:
    token = make_signed_value(str(user_id), ttl_seconds=ONE_YEAR)
    return f"{get_settings().app_url.rstrip('/')}/api/unsubscribe?token={quote(token)}"


def reply_to_address(newsletter_id: UUID) -> str | None:
    """Plus-address the reply mailbox with the issue ID so replies can be matched to an issue."""
    base = extract_address(get_settings().resend_reply_to_email or "")
    local, _, domain = base.partition("@")
    local = local.strip().strip('"')
    if not local or not domain:
        return None
    tagged = f"{local}+{newsletter_id}"
    return f"{tagged}@{domain}" if len(tagged) <= 64 else None


def merge_events(*sources: list[Event]) -> list[Event]:
    """Concatenate event lists, dropping duplicates by (name, date, location)."""
    merged: list[Event] = []
    seen: set[tuple[str, str, str]] = set()
    for source in sources:
        for event in source:
            name, date, location = (str(event.get(k, "")).strip().lower() for k in ("name", "date", "location"))
            key = (name, date, location)
            if not name or key in seen:
                continue
            seen.add(key)
            merged.append(event)
    return merged


def clean_subject(subject: str, city: str, events: list[Event]) -> str:
    candidate = " ".join(subject.split()).strip(" -")
    if not candidate or any(term in candidate.lower() for term in BANNED_PHRASES):
        first = truncate(str(events[0].get("name", "weekend plans")), 38) if events else "weekend plans"
        candidate = f"{city}: {first}"
    return truncate(candidate, 78)


def clean_intro(intro: str, city: str) -> str:
    cleaned = " ".join(intro.split())
    for end, char in enumerate(cleaned):
        if char in ".!?" and (end + 1 == len(cleaned) or cleaned[end + 1] == " "):
            cleaned = cleaned[: end + 1]
            break
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    padded = f" {cleaned.lower()} "
    if not cleaned or " yo " in padded or " vibe" in padded or any(term in padded for term in BANNED_PHRASES):
        return f"This week in {city} has a few legit standouts that are actually worth your time."
    return truncate(cleaned, 190)


def derive_dating_preference(user: User, goals_raw_text: str, goal_types: list[str]) -> str:
    explicit = (user.dating_preference or "").strip().lower()
    if explicit in {"date_night_spots", "meeting_people", "both"}:
        return explicit
    if not any("dating" in str(goal).lower() for goal in goal_types):
        return "not_specified"
    text = goals_raw_text.lower()
    if any(term in text for term in ("meet people", "singles", "speed dating", "mixer")):
        return "meeting_people"
    if any(term in text for term in ("partner", "boyfriend", "girlfriend", "wife", "husband", "date night")):
        return "date_night_spots"
    return "both"


def _event_digest(events: list[Event]) -> str:
    rows = []
    for event in events[:6]:
        name = truncate(str(event.get("name", "Event")), 70)
        date = truncate(str(event.get("date", "TBA")), 45)
        location = truncate(str(event.get("location", "Local")), 50)
        blurb = truncate(str(event.get("description", "")), 90)
        rows.append(f"- {name} | {date} | {location} | {blurb}")
    return "\n".join(rows)


def build_copy_prompt(
    *,
    user: User,
    tags: list[str],
    hobbies_text: str,
    goals_text: str,
    dating_preference: str,
    feedback: list[str],
    events: list[Event],
    music: list[dict[str, object]],
    busy_windows: list[dict[str, object]],
) -> str:
    feedback_block = "\n".join(f"- {item}" for item in feedback) or "- none yet"
    return (
        "Create newsletter copy for a local-events product.\n"
        "Return strict JSON with keys: subject, intro.\n"
        f"Constraints:\n{VOICE_GUIDE}"
        f"User: name={user.name}, city={user.city}, concision={user.concision_pref}.\n"
        f"Hobby tags (for event search, not writing style): {tags}\n"
        f"Hobbies raw text (for personalization/tone): {hobbies_text}\n"
        f"Goals raw text (for personalization/tone): {goals_text}\n"
        f"Dating preference context: {dating_preference}\n"
        f"Recent feedback from prior newsletters:\n{feedback_block}\n"
        f"Events:\n{_event_digest(events)}\n"
        f"Spotify context: {music}\n"
        f"Calendar busy windows: {busy_windows}\n"
    )


def collect_events(db: Session, user: User, tags: list[str]) -> list[Event]:
    """Venue calendars first, then cached results for the subscriber's own interests, topped
    up with the city's most popular interests if they have few matches."""
    city_key = normalize_city(user.city)
    city_pairs = select(HobbyCityPair).join(HobbyTag).where(HobbyCityPair.city == city_key)
    own = db.scalars(city_pairs.where(HobbyTag.tag_name.in_(tags)).order_by(HobbyCityPair.frequency.desc())).all()
    popular = db.scalars(city_pairs.order_by(HobbyCityPair.frequency.desc()).limit(PAIRS_PER_ISSUE)).all()
    pairs = list(dict.fromkeys([*own, *popular]))[: max(PAIRS_PER_ISSUE, len(own))]
    pair_events = [event for pair in pairs for event in pair.cached_results[:EVENTS_PER_PAIR]]
    return merge_events(get_cached_venue_events_for_city(db, user.city), pair_events)


def recent_feedback(db: Session, user_id: UUID) -> list[str]:
    rows = db.scalars(
        select(NewsletterFeedback.rewritten_feedback)
        .where(NewsletterFeedback.user_id == user_id)
        .order_by(NewsletterFeedback.created_at.desc())
        .limit(RECENT_FEEDBACK_LIMIT)
    ).all()
    return [row.strip() for row in rows if row and row.strip()]


def draft_newsletter_for_user(db: Session, user: User, *, now: datetime | None = None) -> Newsletter | None:
    """Create an unsent issue for `user`. Returns None when there are no events to send."""
    hobbies = latest_hobbies(db, user.id)
    tags = list(hobbies.parsed_tags) if hobbies else []
    events = collect_events(db, user, tags)
    if not events:
        log.info("No cached events for %s yet; skipping issue for user %s", user.city, user.id)
        return None

    goals = db.scalars(select(UserGoal).where(UserGoal.user_id == user.id).order_by(UserGoal.created_at.desc())).first()
    goals_text = goals.raw_text if goals else ""
    goal_types = list(goals.goal_types) if goals else []

    spotify_token = get_access_token(db, user.id, "spotify")
    google_token = get_access_token(db, user.id, "google")

    prompt = build_copy_prompt(
        user=user,
        tags=tags,
        hobbies_text=hobbies.raw_text if hobbies else "",
        goals_text=goals_text,
        dating_preference=derive_dating_preference(user, goals_text, goal_types),
        feedback=recent_feedback(db, user.id),
        events=events,
        music=get_recent_tracks(spotify_token) if spotify_token else [],
        busy_windows=get_calendar_busy_windows(google_token) if google_token else [],
    )
    copy = parse_json_object(llm.write(prompt, system_prompt=COPYWRITER_SYSTEM_PROMPT))
    subject = clean_subject(str(copy.get("subject", "")), user.city, events)
    intro = clean_intro(str(copy.get("intro", "")), user.city)

    settings = get_settings()
    html = render_newsletter_html(
        user_name=user.name,
        city=user.city,
        intro_line=intro,
        events=events,
        generated_at=now or utcnow(),
        links=IssueLinks(
            app_url=settings.app_url,
            unsubscribe_url=unsubscribe_url(user.id),
            contact_email=extract_address(settings.resend_reply_to_email or settings.resend_from_email),
        ),
        footer_note=f"ITK curates local events for its pilot cities: {pilot_cities_label()}.",
    )

    newsletter = Newsletter(user_id=user.id, subject=subject, html_content=html, events_included=events)
    db.add(newsletter)
    db.commit()
    return newsletter


def draft_newsletters(db: Session, user_id: UUID | None = None) -> int:
    """Draft issues for every subscribed user (or one user). Returns how many were drafted."""
    query = select(User).where(User.is_subscribed.is_(True))
    if user_id:
        query = query.where(User.id == user_id)
    return sum(1 for user in db.scalars(query).all() if draft_newsletter_for_user(db, user))


def send_newsletters(db: Session, user_id: UUID | None = None) -> int:
    """Send every drafted-but-unsent issue (or one user's). Returns how many were delivered."""
    query = select(Newsletter).where(Newsletter.sent_at.is_(None))
    if user_id:
        query = query.where(Newsletter.user_id == user_id)

    sent = 0
    for newsletter in db.scalars(query).all():
        user = db.get(User, newsletter.user_id)
        if not user or not user.is_subscribed:
            continue
        delivered = send_email(
            user.email,
            newsletter.subject,
            newsletter.html_content,
            reply_to=reply_to_address(newsletter.id),
            headers={"List-Unsubscribe": f"<{unsubscribe_url(user.id)}>"},
        )
        if delivered:
            newsletter.sent_at = utcnow()
            sent += 1
    db.commit()
    return sent
