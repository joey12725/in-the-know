# ITK (In The Know)

AI-powered hyper-personalized local events newsletter.

## What is implemented

- Next.js frontend (`frontend/`)
  - SB7 landing page with high-conversion structure
  - Multi-step onboarding form (name/location, hobbies, goals, preferences, integrations, confirmation)
  - API proxy routes under `frontend/app/api/[...path]/route.ts` forwarding to FastAPI backend
- FastAPI backend (`backend/`)
  - Public endpoints: signup, onboarding status, onboarding step completion
  - OAuth endpoints: Google Calendar + Spotify initiation/callback
  - Pipeline endpoints: run, parse hobbies, search events, discover venues, search venue events, draft emails, send emails
  - Webhook endpoint: `POST /api/webhooks/email-reply` for inbound Resend replies
  - Meta webhook stub
- Neon/Postgres schema + Alembic migration
  - All required tables from spec
- Security baseline
  - Encrypted OAuth token storage at rest
  - CSRF token issuance + validation for state-changing public endpoints
  - httpOnly signed session cookie on signup
  - Signup rate limiting
  - Input validation + sanitization
  - Parameterized DB access via SQLAlchemy ORM

## Repository layout

- `frontend/`: Next.js app (Vercel frontend project)
- `backend/`: FastAPI app (Vercel backend project)
- `vercel.json`: root-level platform headers (frontend project can still use root config)

## Local development

1. Copy and fill environment values:

```bash
cp .env.example .env
```

2. Backend setup:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000
```

3. Frontend setup (new terminal):

```bash
cd frontend
npm install
npm run dev
```

4. Open `http://localhost:3000`

## Deploy to Vercel

Use two Vercel projects for clean production separation:

1. Frontend project:
- Root directory: `frontend`
- Framework preset: Next.js
- Required env vars: `BACKEND_API_URL`, `NEXT_PUBLIC_APP_URL`

2. Backend project:
- Root directory: `backend`
- `backend/vercel.json` routes everything to `api/index.py`
- Required env vars: DB, OAuth, OpenRouter, email, secrets

## Weekly cron trigger

Configure a Vercel Cron on either project to call:

```text
POST /api/pipeline/run?secret=<API_CRON_SECRET>
```

If scheduled on frontend, it will proxy to backend through `BACKEND_API_URL`.

## Resend inbound replies

- Configure `RESEND_REPLY_TO_EMAIL` to a mailbox on your verified domain, for example `reply@itk.so`.
- Configure `RESEND_INBOUND_WEBHOOK_SECRET` and pass that same value in webhook headers.
- `onboarding@resend.dev` is fine for outbound testing, but inbound reply routing requires a verified custom domain.

## Notes

- `.env` and `google_credentials.json` are git-ignored and not committed.
- OAuth tokens are encrypted in the database.
