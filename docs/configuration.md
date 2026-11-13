# Configuration and deployment

All settings are environment variables, read from `.env` at the repo root during local
development. `.env.example` lists every one. Nothing is required to run locally.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` enables secure cookies, refuses default secrets and unsigned webhooks, and disables the local email outbox |
| `DATABASE_URL` | `sqlite:///./itk-dev.db` | Postgres (`postgresql://...`) in production. `postgres://` URLs are accepted |
| `DATABASE_URL_UNPOOLED` | | Direct connection used for migrations (e.g. Neon's non-pooler host) |
| `NEXT_PUBLIC_APP_URL` | `http://localhost:3000` | Public site URL, used in emails and OAuth landing redirects |
| `BACKEND_API_URL` | `http://localhost:8000` | Backend origin. OAuth callbacks are registered here; the Next.js proxy forwards to it |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated |
| `PILOT_CITIES` | `austin,san antonio` | Comma-separated cities that can sign up; everyone else joins the waitlist |
| `OPENROUTER_API_KEY` | | Without it, every AI step falls back to heuristics |
| `OPENROUTER_MODEL` / `_SEARCH_MODEL` / `_WRITING_MODEL` | `openai/gpt-5.2` / `perplexity/sonar` / `openai/gpt-5.2` | Model per role |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | | Google Calendar (read-only free/busy) |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | | Spotify (recently played, top items) |
| `NEXT_PUBLIC_GOOGLE_PLACES_API_KEY` | | Browser key for address autocomplete in onboarding |
| `RESEND_API_KEY` | | Without it, email is written to `EMAIL_OUTBOX_DIR` (development only) |
| `RESEND_FROM_EMAIL` | `ITK <onboarding@resend.dev>` | Sender |
| `RESEND_REPLY_TO_EMAIL` | | Reply mailbox on your verified domain; issues are plus-addressed per issue |
| `RESEND_INBOUND_WEBHOOK_SECRET` | | `whsec_...` (Svix signature check) or any shared secret sent as `X-Webhook-Secret` |
| `EMAIL_OUTBOX_DIR` | `.outbox` | Where development email lands |
| `SESSION_SECRET` | dev placeholder | HMAC key for signed tokens (OAuth state, unsubscribe links) |
| `TOKEN_ENCRYPTION_KEY` | falls back to `SESSION_SECRET` | Key material for encrypting OAuth tokens |
| `API_CRON_SECRET` | dev placeholder | Guards `/api/pipeline/*` |
| `RATE_LIMIT_SIGNUP` | `10/minute` | slowapi limit string |

The frontend only needs `BACKEND_API_URL` (server side, for the proxy),
`NEXT_PUBLIC_APP_URL` and optionally `NEXT_PUBLIC_GOOGLE_PLACES_API_KEY`.

## Local Postgres

```bash
docker compose up -d db
# in .env:
DATABASE_URL=postgresql://itk:itk@localhost:5432/itk
make seed      # runs Alembic migrations, then loads demo data
```

## Deploying to Vercel

Use two Vercel projects pointing at the same repository.

**Frontend**: root directory `frontend`, framework Next.js. Set `BACKEND_API_URL` and
`NEXT_PUBLIC_APP_URL` (plus the Places key if you use it).

**Backend**: root directory `backend`. `backend/vercel.json` routes every path to
`api/index.py`, which serves the FastAPI app; dependencies come from `requirements.txt`
(a test keeps it in sync with `pyproject.toml`). Set the database, OAuth, OpenRouter, Resend
and secret variables, plus `ENVIRONMENT=production`. Run migrations from your machine or CI:

```bash
cd backend
DATABASE_URL=... uv run alembic upgrade head
```

### Weekly cron

Set `CRON_SECRET` on the backend project to the same value as `API_CRON_SECRET` (Vercel Cron
sends it as `Authorization: Bearer ...`) and add a schedule to `backend/vercel.json`:

```json
"crons": [{ "path": "/api/pipeline/run-all", "schedule": "0 13 * * 0" }]
```

Run the research steps on their own schedule (or from any long-running host) so each
subscriber's run only has to draft and send:

```bash
curl -X POST -H "X-Cron-Secret: $API_CRON_SECRET" -H 'content-type: application/json' \
  -d '{}' https://<backend>/api/pipeline/search-events
```

## OAuth apps

Register these redirect URIs:

- Google Cloud console (OAuth client, Calendar API enabled, scope `calendar.readonly`):
  `{BACKEND_API_URL}/api/auth/google/callback`
- Spotify developer dashboard: `{BACKEND_API_URL}/api/auth/spotify/callback`

## Inbound replies (Resend)

1. Verify your sending domain in Resend and create an inbound address, e.g. `reply@yourdomain`.
2. Set `RESEND_REPLY_TO_EMAIL` to that address.
3. Add a webhook for received email pointing at `{BACKEND_API_URL}/api/webhooks/email-reply`
   and put its signing secret (`whsec_...`) in `RESEND_INBOUND_WEBHOOK_SECRET`.
