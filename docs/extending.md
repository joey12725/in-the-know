# Extending ITK

## Open a new city

1. Add it to `PILOT_CITIES` (backend env) and to `PILOT_CITIES` / `PILOT_CITIES_LABEL` /
   `PILOT_BOUNDS` in `frontend/lib/cities.ts`.
2. Optionally seed a few venues for it in `SEED_VENUES` (`backend/itk/services/venues.py`).
   They are only used when the venue-discovery model call returns nothing.
3. Waitlist entries for that city are already in `waitlist_entries`; email them.

City names are normalized the same way on both sides ("San Antonio, TX 78205" becomes
"san antonio"). If you change the rules, add cases to `shared/city-normalization-cases.json`;
the Python and TypeScript tests both read it.

## Add an OAuth integration

1. Add an `OAuthProvider` to `PROVIDERS` in `backend/itk/services/oauth.py` with its authorize
   and token URLs and scopes.
2. Add `<name>_client_id` / `<name>_client_secret` fields to `Settings` in `itk/config.py`.
3. Write a read-only fetcher in `itk/services/integrations.py` and pass its output into
   `build_copy_prompt` in `itk/services/newsletter.py`, using
   `get_access_token(db, user.id, "<name>")` (it handles refresh).
4. Add a button to `IntegrationsStep` in `frontend/components/onboarding/steps.tsx`.

The connect and callback routes are generic, so no new endpoints are needed.

## Swap models

Each role is its own setting: `OPENROUTER_MODEL` (structured extraction),
`OPENROUTER_SEARCH_MODEL` (web-grounded research) and `OPENROUTER_WRITING_MODEL` (copy). Any
OpenRouter model ID works. Model replies are parsed with `parse_json_array` /
`parse_json_object`, which tolerate code fences and surrounding prose.

## Change the voice

The copywriting constraints live in `VOICE_GUIDE` in `itk/services/newsletter.py`;
`BANNED_PHRASES` and `clean_subject` / `clean_intro` are the guardrails applied to whatever the
model returns. The HTML is in `itk/services/newsletter_template.py`.

## Add a pipeline step

Write a function `(db: Session) -> int` and register it in `run_weekly_pipeline` with
`run.step("name", lambda: your_step(db))`. If it should be callable on its own, add an
endpoint to `itk/routes/pipeline.py`; the router already requires the cron secret.

## Develop offline

```bash
make demo   # SQLite + fabricated subscribers + a full pipeline run; issues land in backend/.outbox/
```

Tests never touch the network: LLM calls are monkeypatched and HTTP is mocked with `respx`.
Set `TEST_DATABASE_URL` to run the suite against Postgres, and `TEST_POSTGRES_URL` to enable
the migration drift check.
