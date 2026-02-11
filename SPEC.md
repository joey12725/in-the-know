# In The Know (ITK) — itk.so

AI-powered hyper-personalized weekly newsletter for local events.

## Overview

ITK learns what users care about (hobbies, goals, music taste, calendar availability) and sends them a beautifully formatted weekly email with curated local events. Every email is unique to the user.

## Tech Stack

- **Frontend:** Next.js (App Router), deployed on Vercel
- **Backend:** Python (FastAPI), deployed on Vercel as serverless functions or separate service
- **Database:** Neon PostgreSQL (connection strings in .env)
- **AI:** OpenRouter API (key in env as OPENROUTER_API_KEY)
- **Integrations:** Google Calendar API, Spotify API
- **Domain:** itk.so

## Architecture (from diagram)

### Entry Points
1. **Web-based onboarding** (landing page form)
2. **Meta IF** (Instagram/Facebook — future, just stub the webhook)

### Onboarding Flow

**Web form collects:**
- Name
- Address (for location/city)
- Email
- Concision preference (brief vs detailed newsletters) — NOT on Meta IF
- Event radius (how far they'll travel, approximate miles) — NOT on Meta IF
- Hobbies (free-text "word vomit" — user describes interests naturally)
- Goals (free-text: dating, friends, charity, community, connection to hobbies)

**After signup, onboarding email (all optional steps):**
- Connect Google Calendar (OAuth)
- Connect Spotify (OAuth)
- If coming from Meta IF: set concision and radius preferences
- Personality quiz (Myers-Briggs style or similar — short, fun)

### Processing Pipeline (Weekly)

1. **Parse hobbies** — AI extracts structured hobby tags from free-text, groups similar hobbies across users
2. **If new hobbies exist** — a search prompt is generated for event discovery
3. **Store in database** — user profiles, hobbies, hobby-city pairings with frequency counts
4. **Weekly timer triggers pipeline:**
   a. Extract all hobby/city pairs (frequency of occurrence tracked so common pairings can use more expensive/better models)
   b. **Search for events** — use web search (OpenRouter + web search capable model, or Brave search API) for each hobby/city pairing
   c. **Pull Spotify data** — user's recent listening for music event matching
   d. **Pull Google Calendar** — user's availability to avoid conflicts
   e. **Draft personalized email** — AI writes each user's newsletter based on their profile, hobbies, location, calendar, music taste, concision preference, personality
   f. **Send emails** — beautifully formatted HTML emails

### Key Design Decisions
- **Frequency-based model routing:** Common hobby/city pairs (e.g., "hiking/Austin") use cached results or cheaper models. Rare pairs get fresh expensive searches
- **Emails must be beautifully formatted** — modern HTML email design, not plain text
- **Everything personalized** — no two users get the same email

## Landing Page — SB7 Framework (StoryBrand)

The landing page must be high-converting using Donald Miller's StoryBrand SB7 framework:

1. **Character** — The user (busy person who wants to do cool stuff in their city)
2. **Problem** — External: Too many events, no time to research. Internal: FOMO, feeling disconnected. Philosophical: People deserve to know what's happening in their own city
3. **Guide** — ITK (with empathy + authority)
4. **Plan** — 3 steps: Sign up → Tell us what you're into → Get your weekly personalized guide
5. **Call to Action** — Direct: "Get My First Newsletter" / Transitional: "See a sample"
6. **Failure** — Missing out on amazing events, staying home when there's something perfect happening
7. **Success** — Never miss an event you'd love. Feel connected to your city. Actually do the things you keep saying you want to do

Design should be modern, clean, bold. Think Linear/Vercel aesthetic. Mobile-first.

### Landing Page Sections
- Hero with headline + CTA + email capture
- Social proof / stats (even if placeholder)
- How it works (3 steps)
- Sample newsletter preview
- Feature highlights
- Final CTA
- Footer

### Onboarding Form
After email capture, multi-step form:
1. Name + Location (address or zip)
2. Hobbies (big text area, encourage word vomit)
3. Goals (what are you looking for? checkboxes + free text)
4. Preferences (concision slider, radius slider)
5. Optional: Connect Spotify, Connect Calendar
6. Confirmation / welcome

## Database Schema (Neon PostgreSQL)

Tables needed:
- `users` — id, name, email, address, city, lat, lng, concision_pref, event_radius_miles, personality_type, created_at, updated_at
- `user_hobbies` — id, user_id, raw_text, parsed_tags (jsonb), created_at
- `user_goals` — id, user_id, raw_text, goal_types (jsonb), created_at
- `hobby_tags` — id, tag_name, search_prompt, created_at
- `hobby_city_pairs` — id, hobby_tag_id, city, frequency, last_searched, cached_results (jsonb)
- `oauth_tokens` — id, user_id, provider (google/spotify), access_token, refresh_token, expires_at
- `newsletters` — id, user_id, sent_at, subject, html_content, events_included (jsonb)
- `onboarding_steps` — id, user_id, step_name, completed_at

## API Endpoints (Python/FastAPI)

### Public
- `POST /api/signup` — create user from onboarding form
- `GET /api/onboarding/{token}` — get onboarding status
- `POST /api/onboarding/{token}/step` — complete onboarding step

### OAuth
- `GET /api/auth/google` — initiate Google Calendar OAuth
- `GET /api/auth/google/callback` — handle callback
- `GET /api/auth/spotify` — initiate Spotify OAuth
- `GET /api/auth/spotify/callback` — handle callback

### Internal/Cron
- `POST /api/pipeline/run` — trigger weekly pipeline
- `POST /api/pipeline/parse-hobbies` — parse hobbies for a user
- `POST /api/pipeline/search-events` — search events for hobby/city pairs
- `POST /api/pipeline/draft-emails` — draft newsletters
- `POST /api/pipeline/send-emails` — send newsletters

## Environment Variables

```
# Database
DATABASE_URL=postgresql://<user>:<password>@<neon-host>/neondb?sslmode=require
DATABASE_URL_UNPOOLED=postgresql://<user>:<password>@<neon-host>/neondb?sslmode=require

# AI
OPENROUTER_API_KEY=<from environment>

# Google OAuth (Calendar)
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=REDACTED_GOOGLE_CLIENT_SECRET

# Spotify OAuth
SPOTIFY_CLIENT_ID=your-spotify-client-id
SPOTIFY_CLIENT_SECRET=REDACTED_SPOTIFY_CLIENT_SECRET

# Email (use Resend or similar — set up during build)
RESEND_API_KEY=<to be configured>

# App
NEXT_PUBLIC_APP_URL=https://itk.so
```

## Security Requirements
- Store OAuth tokens encrypted at rest
- Use httpOnly cookies for sessions
- CSRF protection on forms
- Rate limit signup endpoint
- Validate and sanitize all user input
- Don't expose API keys to frontend
- Use parameterized queries (SQLAlchemy or similar)

## File Structure

```
itk/
├── frontend/          # Next.js app
│   ├── app/
│   │   ├── page.tsx          # Landing page
│   │   ├── onboarding/       # Multi-step form
│   │   ├── auth/             # OAuth callback pages
│   │   └── api/              # Next.js API routes (proxy to Python)
│   ├── components/
│   └── public/
├── backend/           # Python FastAPI
│   ├── main.py
│   ├── models/
│   ├── routes/
│   ├── services/
│   │   ├── ai.py             # OpenRouter integration
│   │   ├── events.py         # Event search
│   │   ├── email.py          # Email drafting + sending
│   │   ├── google_cal.py     # Google Calendar
│   │   ├── spotify.py        # Spotify
│   │   └── hobbies.py        # Hobby parsing + matching
│   ├── pipeline/             # Weekly pipeline logic
│   └── requirements.txt
├── google_credentials.json   # DO NOT commit — add to .gitignore
├── .env                      # DO NOT commit
├── .gitignore
├── vercel.json
└── README.md
```

## Priority Order
1. Landing page (hero + CTA + email capture working)
2. Onboarding form (multi-step, data saves to Neon)
3. Database schema + migrations
4. OAuth flows (Google Calendar + Spotify)
5. Hobby parsing pipeline
6. Event search pipeline
7. Email drafting + sending
8. Weekly cron trigger

Build it incrementally. Get the landing page and onboarding working first, then layer in the pipeline.
