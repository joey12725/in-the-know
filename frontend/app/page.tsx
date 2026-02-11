import Link from "next/link";

import EmailCaptureForm from "@/components/email-capture-form";

const stats = [
  { value: "2.4h", label: "average weekly time saved" },
  { value: "94%", label: "say ITK events felt personally relevant" },
  { value: "18", label: "cities currently in pilot" },
];

const features = [
  {
    title: "Calendar-aware picks",
    body: "ITK checks your Google Calendar and filters out conflicts before recommending anything.",
  },
  {
    title: "Taste-matched discovery",
    body: "Spotify and hobby signals shape each edition so your city guide feels made for you.",
  },
  {
    title: "Personalized every week",
    body: "No generic blast. Every newsletter is generated from your goals, radius, and personality style.",
  },
];

export default function Home() {
  return (
    <main>
      <section className="hero section">
        <div className="hero-grid">
          <div>
            <p className="eyebrow">In The Know for your city</p>
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
            <p className="card-kicker">This week for Austin</p>
            <h3>For Alex: indie sets, trail mornings, and social volunteering</h3>
            <ul>
              <li>Thu, 7:30 PM - Intimate rooftop jazz session</li>
              <li>Sat, 8:00 AM - Beginner-friendly hill country trail run</li>
              <li>Sun, 11:00 AM - Neighborhood food bank pop-up shift</li>
            </ul>
            <p>Built from your hobbies, goals, Spotify taste, and calendar availability.</p>
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
            <p>Tell us your city and drop a raw brain-dump of what you are into.</p>
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
          <h2>Looks polished. Reads fast. Feels custom.</h2>
          <p>
            Brief mode gives quick hits. Detailed mode includes context, timing notes, and why each event was chosen.
          </p>
        </div>
        <div className="sample-email">
          <header>
            <span>ITK Weekly</span>
            <span>Feb 11 Edition</span>
          </header>
          <h3>This week in Austin, Alex</h3>
          <p>
            Your city has a lot going on. Here are events that match your live music + outdoors + community goals.
          </p>
          <ol>
            <li>Eastside Vinyl Night</li>
            <li>Town Lake Sunrise Ride</li>
            <li>Women in Tech Coffee Social</li>
          </ol>
        </div>
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
        <h2>Success looks like this: you feel connected to your city, every single week.</h2>
        <p>
          Failure looks like another month of saying, we should do more stuff, then staying home. Choose better signal.
        </p>
        <Link className="cta-link" href="/onboarding">
          Get My First Newsletter
        </Link>
      </section>

      <footer className="section footer">
        <p>itk.so</p>
        <p>Built for local curiosity, community, and momentum.</p>
      </footer>
    </main>
  );
}
