"use client";

import { RefObject } from "react";

import type { DatingPreference } from "@/lib/api";
import { PILOT_CITIES_LABEL } from "@/lib/cities";

export const GOAL_OPTIONS = ["dating", "friends", "charity", "community", "hobby-growth", "music-discovery"];

export const DATING_OPTIONS: Array<{ value: DatingPreference; label: string; description: string }> = [
  {
    value: "date_night_spots",
    label: "Date night spots",
    description: "Restaurants, activities, and experiences for couples.",
  },
  {
    value: "meeting_people",
    label: "Meeting people",
    description: "Singles events, social mixers, and community spaces to meet people.",
  },
  { value: "both", label: "Both", description: "Mix date-night recommendations with social events to meet people." },
];

export const PROCESSING_STAGES = [
  "Analyzing your interests...",
  "Finding events near you...",
  "Personalizing your experience...",
];

type Setter<T> = (value: T) => void;

type ProfileStepProps = {
  email: string;
  name: string;
  address: string;
  city: string;
  onEmail: Setter<string>;
  onName: Setter<string>;
  onAddress: Setter<string>;
  onCity: Setter<string>;
  addressRef: RefObject<HTMLInputElement | null>;
  autocompleteStatus: string | null;
};

export function ProfileStep({
  email,
  name,
  address,
  city,
  onEmail,
  onName,
  onAddress,
  onCity,
  addressRef,
  autocompleteStatus,
}: ProfileStepProps) {
  return (
    <div className="step-group">
      <label>
        Email
        <input type="email" value={email} onChange={(e) => onEmail(e.target.value)} required />
      </label>
      <label>
        Name
        <input value={name} onChange={(e) => onName(e.target.value)} required />
      </label>
      <label>
        Full address
        <input
          ref={addressRef}
          value={address}
          onChange={(e) => onAddress(e.target.value)}
          placeholder="Street + city + state"
          required
        />
      </label>
      {autocompleteStatus && <p className="status-line">{autocompleteStatus}</p>}
      <label>
        City
        <input value={city} onChange={(e) => onCity(e.target.value)} required />
      </label>
    </div>
  );
}

export function WaitlistNotice({ city, joinedMessage }: { city: string; joinedMessage: string | null }) {
  if (joinedMessage !== null) {
    return (
      <div className="step-group waitlist-panel">
        <h2>You are on the waitlist.</h2>
        <p>{joinedMessage || "Thanks. We will email you when ITK launches in your city."}</p>
        <p className="status-line">Pilot access is currently {PILOT_CITIES_LABEL} only.</p>
      </div>
    );
  }
  return (
    <div className="step-group waitlist-panel">
      <h2>ITK is in pilot mode right now.</h2>
      <p>
        We are currently available only in {PILOT_CITIES_LABEL}. Join the waitlist and we will notify you as soon as we
        open in {city || "your city"}.
      </p>
      <p className="status-line">You can also go back and enter an address in a pilot city to continue now.</p>
    </div>
  );
}

export function HobbiesStep({ hobbies, onChange }: { hobbies: string; onChange: Setter<string> }) {
  return (
    <div className="step-group">
      <h2>What are you into? Word-vomit is perfect.</h2>
      <p>Include activities, interests, scenes you like, and anything you want more of in your weekly life.</p>
      <textarea
        rows={8}
        value={hobbies}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Ex: live indie music, pottery classes, beginner tennis, volunteering, group hikes, startup meetups"
      />
    </div>
  );
}

export function GoalsStep(props: {
  goalTypes: string[];
  onToggleGoal: Setter<string>;
  datingPreference: DatingPreference | null;
  onDatingPreference: Setter<DatingPreference>;
  goalText: string;
  onGoalText: Setter<string>;
}) {
  const chip = (active: boolean) => (active ? "goal-chip active" : "goal-chip");
  const selectedDating = DATING_OPTIONS.find((option) => option.value === props.datingPreference);
  return (
    <div className="step-group">
      <h2>What are your goals right now?</h2>
      <div className="goal-grid">
        {GOAL_OPTIONS.map((goal) => (
          <button
            key={goal}
            type="button"
            className={chip(props.goalTypes.includes(goal))}
            onClick={() => props.onToggleGoal(goal)}
          >
            {goal}
          </button>
        ))}
      </div>
      {props.goalTypes.includes("dating") && (
        <div className="dating-followup">
          <h3>When you say dating, which one do you want?</h3>
          <div className="goal-grid">
            {DATING_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={chip(props.datingPreference === option.value)}
                onClick={() => props.onDatingPreference(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <p className="status-line">
            {selectedDating?.description ??
              "Choose one so ITK can separate date-night ideas from meet-people recommendations."}
          </p>
        </div>
      )}
      <label>
        Anything else you want ITK to optimize for?
        <textarea
          rows={5}
          value={props.goalText}
          onChange={(e) => props.onGoalText(e.target.value)}
          placeholder="Ex: help me meet people who are also into trail running"
        />
      </label>
    </div>
  );
}

export function PreferencesStep(props: {
  concision: number;
  onConcision: Setter<number>;
  radius: number;
  onRadius: Setter<number>;
}) {
  return (
    <div className="step-group">
      <h2>Set your newsletter preferences</h2>
      <label>
        Concision ({props.concision >= 50 ? "Detailed" : "Brief"})
        <input
          type="range"
          min={0}
          max={100}
          value={props.concision}
          onChange={(e) => props.onConcision(Number(e.target.value))}
        />
      </label>
      <label>
        Event radius ({props.radius} miles)
        <input
          type="range"
          min={1}
          max={75}
          value={props.radius}
          onChange={(e) => props.onRadius(Number(e.target.value))}
        />
      </label>
      <p>Next step will save your profile to ITK.</p>
    </div>
  );
}

const PROVIDER_LABELS = { google: "Google Calendar", spotify: "Spotify" } as const;

export function IntegrationsStep(props: {
  processingStage: string | null;
  connectUrl: (provider: "google" | "spotify") => string | null;
  status: Record<"google" | "spotify", string>;
}) {
  if (props.processingStage) {
    return (
      <div className="step-group">
        <h2>Making ITK smarter...</h2>
        <div className="ai-loader" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <p className="status-line status-active">{props.processingStage}</p>
      </div>
    );
  }
  return (
    <div className="step-group">
      <h2>Optional: make ITK smarter</h2>
      <p>Connect accounts so we can avoid schedule conflicts and better match your music/event taste.</p>
      <div className="oauth-grid">
        {(["google", "spotify"] as const).map((provider) => {
          const href = props.connectUrl(provider);
          return (
            <a
              key={provider}
              href={href ?? undefined}
              aria-disabled={!href}
              className="oauth-btn"
            >
              {props.status[provider] === "connected" ? "✓ " : "Connect "}
              {PROVIDER_LABELS[provider]}
            </a>
          );
        })}
      </div>
      <p className="status-line">
        Google: {props.status.google || "not connected"} | Spotify: {props.status.spotify || "not connected"}
      </p>
    </div>
  );
}

export function ConfirmationStep() {
  return (
    <div className="step-group">
      <h2>Ready to launch your first issue?</h2>
      <p>
        ITK will curate a weekly email based on your profile, goals, and optional integrations. Your welcome email has a
        link back here if you want to connect more accounts later.
      </p>
      <p className="status-line">Click Finish to lock everything in and start receiving your personalized briefings.</p>
    </div>
  );
}
