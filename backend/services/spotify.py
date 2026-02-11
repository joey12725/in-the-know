from __future__ import annotations

import httpx


def get_recent_tracks(access_token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": 10}
    with httpx.Client(timeout=15) as client:
        response = client.get("https://api.spotify.com/v1/me/player/recently-played", headers=headers, params=params)
        if response.status_code >= 400:
            return []
        items = response.json().get("items", [])

    tracks: list[dict] = []
    for item in items:
        track = item.get("track", {})
        tracks.append(
            {
                "name": track.get("name"),
                "artists": [artist.get("name") for artist in track.get("artists", [])],
            }
        )
    return tracks
