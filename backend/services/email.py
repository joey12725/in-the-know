from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from models import HobbyCityPair, Newsletter, OAuthToken, User, UserHobby
from services.ai import openrouter_client
from services.google_cal import get_calendar_availability
from services.spotify import get_recent_tracks
from services.token_crypto import cipher


def _render_fallback_html(user_name: str, city: str, events: list[dict]) -> str:
    event_rows = "".join(
        [
            f"<li><strong>{event.get('name', 'Event')}</strong> - {event.get('date', 'TBD')} - {event.get('location', city)}</li>"
            for event in events
        ]
    )
    return (
        "<html><body style='font-family:Arial,sans-serif;background:#f7f7f7;padding:24px;'>"
        f"<div style='max-width:600px;margin:0 auto;background:white;border-radius:16px;padding:24px;'>"
        f"<h1 style='margin:0 0 12px;'>Your ITK Weekly Picks, {user_name}</h1>"
        f"<p style='margin:0 0 12px;'>Here are events in {city} picked for you.</p>"
        f"<ul>{event_rows}</ul>"
        "</div></body></html>"
    )


def _collect_music_context(db: Session, user: User) -> list[dict]:
    spotify_token = db.scalar(
        select(OAuthToken).where(OAuthToken.user_id == user.id, OAuthToken.provider == "spotify")
    )
    if not spotify_token:
        return []
    try:
        access_token = cipher.decrypt(spotify_token.access_token)
    except Exception:
        access_token = spotify_token.access_token
    return get_recent_tracks(access_token)


def _collect_calendar_context(db: Session, user: User) -> list[dict]:
    google_token = db.scalar(select(OAuthToken).where(OAuthToken.user_id == user.id, OAuthToken.provider == "google"))
    if not google_token:
        return []
    try:
        access_token = cipher.decrypt(google_token.access_token)
    except Exception:
        access_token = google_token.access_token
    return get_calendar_availability(access_token)


def draft_newsletter_for_user(db: Session, user: User) -> Newsletter:
    latest_hobbies = db.scalars(
        select(UserHobby).where(UserHobby.user_id == user.id).order_by(UserHobby.created_at.desc())
    ).first()
    tags = latest_hobbies.parsed_tags if latest_hobbies else []

    pairs = db.scalars(
        select(HobbyCityPair).where(HobbyCityPair.city == user.city.lower()).order_by(HobbyCityPair.frequency.desc()).limit(4)
    ).all()

    events: list[dict] = []
    for pair in pairs:
        events.extend(pair.cached_results[:2])
    if not events:
        events = [
            {"name": "City event roundup", "date": "This week", "location": user.city, "url": "https://itk-so.vercel.app"}
        ]

    music_context = _collect_music_context(db, user)
    busy_windows = _collect_calendar_context(db, user)

    prompt = (
        "Write a polished, modern weekly events newsletter in HTML. "
        "Include a short intro, bullet list of events, and closing CTA. "
        f"User name: {user.name}. City: {user.city}. Concision: {user.concision_pref}. "
        f"Hobby tags: {tags}. Events: {events}. "
        f"Spotify context: {music_context}. Busy windows: {busy_windows}."
    )
    html = openrouter_client.chat(prompt=prompt, system_prompt="Return only HTML.")
    if not html or "<" not in html:
        html = _render_fallback_html(user_name=user.name, city=user.city, events=events)

    newsletter = Newsletter(
        user_id=user.id,
        subject=f"{user.name}, your week in {user.city}",
        html_content=html,
        events_included=events,
    )
    db.add(newsletter)
    db.commit()
    db.refresh(newsletter)
    return newsletter


def draft_newsletters(db: Session, user_id: UUID | None = None) -> int:
    query = select(User)
    if user_id:
        query = query.where(User.id == user_id)
    users = db.scalars(query).all()
    for user in users:
        draft_newsletter_for_user(db, user)
    return len(users)


def _send_email_via_resend(to_email: str, subject: str, html_content: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        return

    with httpx.Client(timeout=20) as client:
        response = client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json"},
            json={
                "from": settings.resend_from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            },
        )
        response.raise_for_status()


def send_newsletters(db: Session, user_id: UUID | None = None) -> int:
    query = select(Newsletter).where(Newsletter.sent_at.is_(None))
    if user_id:
        query = query.where(Newsletter.user_id == user_id)

    newsletters = db.scalars(query).all()
    sent_count = 0
    for newsletter in newsletters:
        user = db.get(User, newsletter.user_id)
        if not user:
            continue
        _send_email_via_resend(user.email, newsletter.subject, newsletter.html_content)
        newsletter.sent_at = datetime.now(tz=timezone.utc)
        sent_count += 1

    db.commit()
    return sent_count
