from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from html import escape
import json
import re
from urllib.parse import quote_plus
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from models import HobbyCityPair, Newsletter, OAuthToken, User, UserGoal, UserHobby
from services.ai import openrouter_client
from services.google_cal import get_calendar_availability
from services.spotify import get_recent_tracks
from services.token_crypto import cipher


def _extract_email_address(value: str) -> str:
    match = re.search(r"<([^>]+)>", value)
    if match:
        return match.group(1).strip()
    return value.strip()


def _truncate(value: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "..."


def _infer_category(event: dict) -> str:
    for key in ("category", "type"):
        raw = str(event.get(key, "")).strip()
        if raw:
            return raw.title()

    haystack = f"{event.get('name', '')} {event.get('why', '')}".lower()
    keyword_map = (
        ("Music", ("music", "concert", "dj", "band", "show", "live")),
        ("Food", ("food", "tasting", "brunch", "dinner", "restaurant", "market")),
        ("Social", ("mixer", "social", "networking", "meetup", "singles")),
        ("Outdoors", ("hike", "run", "trail", "outdoor", "park", "bike")),
        ("Arts", ("gallery", "museum", "art", "film", "photo", "theater")),
        ("Fitness", ("fitness", "yoga", "pilates", "workout", "wellness")),
    )
    for category, words in keyword_map:
        if any(word in haystack for word in words):
            return category
    return "Featured"


def _category_emoji(category: str) -> str:
    key = category.lower()
    if key == "music":
        return "🎵"
    if key == "food":
        return "🍽️"
    if key == "social":
        return "🤝"
    if key == "outdoors":
        return "🌿"
    if key == "arts":
        return "🎨"
    if key == "fitness":
        return "💪"
    return "✨"


def _infer_price_indicator(event: dict) -> str:
    for key in ("price_indicator", "price", "cost"):
        raw = str(event.get(key, "")).strip().lower()
        if raw in {"$", "$$", "$$$", "$$$$"}:
            return raw
        if "free" in raw:
            return "Free"
        digits = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
        if digits:
            try:
                amount = float(digits)
                if amount == 0:
                    return "Free"
                if amount <= 15:
                    return "$"
                if amount <= 40:
                    return "$$"
                if amount <= 100:
                    return "$$$"
                return "$$$$"
            except ValueError:
                continue
    return "$$"


def _format_event_date(event: dict) -> str:
    raw = str(event.get("date", "")).strip()
    if not raw:
        return "Date TBA"
    return raw


def _build_event_groups(events: list[dict], city: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events[:8]:
        category = _infer_category(event)
        grouped[category].append(
            {
                "name": _truncate(str(event.get("name", "Event")).strip() or "Event", 90),
                "date": _format_event_date(event),
                "location": _truncate(str(event.get("location", city)).strip() or city, 80),
                "price": _infer_price_indicator(event),
                "summary": _truncate(str(event.get("why", "Worth checking out this week.")).strip(), 170),
                "url": str(event.get("url", "")).strip() or "https://itk-so.vercel.app",
            }
        )
    if not grouped:
        grouped["Featured"] = [
            {
                "name": "City event roundup",
                "date": "This week",
                "location": city,
                "price": "$$",
                "summary": "Fresh picks are loading in now. Open ITK for the latest schedule.",
                "url": "https://itk-so.vercel.app",
            }
        ]
    return grouped


def _sanitize_subject(subject: str, city: str, events: list[dict]) -> str:
    banned_terms = ("what's actually worth leaving the house for", "fits your vibe", "doom-scrolling", "doom scrolling")
    candidate = " ".join(subject.replace("\n", " ").split()).strip(" -")
    lowered = candidate.lower()
    if not candidate or any(term in lowered for term in banned_terms):
        first_event = _truncate(str(events[0].get("name", "weekend plans")).strip(), 38) if events else "weekend plans"
        candidate = f"{city}: {first_event}"
    if len(candidate) > 78:
        candidate = _truncate(candidate, 78)
    return candidate


def _sanitize_intro(intro: str, city: str) -> str:
    banned_terms = (" yo ", " vibe", "doom-scrolling", "doom scrolling", "fits your vibe", "what's worth leaving the house for")
    cleaned = " ".join(intro.replace("\n", " ").split())
    sentence_parts = re.split(r"(?<=[.!?])\s+", cleaned)
    one_sentence = sentence_parts[0].strip() if sentence_parts else cleaned.strip()
    if one_sentence and one_sentence[-1] not in ".!?":
        one_sentence = f"{one_sentence}."
    lowered = f" {one_sentence.lower()} "
    if not one_sentence or any(term in lowered for term in banned_terms):
        return f"This week in {city} has a few legit standouts that are actually worth your time."
    return _truncate(one_sentence, 190)


def _event_digest(events: list[dict]) -> str:
    rows: list[str] = []
    for event in events[:6]:
        name = _truncate(str(event.get("name", "Event")).strip(), 70)
        date = _truncate(str(event.get("date", "TBA")).strip(), 45)
        location = _truncate(str(event.get("location", "Local")).strip(), 50)
        why = _truncate(str(event.get("why", "")).strip(), 90)
        rows.append(f"- {name} | {date} | {location} | {why}")
    return "\n".join(rows)


def _generate_newsletter_copy(
    user: User,
    tags: list[str],
    hobby_raw_text: str,
    goals_raw_text: str,
    events: list[dict],
    music_context: list[dict],
    busy_windows: list[dict],
) -> tuple[str, str]:
    prompt = (
        "Create newsletter copy for a local-events product.\n"
        "Return strict JSON with keys: subject, intro.\n"
        "Constraints:\n"
        "- Subject: 4-9 words, specific, intriguing, tweet-energy.\n"
        "- Intro: exactly one sentence, <= 24 words.\n"
        "- Voice: sharp, social, friend-in-a-group-chat. Natural Gen Z tone only.\n"
        "- Never use: yo, vibe, doom-scrolling, fits your vibe, what's worth leaving the house for.\n"
        "- Ground writing in real details from events, hobbies raw text, and goals raw text.\n"
        f"User: name={user.name}, city={user.city}, concision={user.concision_pref}.\n"
        f"Hobby tags (search labels): {tags}\n"
        f"Hobbies raw text (personalization context): {hobby_raw_text}\n"
        f"Goals raw text (personalization context): {goals_raw_text}\n"
        f"Events:\n{_event_digest(events)}\n"
        f"Spotify context: {music_context}\n"
        f"Calendar busy windows: {busy_windows}\n"
    )
    result = openrouter_client.chat(
        prompt=prompt,
        system_prompt="You are ITK's newsletter copywriter. Return strict minified JSON only.",
    )

    subject = ""
    intro = ""
    if result:
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict):
                subject = str(parsed.get("subject", "")).strip()
                intro = str(parsed.get("intro", "")).strip()
        except json.JSONDecodeError:
            pass

    sanitized_subject = _sanitize_subject(subject, user.city, events)
    sanitized_intro = _sanitize_intro(intro, user.city)
    return sanitized_subject, sanitized_intro


def _render_newsletter_html(
    user_name: str,
    city: str,
    intro_line: str,
    events: list[dict],
    generated_at: datetime,
) -> str:
    settings = get_settings()
    app_url = settings.app_url.rstrip("/")
    from_email = _extract_email_address(settings.resend_from_email)
    unsubscribe_url = f"{app_url}/unsubscribe?email={quote_plus(from_email)}"
    grouped_events = _build_event_groups(events, city)

    rendered_sections: list[str] = []
    for category, category_events in grouped_events.items():
        emoji = _category_emoji(category)
        cards = []
        for event in category_events:
            cards.append(
                (
                    "<tr>"
                    "<td style=\"padding:0 0 16px 0;\">"
                    "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
                    "style=\"border:1px solid #dbe5ff;border-radius:14px;background:#f8faff;\">"
                    "<tr><td style=\"padding:16px 16px 10px 16px;\">"
                    "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
                    "<tr>"
                    f"<td style=\"font-size:20px;line-height:1.2;font-weight:700;color:#111827;\">{escape(event['name'])}</td>"
                    f"<td align=\"right\" style=\"font-size:13px;font-weight:700;color:#1d4ed8;white-space:nowrap;\">{escape(event['price'])}</td>"
                    "</tr>"
                    "</table>"
                    f"<p style=\"margin:10px 0 0 0;font-size:14px;line-height:1.5;color:#334155;\">🗓️ {escape(event['date'])}</p>"
                    f"<p style=\"margin:4px 0 0 0;font-size:14px;line-height:1.5;color:#334155;\">📍 {escape(event['location'])}</p>"
                    f"<p style=\"margin:10px 0 0 0;font-size:15px;line-height:1.55;color:#111827;\">{escape(event['summary'])}</p>"
                    "<p style=\"margin:14px 0 0 0;\">"
                    f"<a href=\"{escape(event['url'])}\" "
                    "style=\"display:inline-block;background:#1d4ed8;color:#ffffff;text-decoration:none;"
                    "font-size:14px;font-weight:700;padding:10px 14px;border-radius:10px;\">Open Event</a>"
                    "</p>"
                    "</td></tr></table></td></tr>"
                )
            )
        rendered_sections.append(
            (
                "<tr><td style=\"padding:2px 0 12px 0;\">"
                "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
                "<tr>"
                f"<td style=\"font-size:13px;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;color:#1d4ed8;\">{emoji} {escape(category)}</td>"
                "<td style=\"border-bottom:1px solid #dbe5ff;\">&nbsp;</td>"
                "</tr>"
                "</table>"
                "</td></tr>"
                + "".join(cards)
            )
        )

    preview = escape(_truncate(intro_line, 90))
    city_display = escape(city)
    issue_date = generated_at.strftime("%b %-d, %Y")
    return (
        "<!doctype html>"
        "<html><head><meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        "<style>"
        "@media only screen and (max-width: 640px) {"
        " .wrapper {width:100% !important;}"
        " .shell {padding:14px !important;}"
        " .card {padding:18px !important;}"
        " .title {font-size:26px !important; line-height:1.2 !important;}"
        "}"
        "</style></head>"
        "<body style=\"margin:0;padding:0;background:#eef2ff;font-family:'Inter','Avenir Next','Segoe UI',Arial,sans-serif;color:#111827;\">"
        f"<div style=\"display:none;max-height:0;overflow:hidden;opacity:0;\">{preview}</div>"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#eef2ff;\">"
        "<tr><td class=\"shell\" style=\"padding:22px 12px;\">"
        "<table class=\"wrapper\" role=\"presentation\" width=\"620\" align=\"center\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:620px;max-width:620px;\">"
        "<tr><td class=\"card\" style=\"background:#ffffff;border-radius:18px;padding:26px 22px;border:1px solid #dbe5ff;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
        "<tr><td style=\"padding-bottom:18px;border-bottom:1px solid #e5e7eb;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
        "<tr>"
        "<td>"
        "<p style=\"margin:0;font-size:12px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#1d4ed8;\">ITK Weekly</p>"
        f"<p style=\"margin:8px 0 0 0;font-size:13px;color:#475569;\">{city_display} local briefing</p>"
        "</td>"
        "<td align=\"right\" style=\"font-size:13px;color:#64748b;\">"
        f"{escape(issue_date)}"
        "</td>"
        "</tr></table></td></tr>"
        "<tr><td style=\"padding-top:18px;\">"
        f"<h1 class=\"title\" style=\"margin:0;font-size:31px;line-height:1.15;color:#0f172a;\">{escape(user_name)}, your week in {city_display}</h1>"
        f"<p style=\"margin:12px 0 18px 0;font-size:16px;line-height:1.5;color:#1f2937;\">{escape(intro_line)}</p>"
        "<p style=\"margin:0 0 20px 0;font-size:13px;line-height:1.5;color:#475569;\">Quick scan format: category sections, concise event cards, direct links.</p>"
        "</td></tr>"
        + "".join(rendered_sections)
        + "<tr><td style=\"padding-top:10px;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f8fafc;border-radius:14px;border:1px solid #e2e8f0;\">"
        "<tr><td style=\"padding:14px;\">"
        "<p style=\"margin:0;font-size:14px;line-height:1.5;color:#0f172a;\">Want this to get sharper next week? Reply to this email and tell us what to include less or more of.</p>"
        f"<p style=\"margin:10px 0 0 0;font-size:13px;line-height:1.5;color:#334155;\">Or message us directly at <a href=\"mailto:{escape(from_email)}\" style=\"color:#1d4ed8;text-decoration:none;\">{escape(from_email)}</a>.</p>"
        "</td></tr></table></td></tr>"
        "<tr><td style=\"padding-top:22px;border-top:1px solid #e5e7eb;\">"
        "<p style=\"margin:0;font-size:12px;line-height:1.6;color:#64748b;\">ITK curates local events for pilot cities: Austin and San Antonio.</p>"
        "<p style=\"margin:8px 0 0 0;font-size:12px;line-height:1.6;color:#64748b;\">"
        f"<a href=\"{escape(unsubscribe_url)}\" style=\"color:#64748b;text-decoration:underline;\">Unsubscribe</a>"
        " &nbsp;|&nbsp; "
        "<a href=\"https://instagram.com\" style=\"color:#64748b;text-decoration:underline;\">Instagram</a>"
        " &nbsp;|&nbsp; "
        "<a href=\"https://x.com\" style=\"color:#64748b;text-decoration:underline;\">X</a>"
        " &nbsp;|&nbsp; "
        "<a href=\"https://tiktok.com\" style=\"color:#64748b;text-decoration:underline;\">TikTok</a>"
        "</p>"
        "</td></tr>"
        "</table></td></tr></table></td></tr></table></body></html>"
    )


def _render_fallback_html(user_name: str, city: str, events: list[dict]) -> str:
    return _render_newsletter_html(
        user_name=user_name,
        city=city,
        intro_line=f"Fresh picks around {city} are in. Here is your clean, quick-hit lineup for the week.",
        events=events,
        generated_at=datetime.now(tz=timezone.utc),
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
    latest_goals = db.scalars(select(UserGoal).where(UserGoal.user_id == user.id).order_by(UserGoal.created_at.desc())).first()
    tags = latest_hobbies.parsed_tags if latest_hobbies else []
    hobby_raw_text = latest_hobbies.raw_text if latest_hobbies else ""
    goals_raw_text = latest_goals.raw_text if latest_goals else ""

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

    subject, intro_line = _generate_newsletter_copy(
        user=user,
        tags=tags,
        hobby_raw_text=hobby_raw_text,
        goals_raw_text=goals_raw_text,
        events=events,
        music_context=music_context,
        busy_windows=busy_windows,
    )

    html = _render_newsletter_html(
        user_name=user.name,
        city=user.city,
        intro_line=intro_line,
        events=events,
        generated_at=datetime.now(tz=timezone.utc),
    )
    if "<html" not in html:
        html = _render_fallback_html(user_name=user.name, city=user.city, events=events)

    newsletter = Newsletter(
        user_id=user.id,
        subject=subject,
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
