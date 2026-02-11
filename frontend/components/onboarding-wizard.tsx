"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type SignupPayload = {
  name: string;
  email: string;
  address: string;
  city: string;
  lat: number | null;
  lng: number | null;
  concision_pref: "brief" | "detailed";
  event_radius_miles: number;
  hobbies_raw_text: string;
  goals_raw_text: string;
  goal_types: string[];
  personality_type: string | null;
};

type SignupResponse = {
  user_id: string;
  onboarding_token: string;
};

type OnboardingWizardProps = {
  initialEmail: string;
  initialToken: string;
  googleStatus: string;
  spotifyStatus: string;
};

const stepNames = ["name-location", "hobbies", "goals", "preferences", "integrations", "confirmation"];

const goalOptions = ["dating", "friends", "charity", "community", "hobby-growth", "music-discovery"];

export default function OnboardingWizard({
  initialEmail,
  initialToken,
  googleStatus,
  spotifyStatus,
}: OnboardingWizardProps) {
  const [stepIndex, setStepIndex] = useState(initialToken ? 4 : 0);
  const [email, setEmail] = useState(initialEmail);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [hobbies, setHobbies] = useState("");
  const [goalTypes, setGoalTypes] = useState<string[]>([]);
  const [goalText, setGoalText] = useState("");
  const [concision, setConcision] = useState(40);
  const [radius, setRadius] = useState(20);
  const [token, setToken] = useState(initialToken);
  const [signupComplete, setSignupComplete] = useState(Boolean(initialToken));
  const [csrfToken, setCsrfToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const getCsrf = async () => {
      const response = await fetch("/api/csrf-token", { credentials: "include" });
      if (!response.ok) {
        return;
      }
      const data = (await response.json()) as { csrf_token: string };
      setCsrfToken(data.csrf_token);
    };
    void getCsrf();
  }, []);

  const completionPercent = useMemo(() => Math.round(((stepIndex + 1) / stepNames.length) * 100), [stepIndex]);

  const toggleGoal = (goal: string) => {
    setGoalTypes((current) =>
      current.includes(goal) ? current.filter((entry) => entry !== goal) : [...current, goal]
    );
  };

  const createSignup = async () => {
    const payload: SignupPayload = {
      name,
      email,
      address,
      city,
      lat: null,
      lng: null,
      concision_pref: concision >= 50 ? "detailed" : "brief",
      event_radius_miles: radius,
      hobbies_raw_text: hobbies,
      goals_raw_text: goalText,
      goal_types: goalTypes,
      personality_type: null,
    };

    const response = await fetch("/api/signup", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "x-csrf-token": csrfToken,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error("Unable to save onboarding data.");
    }

    const data = (await response.json()) as SignupResponse;
    setToken(data.onboarding_token);
    setSignupComplete(true);

    await Promise.all(
      ["name-location", "hobbies", "goals", "preferences"].map((stepName) =>
        fetch(`/api/onboarding/${data.onboarding_token}/step`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            "x-csrf-token": csrfToken,
          },
          body: JSON.stringify({ step_name: stepName, metadata: {} }),
        })
      )
    );
  };

  const markStep = async (stepName: string) => {
    if (!token) {
      return;
    }
    await fetch(`/api/onboarding/${token}/step`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "x-csrf-token": csrfToken,
      },
      body: JSON.stringify({ step_name: stepName, metadata: {} }),
    });
  };

  const next = async () => {
    setError("");

    if (!email || !email.includes("@")) {
      setError("Please enter a valid email before continuing.");
      return;
    }

    if (stepIndex === 0 && (!name.trim() || !address.trim() || !city.trim())) {
      setError("Please complete your name, address, and city.");
      return;
    }

    if (stepIndex === 1 && hobbies.trim().length < 8) {
      setError("Add a bit more detail so ITK can understand your interests.");
      return;
    }

    if (stepIndex === 3 && !signupComplete) {
      try {
        setBusy(true);
        await createSignup();
      } catch (signupError) {
        setError(signupError instanceof Error ? signupError.message : "Unexpected signup error");
        return;
      } finally {
        setBusy(false);
      }
    }

    if (stepIndex === 4) {
      await markStep("integrations");
    }

    if (stepIndex === 5) {
      await markStep("confirmation");
      return;
    }

    setStepIndex((current) => Math.min(current + 1, stepNames.length - 1));
  };

  const back = () => {
    setError("");
    setStepIndex((current) => Math.max(current - 1, 0));
  };

  return (
    <div className="onboarding-shell">
      <header>
        <p>Step {stepIndex + 1} of 6</p>
        <h1>Build your first personalized ITK newsletter</h1>
        <div className="progress-bar" aria-hidden="true">
          <span style={{ width: `${completionPercent}%` }} />
        </div>
      </header>

      <section className="onboarding-card">
        {stepIndex === 0 && (
          <div className="step-group">
            <label>
              Email
              <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label>
              Full address
              <input
                value={address}
                onChange={(event) => setAddress(event.target.value)}
                placeholder="Street + city + state"
                required
              />
            </label>
            <label>
              City
              <input value={city} onChange={(event) => setCity(event.target.value)} required />
            </label>
          </div>
        )}

        {stepIndex === 1 && (
          <div className="step-group">
            <h2>What are you into? Word-vomit is perfect.</h2>
            <p>
              Include activities, interests, scenes you like, and anything you want more of in your weekly life.
            </p>
            <textarea
              rows={8}
              value={hobbies}
              onChange={(event) => setHobbies(event.target.value)}
              placeholder="Ex: live indie music, pottery classes, beginner tennis, volunteering, group hikes, startup meetups"
            />
          </div>
        )}

        {stepIndex === 2 && (
          <div className="step-group">
            <h2>What are your goals right now?</h2>
            <div className="goal-grid">
              {goalOptions.map((goal) => (
                <button
                  key={goal}
                  type="button"
                  className={goalTypes.includes(goal) ? "goal-chip active" : "goal-chip"}
                  onClick={() => toggleGoal(goal)}
                >
                  {goal}
                </button>
              ))}
            </div>
            <label>
              Anything else you want ITK to optimize for?
              <textarea
                rows={5}
                value={goalText}
                onChange={(event) => setGoalText(event.target.value)}
                placeholder="Ex: help me meet people who are also into trail running"
              />
            </label>
          </div>
        )}

        {stepIndex === 3 && (
          <div className="step-group">
            <h2>Set your newsletter preferences</h2>
            <label>
              Concision ({concision >= 50 ? "Detailed" : "Brief"})
              <input
                type="range"
                min={0}
                max={100}
                value={concision}
                onChange={(event) => setConcision(Number(event.target.value))}
              />
            </label>
            <label>
              Event radius ({radius} miles)
              <input
                type="range"
                min={1}
                max={75}
                value={radius}
                onChange={(event) => setRadius(Number(event.target.value))}
              />
            </label>
            <p>Next step will save your profile to ITK.</p>
          </div>
        )}

        {stepIndex === 4 && (
          <div className="step-group">
            <h2>Optional: make ITK smarter</h2>
            <p>
              Connect accounts so we can avoid schedule conflicts and better match your music/event taste.
            </p>
            <div className="oauth-grid">
              <a href={token ? `/api/auth/google?token=${token}` : "#"} className="oauth-btn">
                Connect Google Calendar
              </a>
              <a href={token ? `/api/auth/spotify?token=${token}` : "#"} className="oauth-btn">
                Connect Spotify
              </a>
            </div>
            <p className="status-line">
              Google: {googleStatus || "not connected"} | Spotify: {spotifyStatus || "not connected"}
            </p>
          </div>
        )}

        {stepIndex === 5 && (
          <div className="step-group">
            <h2>You are in. Your first issue is being prepared.</h2>
            <p>
              ITK will curate a weekly email based on your profile, goals, and optional integrations. Keep this onboarding
              token for debugging/support:
            </p>
            <code>{token || "pending"}</code>
            <Link className="back-home" href="/">
              Back to landing page
            </Link>
          </div>
        )}
      </section>

      {error && <p className="error-banner">{error}</p>}

      <div className="wizard-actions">
        <button type="button" onClick={back} disabled={stepIndex === 0 || busy}>
          Back
        </button>
        <button type="button" onClick={() => void next()} disabled={busy}>
          {busy ? "Saving..." : stepIndex === 5 ? "Finish" : "Continue"}
        </button>
      </div>
    </div>
  );
}
