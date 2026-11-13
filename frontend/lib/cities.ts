// Mirrors backend/itk/cities.py. Both are tested against shared/city-normalization-cases.json.

const US_STATES: Record<string, string> = {
  al: "alabama", ak: "alaska", az: "arizona", ar: "arkansas", ca: "california",
  co: "colorado", ct: "connecticut", de: "delaware", fl: "florida", ga: "georgia",
  hi: "hawaii", id: "idaho", il: "illinois", in: "indiana", ia: "iowa",
  ks: "kansas", ky: "kentucky", la: "louisiana", me: "maine", md: "maryland",
  ma: "massachusetts", mi: "michigan", mn: "minnesota", ms: "mississippi", mo: "missouri",
  mt: "montana", ne: "nebraska", nv: "nevada", nh: "new hampshire", nj: "new jersey",
  nm: "new mexico", ny: "new york", nc: "north carolina", nd: "north dakota", oh: "ohio",
  ok: "oklahoma", or: "oregon", pa: "pennsylvania", ri: "rhode island", sc: "south carolina",
  sd: "south dakota", tn: "tennessee", tx: "texas", ut: "utah", vt: "vermont",
  va: "virginia", wa: "washington", wv: "west virginia", wi: "wisconsin", wy: "wyoming",
  dc: "district of columbia",
};

const STATE_SUFFIXES = [...new Set([...Object.keys(US_STATES), ...Object.values(US_STATES)])].sort(
  (a, b) => b.length - a.length,
);

export const PILOT_CITIES = ["austin", "san antonio"] as const;
export const PILOT_CITIES_LABEL = "Austin & San Antonio";

// Rough bounding box around the pilot cities, used to bias address autocomplete.
export const PILOT_BOUNDS = { south: 29.02, west: -99.75, north: 30.91, east: -97.02 };

export function normalizeCity(value: string): string {
  let text = value.trim().toLowerCase().replaceAll(".", "").split(/\s+/).filter(Boolean).join(" ");
  text = text.split(",", 1)[0].trim();
  text = text
    .split(" ")
    .filter((token) => token && !/^\d+$/.test(token))
    .join(" ");
  for (const suffix of STATE_SUFFIXES) {
    if (text.endsWith(` ${suffix}`)) {
      text = text.slice(0, -(suffix.length + 1)).trim();
      break;
    }
  }
  return text;
}

export function isPilotCity(value: string): boolean {
  return (PILOT_CITIES as readonly string[]).includes(normalizeCity(value));
}
