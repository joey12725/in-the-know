# ITK Fixes - Round 1

Apply all of these changes. Commit after each major fix group.

## Frontend Fixes

### 1. Landing Page Hero - Right Side
The right side sample newsletter card looks sparse and weird. Make it much better:
- Change "Alex" to "John" throughout
- Make the sample newsletter WAY more compelling and realistic. It should look like an actual beautiful mini-newsletter preview, not a plain card with bullet points
- Include more variety: a concert, a food festival, a meetup, a workshop - things that feel real for Austin/San Antonio
- Add visual flair - maybe colored category tags, small emoji icons next to events, better typography hierarchy
- The card should feel like a sneak peek that makes you WANT to sign up
- Pilot cities are **Austin and San Antonio only** - reflect this

### 2. Landing Page - "See a sample" Section
The sample newsletter further down the page is abysmal. Redesign it completely:
- Should look like an actual email preview with proper formatting
- Include 5-6 events across different categories (music, food, outdoor, social, creative)
- Each event should have: day, time, venue name, short compelling description, category tag
- Make it look like something from a premium newsletter (think Morning Brew or The Hustle aesthetic)
- Use Austin/San Antonio venues and events that feel real

### 3. Landing Page - "Choose better" Signal
The section about choosing better is weak. Make the value proposition punchier:
- Stronger copy that emphasizes what you're MISSING without ITK
- More specific benefits (not generic)
- Consider social proof elements or stats (even placeholder ones like "Join 2,000+ locals")

### 4. Address Input - Autofill
Add Google Places autocomplete to the address field in the onboarding form:
- Use the Google Places API for address suggestions as user types
- The Google Places API key is available as env var GOOGLE_PLACES_API_KEY
- Add it to the frontend env on Vercel too
- For the pilot, bias results toward Austin and San Antonio, TX
- After selection, auto-populate city field

### 5. Onboarding - Loading Animation
The "make ITK smarter" optional step hangs with no feedback. Add:
- A nice loading/processing animation when this step is running
- Animated text like "Analyzing your interests..." → "Finding events near you..." → "Personalizing your experience..."
- Should feel like AI is working, not like the page is broken

### 6. Onboarding - Finish Button
The finish button seems to do nothing. Fix it:
- Should show a success/welcome screen or redirect to a "You're all set!" page
- If it's already supposed to do something, debug why it's not working
- Add a confirmation state with confetti or celebration animation

### 7. Pilot City Restriction
- Limit the service to Austin and San Antonio for the pilot
- Add messaging on the landing page like "Currently available in Austin & San Antonio" 
- In the onboarding, if someone enters an address outside these areas, show a "Join the waitlist" flow instead
- Add a waitlist table to the database if it doesn't exist

### 8. Update app_url references
- The frontend is now at https://itk-so.vercel.app (not itk.so yet)
- Update CORS_ORIGINS on backend to include this URL
- The NEXT_PUBLIC_APP_URL should be https://itk-so.vercel.app for now

## Backend Fixes

### 9. OAuth Redirect URIs
- The backend_api_url env var is now set to https://your-backend.vercel.app
- Make sure the config reads BACKEND_API_URL from env (it currently defaults to localhost:8000)
- OAuth callbacks: /api/auth/google/callback and /api/auth/spotify/callback

## After all fixes
- Run `npm run build` in frontend/ to verify no build errors
- Commit all changes with descriptive messages
- Do NOT commit .env files
