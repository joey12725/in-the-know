"""Read-only context pulled from connected accounts to personalize each issue."""

from datetime import timedelta
from typing import Any

import httpx

from itk.db import utcnow


def get_calendar_busy_windows(access_token: str, days: int = 7) -> list[dict[str, Any]]:
    """Busy blocks on the user's primary Google Calendar for the coming week."""
    now = utcnow()
    try:
        response = httpx.post(
            "https://www.googleapis.com/calendar/v3/freeBusy",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "timeMin": now.isoformat(),
                "timeMax": (now + timedelta(days=days)).isoformat(),
                "items": [{"id": "primary"}],
            },
            timeout=15,
        )
    except httpx.HTTPError:
        return []
    if response.status_code >= 400:
        return []
    busy: list[dict[str, Any]] = response.json().get("calendars", {}).get("primary", {}).get("busy", [])
    return busy


def get_recent_tracks(access_token: str, limit: int = 10) -> list[dict[str, Any]]:
    """The user's recently played Spotify tracks, reduced to track and artist names."""
    try:
        response = httpx.get(
            "https://api.spotify.com/v1/me/player/recently-played",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"limit": limit},
            timeout=15,
        )
    except httpx.HTTPError:
        return []
    if response.status_code >= 400:
        return []
    tracks = []
    for item in response.json().get("items", []):
        track = item.get("track") or {}
        tracks.append(
            {"name": track.get("name"), "artists": [artist.get("name") for artist in track.get("artists", [])]}
        )
    return tracks
