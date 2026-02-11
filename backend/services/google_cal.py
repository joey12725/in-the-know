from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx


def get_calendar_availability(access_token: str) -> list[dict]:
    now = datetime.now(tz=timezone.utc)
    end = now + timedelta(days=7)
    payload = {
        "timeMin": now.isoformat(),
        "timeMax": end.isoformat(),
        "items": [{"id": "primary"}],
    }

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=15) as client:
        response = client.post("https://www.googleapis.com/calendar/v3/freeBusy", headers=headers, json=payload)
        if response.status_code >= 400:
            return []
        data = response.json()
        return data.get("calendars", {}).get("primary", {}).get("busy", [])
