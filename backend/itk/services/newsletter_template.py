"""Email-safe HTML for a weekly issue: table layout, inline styles, mobile breakpoint."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from html import escape

from itk.models import Event

MAX_EVENTS_PER_ISSUE = 8

CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Music", ("music", "concert", "dj", "band", "show", "live", "jazz")),
    ("Food", ("food", "tasting", "brunch", "dinner", "restaurant", "market", "taco")),
    ("Social", ("mixer", "social", "networking", "meetup", "singles")),
    ("Outdoors", ("hike", "run", "trail", "outdoor", "park", "bike")),
    ("Arts", ("gallery", "museum", "art", "film", "photo", "theater", "theatre")),
    ("Fitness", ("fitness", "yoga", "pilates", "workout", "wellness")),
)
CATEGORY_EMOJI = {"music": "🎵", "food": "🍽️", "social": "🤝", "outdoors": "🌿", "arts": "🎨", "fitness": "💪"}


@dataclass(frozen=True)
class EventCard:
    name: str
    date: str
    location: str
    price: str
    summary: str
    url: str
    cta: str


@dataclass(frozen=True)
class IssueLinks:
    app_url: str
    unsubscribe_url: str
    contact_email: str


def truncate(value: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def infer_category(event: Event) -> str:
    raw = str(event.get("category") or "").strip()
    if raw:
        return raw.title()
    haystack = f"{event.get('name', '')} {event.get('description', '')}".lower()
    for category, words in CATEGORY_KEYWORDS:
        if any(word in haystack for word in words):
            return category
    return "Featured"


def price_indicator(raw_price: object) -> str:
    """Map "$25", "Free", "$10-$15" or "$$" to Free / $ / $$ / $$$ / $$$$."""
    raw = str(raw_price or "").strip().lower()
    if raw in {"$", "$$", "$$$", "$$$$"}:
        return raw
    if "free" in raw:
        return "Free"
    number = ""
    for ch in raw:
        if ch.isdigit() or (ch == "." and number):
            number += ch
        elif ch == "," and number:
            continue
        elif number:
            break
    if not number:
        return "$$"
    amount = float(number.rstrip("."))
    if amount == 0:
        return "Free"
    if amount <= 15:
        return "$"
    if amount <= 40:
        return "$$"
    if amount <= 100:
        return "$$$"
    return "$$$$"


def group_events(events: list[Event], city: str, app_url: str) -> dict[str, list[EventCard]]:
    grouped: dict[str, list[EventCard]] = defaultdict(list)
    for event in events[:MAX_EVENTS_PER_ISSUE]:
        grouped[infer_category(event)].append(
            EventCard(
                name=truncate(str(event.get("name") or "Event"), 90),
                date=str(event.get("date") or "Date TBA").strip(),
                location=truncate(str(event.get("location") or city), 80),
                price=price_indicator(event.get("price")),
                summary=truncate(str(event.get("description") or "Worth checking out this week."), 170),
                url=str(event.get("url") or "").strip() or app_url,
                cta=str(event.get("cta") or "").strip() or "Check it out",
            )
        )
    return dict(grouped)


def _card_html(card: EventCard) -> str:
    return (
        '<tr><td style="padding:0 0 16px 0;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border:1px solid #dbe5ff;border-radius:14px;background:#f8faff;">'
        '<tr><td style="padding:16px 16px 10px 16px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="font-size:20px;line-height:1.2;font-weight:700;color:#111827;">{escape(card.name)}</td>'
        '<td align="right" style="font-size:13px;font-weight:700;color:#1d4ed8;white-space:nowrap;">'
        f"{escape(card.price)}</td>"
        "</tr></table>"
        f'<p style="margin:10px 0 0 0;font-size:14px;line-height:1.5;color:#334155;">🗓️ {escape(card.date)}</p>'
        f'<p style="margin:4px 0 0 0;font-size:14px;line-height:1.5;color:#334155;">📍 {escape(card.location)}</p>'
        f'<p style="margin:10px 0 0 0;font-size:15px;line-height:1.55;color:#111827;">{escape(card.summary)}</p>'
        '<p style="margin:14px 0 0 0;">'
        f'<a href="{escape(card.url)}" style="display:inline-block;background:#1d4ed8;color:#ffffff;'
        'text-decoration:none;font-size:14px;font-weight:700;padding:10px 14px;border-radius:10px;">'
        f"{escape(card.cta)}</a></p>"
        "</td></tr></table></td></tr>"
    )


def _section_html(category: str, cards: list[EventCard]) -> str:
    emoji = CATEGORY_EMOJI.get(category.lower(), "✨")
    return (
        '<tr><td style="padding:2px 0 12px 0;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        '<td style="font-size:13px;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;color:#1d4ed8;'
        f'white-space:nowrap;padding-right:12px;">{emoji} {escape(category)}</td>'
        '<td width="100%" style="border-bottom:1px solid #dbe5ff;font-size:0;line-height:0;">&nbsp;</td>'
        "</tr></table></td></tr>" + "".join(_card_html(card) for card in cards)
    )


def render_newsletter_html(
    *,
    user_name: str,
    city: str,
    intro_line: str,
    events: list[Event],
    generated_at: datetime,
    links: IssueLinks,
    footer_note: str,
) -> str:
    sections = "".join(
        _section_html(category, cards) for category, cards in group_events(events, city, links.app_url).items()
    )
    city_display = escape(city)
    contact = escape(links.contact_email)
    issue_date = f"{generated_at:%b} {generated_at.day}, {generated_at:%Y}"
    return (
        "<!doctype html>"
        '<html><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />'
        "<style>"
        "@media only screen and (max-width: 640px) {"
        " .wrapper {width:100% !important;}"
        " .shell {padding:14px !important;}"
        " .card {padding:18px !important;}"
        " .title {font-size:26px !important; line-height:1.2 !important;}"
        "}"
        "</style></head>"
        "<body style=\"margin:0;padding:0;background:#eef2ff;font-family:'Inter','Avenir Next','Segoe UI',Arial,"
        'sans-serif;color:#111827;">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(truncate(intro_line, 90))}</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2ff;">'
        '<tr><td class="shell" style="padding:22px 12px;">'
        '<table class="wrapper" role="presentation" width="620" align="center" cellpadding="0" cellspacing="0" '
        'style="width:620px;max-width:620px;">'
        '<tr><td class="card" style="background:#ffffff;border-radius:18px;padding:26px 22px;'
        'border:1px solid #dbe5ff;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td style="padding-bottom:18px;border-bottom:1px solid #e5e7eb;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td>'
        '<p style="margin:0;font-size:12px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;'
        'color:#1d4ed8;">ITK Weekly</p>'
        f'<p style="margin:8px 0 0 0;font-size:13px;color:#475569;">{city_display} local briefing</p>'
        f'</td><td align="right" style="font-size:13px;color:#64748b;">{escape(issue_date)}</td>'
        "</tr></table></td></tr>"
        '<tr><td style="padding-top:18px;">'
        f'<h1 class="title" style="margin:0;font-size:31px;line-height:1.15;color:#0f172a;">{escape(user_name)}, '
        f"your week in {city_display}</h1>"
        f'<p style="margin:12px 0 18px 0;font-size:16px;line-height:1.5;color:#1f2937;">{escape(intro_line)}</p>'
        "</td></tr>" + sections + '<tr><td style="padding-top:10px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f8fafc;border-radius:14px;border:1px solid #e2e8f0;">'
        '<tr><td style="padding:14px;">'
        '<p style="margin:0;font-size:14px;line-height:1.5;color:#0f172a;">Want this to get sharper next week? '
        "Reply to this email and tell us what to include less or more of.</p>"
        '<p style="margin:10px 0 0 0;font-size:13px;line-height:1.5;color:#334155;">Or message us directly at '
        f'<a href="mailto:{contact}" style="color:#1d4ed8;text-decoration:none;">{contact}</a>.</p>'
        "</td></tr></table></td></tr>"
        '<tr><td style="padding-top:22px;border-top:1px solid #e5e7eb;">'
        f'<p style="margin:0;font-size:12px;line-height:1.6;color:#64748b;">{escape(footer_note)}</p>'
        '<p style="margin:8px 0 0 0;font-size:12px;line-height:1.6;color:#64748b;">'
        f'<a href="{escape(links.unsubscribe_url)}" style="color:#64748b;text-decoration:underline;">Unsubscribe</a>'
        "</p></td></tr>"
        "</table></td></tr></table></td></tr></table></body></html>"
    )
