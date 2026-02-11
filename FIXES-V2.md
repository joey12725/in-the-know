# ITK Fixes V2 - Newsletter & Feature Improvements

## 1. Newsletter Tone & Copy Overhaul

### Problem
- Subject line "What's Actually Worth Leaving The House For" is bad
- Intro copy ("Yo Joey — here's what's happening in SA that fits your vibe. Some of this is solid, some of it's weird, all of it beats doom-scrolling.") is extremely cringe
- Reads like a dad trying to be cool, not someone actually in the know

### Fix
Update the newsletter drafting prompt/template in `backend/services/email.py` and any related pipeline code:

- Work in gen z slang naturally - sharp, clever, from someone who actually talks like this. NOT forced. Reference: https://gabb.com/blog/teen-slang/ for vocabulary but the key is using it like someone who grew up with it, not someone who googled it
- Subject lines should be short, specific, intriguing. Think tweet energy not blog title energy
- Intro should be 1 sentence max. No "yo". No "vibe". No "doom-scrolling". Those are dead internet words
- The newsletter voice should sound like a friend in a group chat dropping links, not a marketing email trying to sound casual
- Examples of good energy: "this week's actually not mid", "the lineup at [venue] goes stupid hard", "lowkey the best thing happening this weekend"
- Examples of BAD energy: "fits your vibe", "beats doom-scrolling", "what's worth leaving the house for"

### Technical
- Update the system prompt used when drafting newsletters (likely in `backend/services/email.py` or `backend/pipeline/runner.py`)
- Make sure the FULL user hobbies raw text (the word vomit) AND goals_raw_text are passed to the newsletter drafting agent, not just the 12 parsed tags. The word vomit has context and specificity the tags lose
- The parsed tags are for EVENT SEARCH. The raw text is for PERSONALIZATION/TONE

## 2. Email Reply Agent (New Feature)

### Problem
Users can't interact with the newsletter. Need a reply-to flow.

### Feature Spec
Create an inbound email handler that processes replies to ITK newsletters. When a user replies to their newsletter email:

a) An OpenRouter-powered agent reads their reply and classifies the intent:
   - **Add interests** - user wants to add new hobbies/interests
   - **Remove interests** - user wants to remove hobbies/interests  
   - **Unsubscribe** - user wants to stop receiving emails
   - **Feedback** - user liked/didn't like something, wants more/less of something

b) For feedback: create a new `newsletter_feedback` table:
```sql
CREATE TABLE newsletter_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    newsletter_id UUID REFERENCES newsletters(id),
    raw_reply TEXT NOT NULL,
    rewritten_feedback TEXT NOT NULL,  -- AI-rewritten with full context
    feedback_type TEXT NOT NULL,  -- 'positive', 'negative', 'preference', 'suggestion'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

c) The agent should REWRITE the user's feedback to include all needed context. Example:
   - User writes: "less rodeo stuff please"
   - Agent rewrites: "User does not want livestock/rodeo events included in their San Antonio newsletter. They were shown SA Stock Show & Rodeo in the Feb 12-25 edition and found it irrelevant to their interests."

d) When drafting newsletters, query this feedback table and include recent feedback entries in the drafting prompt so the AI can course-correct

### Technical
- Set up a Resend inbound webhook endpoint: `POST /api/webhooks/email-reply`
- Use Resend's inbound email feature (or if not available with onboarding@resend.dev, document what's needed when they get their own domain)
- New route in `backend/routes/` for the webhook
- New service in `backend/services/reply_agent.py` for the OpenRouter classification/rewriting
- New alembic migration for `newsletter_feedback` table
- Update newsletter drafting to query and include feedback

## 3. Dating Distinction in Onboarding

### Problem
"Dating" is listed as an interest but there's a huge difference between:
- "I want cool date spots to take my partner to" (date night ideas)
- "I want to find places/events where I can meet people to date" (singles events, social mixers)

### Fix
- In the onboarding flow, if user selects dating-related interests, present a follow-up:
  - "Date night spots" (restaurants, activities, experiences for couples)
  - "Meeting people" (singles events, social mixers, speed dating, community events)
  - Both
- Store this as a field on the user or as a goal type
- Update `backend/schemas/public.py` SignupRequest if needed
- Update frontend onboarding wizard to include this distinction
- Pass this context to the newsletter agent so it can tailor dating recommendations

## 4. Music Venue Enrollment Search

### Problem
For pilot cities (Austin, San Antonio), we should know the major music venues and actively search their upcoming events rather than relying on generic event searches.

### Feature Spec
Create a venue discovery and event search pipeline:

1. **Venue Discovery** (run once per city on enrollment, refreshed monthly):
   - Search "what are the major music venues in [city name]" via Perplexity/web search
   - Extract venue names and store in a new `city_venues` table:
   ```sql
   CREATE TABLE city_venues (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       city TEXT NOT NULL,
       venue_name TEXT NOT NULL,
       venue_type TEXT DEFAULT 'music',  -- expandable later
       address TEXT,
       website TEXT,
       last_searched TIMESTAMPTZ,
       created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       UNIQUE(city, venue_name)
   );
   ```

2. **Venue Event Search** (run as part of weekly pipeline):
   - For each venue in the user's city, search "[venue name] upcoming events [date range]"
   - Store/cache results in the venue record or a separate events cache
   - Feed these into the newsletter drafting alongside the hobby-based event search results

3. **Pilot cities to pre-populate:**
   - San Antonio: search and store major venues
   - Austin: search and store major venues

### Technical
- New alembic migration for `city_venues` table
- New service `backend/services/venues.py` for venue discovery and event search
- Add venue search step to `backend/pipeline/runner.py`
- New pipeline endpoint `POST /api/pipeline/discover-venues` (cron-secret protected)
- New pipeline endpoint `POST /api/pipeline/search-venue-events` (cron-secret protected)

## 5. Email Design/Formatting

### Problem
The email looks sad. Basic HTML with no visual appeal.

### Fix
Redesign the newsletter HTML template:
- Modern, clean email design (think Morning Brew, The Hustle, TLDR newsletter aesthetic)
- Proper email-safe CSS (inline styles, table-based layout for compatibility)
- Brand colors and ITK logo/header
- Card-based event layout with clear visual hierarchy
- Mobile-responsive (most people read email on phone)
- Clear category separators with icons/emoji
- Each event card should have: name, date, location, price indicator, one-liner, link button
- Footer with unsubscribe link, reply-to-give-feedback CTA, social links placeholder
- Use a clean sans-serif font stack

## 6. Pass Full Context to Newsletter Agent

### Problem
Currently only parsed tags (12 max) are used for newsletter personalization. The full hobby word vomit and goals have rich context that gets lost.

### Fix
- In the newsletter drafting step (`backend/services/email.py` or wherever the AI prompt is built):
  - Include `user_hobbies.raw_text` (the full word vomit)
  - Include `user_goals.raw_text` (goals if present)
  - Include recent `newsletter_feedback` entries
  - Include the user's dating preference (from fix #3)
- The parsed tags drive EVENT SEARCH (what to look for)
- The raw text drives PERSONALIZATION (how to write about it, what angle to take)

## Priority Order
1. Email design (#5) - visual first impression
2. Newsletter tone (#1) - copy quality
3. Full context to agent (#6) - personalization quality  
4. Music venue search (#4) - content quality
5. Dating distinction (#3) - onboarding improvement
6. Email reply agent (#2) - engagement feature
