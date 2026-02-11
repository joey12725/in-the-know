import Link from "next/link";

import EmailCaptureForm from "@/components/email-capture-form";

const stats = [
  { value: "2,000+", label: "locals already using ITK + waitlist members" },
  { value: "91%", label: "say they discovered events they would have missed" },
  { value: "2", label: "pilot cities right now: Austin and San Antonio" },
];

const heroPreviewEvents = [
  {
    emoji: "🎷",
    tag: "Music",
    city: "Austin",
    title: "Blue Note Rooftop Sessions",
    details: "Thursday, 7:30 PM · Azul Rooftop",
    note: "A sunset jazz set with reserved lounge seating and skyline views.",
  },
  {
    emoji: "🌮",
    tag: "Food",
    city: "San Antonio",
    title: "Pearl Night Market + Taco Walk",
    details: "Friday, 6:00 PM · The Pearl District",
    note: "Chef pop-ups, live cumbia, and a guided tasting route.",
  },
  {
    emoji: "🤝",
    tag: "Meetup",
    city: "Austin",
    title: "Founders & Creators Mixer",
    details: "Saturday, 11:00 AM · Cosmic Coffee",
    note: "Curated networking circles for operators, builders, and creatives.",
  },
  {
    emoji: "🛠️",
    tag: "Workshop",
    city: "San Antonio",
    title: "Ceramics Crash Course",
    details: "Sunday, 2:00 PM · Plaza Clay Studio",
    note: "Hands-on wheel class built for beginners and date nights.",
  },
];

const sampleEvents = [
  {
    category: "Music",
    day: "Thu",
    time: "7:30 PM",
    venue: "Mohawk Austin",
    name: "Indie Passport Night",
    description: "Three emerging Texas acts, short sets, rooftop lounge open all night.",
  },
  {
    category: "Food",
    day: "Fri",
    time: "6:00 PM",
    venue: "The Pearl, San Antonio",
    name: "Twilight Street Food Festival",
    description: "Chef stalls, live DJs, and late-night dessert carts across the courtyard.",
  },
  {
    category: "Outdoor",
    day: "Sat",
    time: "8:00 AM",
    venue: "Barton Creek Greenbelt",
    name: "Sunrise Trail Social",
    description: "Beginner-friendly hike with a post-walk coffee meetup nearby.",
  },
  {
    category: "Social",
    day: "Sat",
    time: "11:30 AM",
    venue: "Common Desk, Austin",
    name: "New-in-City Brunch Club",
    description: "Hosted table format so everyone meets at least five new people.",
  },
  {
    category: "Creative",
    day: "Sun",
    time: "1:00 PM",
    venue: "Blue Star Arts Complex",
    name: "Analog Photo Walk",
    description: "Guided urban shooting session plus live critique from local photographers.",
  },
  {
    category: "Workshop",
    day: "Sun",
    time: "4:00 PM",
    venue: "MakeATX Lab",
    name: "Intro to Screenprinting",
    description: "Design and print your own tote with all materials included.",
  },
];

const features = [
  {
    title: "No more default weekends",
    body: "ITK cuts through 200+ listings and surfaces only events that actually fit your interests and schedule.",
  },
  {
    title: "Built around your real life",
    body: "Distance, timing windows, and vibe preferences are baked into every recommendation automatically.",
  },
  {
    title: "Momentum you can feel",
    body: "Most members save 2+ hours weekly and finally follow through on the plans they keep talking about.",
  },
];

export default function Home() {
  return (
    <main>
      <section className="hero section">
        <div className="hero-grid">
          <div>
            <p className="eyebrow">In The Know for your city</p>
            <p className="pilot-pill">Currently available in Austin &amp; San Antonio</p>
            <h1>
              Stop missing the best events. <span>Start living like a local insider.</span>
            </h1>
            <p className="lead">
              You are busy. We research your city, filter noise, and send a weekly events guide tuned to your tastes,
              schedule, and goals.
            </p>
            <EmailCaptureForm />
            <div className="hero-links">
              <Link href="#sample">See a sample</Link>
              <Link href="/onboarding">Skip to onboarding</Link>
            </div>
          </div>
          <div className="hero-card">
            <header>
              <p className="card-kicker">ITK Weekend Preview</p>
              <h3>For John: your Austin + San Antonio insider lineup</h3>
            </header>
            <div className="hero-event-list">
              {heroPreviewEvents.map((event) => (
                <article key={event.title} className="hero-event">
                  <div>
                    <p className="hero-event-tag">{event.emoji} {event.tag}</p>
                    <h4>{event.title}</h4>
                    <p className="hero-event-meta">
                      {event.city} · {event.details}
                    </p>
                  </div>
                  <p className="hero-event-note">{event.note}</p>
                </article>
              ))}
            </div>
            <p className="hero-card-footnote">Generated from your hobbies, goals, radius, Spotify taste, and calendar availability.</p>
          </div>
        </div>
      </section>

      <section className="section panel">
        <h2>People deserve to know what is happening in their own city</h2>
        <div className="stats-grid">
          {stats.map((stat) => (
            <article key={stat.label}>
              <h3>{stat.value}</h3>
              <p>{stat.label}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <h2>How ITK works</h2>
        <div className="steps-grid">
          <article>
            <p>Step 1</p>
            <h3>Sign up in under 2 minutes</h3>
            <p>Tell us where you live and drop a raw brain-dump of what you are into.</p>
          </article>
          <article>
            <p>Step 2</p>
            <h3>Share taste + intent</h3>
            <p>Add hobbies, goals, radius, and optional Spotify/Google Calendar for smarter matching.</p>
          </article>
          <article>
            <p>Step 3</p>
            <h3>Receive your weekly local plan</h3>
            <p>Get a beautiful personalized email with events that fit your real life.</p>
          </article>
        </div>
      </section>

      <section id="sample" className="section panel sample">
        <div>
          <p className="eyebrow">Sample newsletter</p>
          <h2>Looks premium. Reads fast. Feels personal.</h2>
          <p>
            A real ITK issue blends fast scanning with enough context to help you decide instantly what to book.
          </p>
        </div>
        <article className="sample-email">
          <header>
            <div>
              <span>ITK Weekly</span>
              <p>Sunday Briefing · Austin + San Antonio</p>
            </div>
            <span>For John</span>
          </header>
          <h3>Your next six plans, already filtered for your vibe</h3>
          <ul className="sample-event-list">
            {sampleEvents.map((event) => (
              <li key={`${event.day}-${event.name}`}>
                <div className="sample-event-top">
                  <span className="sample-tag">{event.category}</span>
                  <p>
                    {event.day} · {event.time}
                  </p>
                </div>
                <h4>{event.name}</h4>
                <p className="sample-venue">{event.venue}</p>
                <p>{event.description}</p>
              </li>
            ))}
          </ul>
        </article>
      </section>

      <section className="section">
        <h2>Built for people who want to actually do the things they talk about</h2>
        <div className="features-grid">
          {features.map((feature) => (
            <article key={feature.title}>
              <h3>{feature.title}</h3>
              <p>{feature.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section cta-panel">
        <p className="eyebrow">Choose better signal</p>
        <h2>Without ITK, great weekends slip by and your city feels smaller than it really is.</h2>
        <p>
          Join 2,000+ locals building better weekly routines with recommendations tuned to their exact taste and real
          availability.
        </p>
        <Link className="cta-link" href="/onboarding">
          Get My First Newsletter
        </Link>
      </section>

      <footer className="section footer">
        <p>itk-so.vercel.app</p>
        <p>Built for local curiosity, community, and momentum.</p>
      </footer>
    </main>
  );
}
