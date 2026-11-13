"""City normalization shared by signup gating, event caching and venue discovery.

The frontend mirrors this logic in `frontend/lib/cities.ts`; both are tested against
`shared/city-normalization-cases.json` so they cannot drift apart.
"""

from itk.config import get_settings

US_STATES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california",
    "co": "colorado", "ct": "connecticut", "de": "delaware", "fl": "florida", "ga": "georgia",
    "hi": "hawaii", "id": "idaho", "il": "illinois", "in": "indiana", "ia": "iowa",
    "ks": "kansas", "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi", "mo": "missouri",
    "mt": "montana", "ne": "nebraska", "nv": "nevada", "nh": "new hampshire", "nj": "new jersey",
    "nm": "new mexico", "ny": "new york", "nc": "north carolina", "nd": "north dakota", "oh": "ohio",
    "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina",
    "sd": "south dakota", "tn": "tennessee", "tx": "texas", "ut": "utah", "vt": "vermont",
    "va": "virginia", "wa": "washington", "wv": "west virginia", "wi": "wisconsin", "wy": "wyoming",
    "dc": "district of columbia",
}  # fmt: skip
_STATE_SUFFIXES = sorted({*US_STATES, *US_STATES.values()}, key=len, reverse=True)


def normalize_city(value: str) -> str:
    """Reduce free-form input like "San Antonio, TX 78205" to a lookup key ("san antonio")."""
    text = " ".join(value.strip().lower().replace(".", "").split())
    text = text.split(",", 1)[0].strip()
    tokens = [token for token in text.split() if not token.isdigit()]
    text = " ".join(tokens)
    for suffix in _STATE_SUFFIXES:
        if text.endswith(f" {suffix}"):
            text = text[: -len(suffix) - 1].strip()
            break
    return text


def is_pilot_city(value: str) -> bool:
    return normalize_city(value) in get_settings().pilot_cities


def pilot_cities() -> list[str]:
    return list(get_settings().pilot_cities)


def pilot_cities_label() -> str:
    """Human-readable list, e.g. "Austin & San Antonio"."""
    names = [city.title() for city in pilot_cities()]
    if len(names) <= 2:
        return " & ".join(names)
    return f"{', '.join(names[:-1])} & {names[-1]}"
