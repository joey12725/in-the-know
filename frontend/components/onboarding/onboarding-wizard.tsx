"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, type DatingPreference } from "@/lib/api";
import { isPilotCity, PILOT_CITIES_LABEL } from "@/lib/cities";
import { placesApiKey, usePlacesAutocomplete, type SelectedPlace } from "@/lib/use-places-autocomplete";

import {
  ConfirmationStep,
  GoalsStep,
  HobbiesStep,
  IntegrationsStep,
  PreferencesStep,
  PROCESSING_STAGES,
  ProfileStep,
  WaitlistNotice,
} from "./steps";

const STEPS = ["name-location", "hobbies", "goals", "preferences", "integrations", "confirmation"] as const;
const PROFILE_STEPS = STEPS.slice(0, 4);
const INTEGRATIONS = STEPS.indexOf("integrations");
const CONFIRMATION = STEPS.indexOf("confirmation");
const PROCESSING_STAGE_MS = 950;

type Props = {
  initialEmail: string;
  initialToken: string;
  googleStatus: string;
  spotifyStatus: string;
};

const errorMessage = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback);
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export default function OnboardingWizard({ initialEmail, initialToken, googleStatus, spotifyStatus }: Props) {
  // Returning from an OAuth redirect lands here with ?token=..., straight on the integrations step.
  const [stepIndex, setStepIndex] = useState<number>(initialToken ? INTEGRATIONS : 0);
  const [token, setToken] = useState(initialToken);

  const [email, setEmail] = useState(initialEmail);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [lat, setLat] = useState<number | null>(null);
  const [lng, setLng] = useState<number | null>(null);
  const [hobbies, setHobbies] = useState("");
  const [goalTypes, setGoalTypes] = useState<string[]>([]);
  const [datingPreference, setDatingPreference] = useState<DatingPreference | null>(null);
  const [goalText, setGoalText] = useState("");
  const [concision, setConcision] = useState(40);
  const [radius, setRadius] = useState(20);
  const [connected, setConnected] = useState<string[]>([]);

  const [outsidePilot, setOutsidePilot] = useState(false);
  const [waitlistMessage, setWaitlistMessage] = useState<string | null>(null);
  const [processingStage, setProcessingStage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [finished, setFinished] = useState(false);

  const addressRef = useRef<HTMLInputElement | null>(null);

  const resetPilotState = () => {
    setOutsidePilot(false);
    setWaitlistMessage(null);
  };

  const onPlaceSelected = useCallback((place: SelectedPlace) => {
    if (place.address) setAddress(place.address);
    if (place.city) {
      setCity(place.city);
      setOutsidePilot(false);
      setWaitlistMessage(null);
    }
    setLat(place.lat);
    setLng(place.lng);
  }, []);
  const placesReady = usePlacesAutocomplete(addressRef, onPlaceSelected);

  useEffect(() => {
    if (!initialToken) return;
    api
      .onboardingStatus(initialToken)
      .then((status) => {
        setName(status.name);
        setEmail(status.email);
        setConnected(status.connected_providers);
      })
      .catch(() => setError("That onboarding link is no longer valid. Start again from the home page."));
  }, [initialToken]);

  const toggleGoal = (goal: string) => {
    setGoalTypes((current) => (current.includes(goal) ? current.filter((g) => g !== goal) : [...current, goal]));
    if (goal === "dating") setDatingPreference(null);
  };

  const validate = (): string | null => {
    if (stepIndex === 0) {
      if (!email.includes("@")) return "Please enter a valid email before continuing.";
      if (!name.trim() || !address.trim() || !city.trim()) return "Please complete your name, address, and city.";
    }
    if (stepIndex === 1 && hobbies.trim().length < 8) {
      return "Add a bit more detail so ITK can understand your interests.";
    }
    if (stepIndex === 2 && goalTypes.includes("dating") && !datingPreference) {
      return "Pick what you mean by dating so ITK can tailor recommendations correctly.";
    }
    return null;
  };

  const saveProfile = async () => {
    const { onboarding_token } = await api.signup({
      name,
      email,
      address,
      city,
      lat,
      lng,
      concision_pref: concision >= 50 ? "detailed" : "brief",
      event_radius_miles: radius,
      hobbies_raw_text: hobbies,
      goals_raw_text: goalText,
      goal_types: goalTypes,
      dating_preference: datingPreference,
      personality_type: null,
    });
    setToken(onboarding_token);
    await Promise.all(PROFILE_STEPS.map((step) => api.completeStep(onboarding_token, step)));
  };

  const run = async (action: () => Promise<void>, fallback: string) => {
    setBusy(true);
    try {
      await action();
      return true;
    } catch (caught) {
      setError(errorMessage(caught, fallback));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const joinWaitlist = () =>
    run(async () => {
      const result = await api.joinWaitlist({ name, email, address, city, source: "outside-pilot-onboarding" });
      setWaitlistMessage(result.message);
    }, "Unexpected waitlist error.");

  const next = async () => {
    setError("");
    const problem = validate();
    if (problem) return setError(problem);

    if (stepIndex === 0 && !isPilotCity(city)) return setOutsidePilot(true);

    if (stepIndex === PROFILE_STEPS.length - 1 && !token) {
      if (!(await run(saveProfile, "Unexpected signup error"))) return;
    }

    if (stepIndex === INTEGRATIONS) {
      const ok = await run(async () => {
        for (const stage of PROCESSING_STAGES) {
          setProcessingStage(stage);
          await sleep(PROCESSING_STAGE_MS);
        }
        await api.completeStep(token, "integrations");
      }, "Unable to complete integrations step.");
      setProcessingStage(null);
      if (!ok) return;
    }

    if (stepIndex === CONFIRMATION) {
      if (await run(() => api.completeStep(token, "confirmation").then(() => undefined), "Unable to finish onboarding.")) {
        setFinished(true);
      }
      return;
    }

    setStepIndex((current) => Math.min(current + 1, STEPS.length - 1));
  };

  const back = () => {
    setError("");
    setStepIndex((current) => Math.max(current - 1, 0));
  };

  const providerStatus = {
    google: googleStatus || (connected.includes("google") ? "connected" : ""),
    spotify: spotifyStatus || (connected.includes("spotify") ? "connected" : ""),
  };

  if (finished) {
    return (
      <div className="onboarding-shell">
        <section className="onboarding-card success-panel">
          <div className="confetti-rain" aria-hidden="true">
            {Array.from({ length: 16 }).map((_, index) => (
              <span key={index} style={{ left: `${(index * 13 + 6) % 100}%`, animationDelay: `${index * 90}ms` }} />
            ))}
          </div>
          <p className="eyebrow">You are all set</p>
          <h2>Welcome to ITK{name ? `, ${name.split(" ")[0]}` : ""}.</h2>
          <p>Your personalized {PILOT_CITIES_LABEL} event briefing is now in motion.</p>
          <Link className="cta-link" href="/">
            Return to landing page
          </Link>
        </section>
      </div>
    );
  }

  const showingWaitlist = stepIndex === 0 && outsidePilot;

  return (
    <div className="onboarding-shell">
      <header>
        <p>
          Step {stepIndex + 1} of {STEPS.length}
        </p>
        <h1>Build your first personalized ITK newsletter</h1>
        <div className="progress-bar" aria-hidden="true">
          <span style={{ width: `${Math.round(((stepIndex + 1) / STEPS.length) * 100)}%` }} />
        </div>
      </header>

      <section className="onboarding-card">
        {stepIndex === 0 &&
          (showingWaitlist ? (
            <WaitlistNotice city={city} joinedMessage={waitlistMessage} />
          ) : (
            <ProfileStep
              email={email}
              name={name}
              address={address}
              city={city}
              onEmail={setEmail}
              onName={setName}
              onAddress={(value) => {
                setAddress(value);
                setLat(null);
                setLng(null);
                resetPilotState();
              }}
              onCity={(value) => {
                setCity(value);
                resetPilotState();
              }}
              addressRef={addressRef}
              autocompleteStatus={
                placesApiKey
                  ? placesReady
                    ? "Address autocomplete is on. Pick a suggestion to auto-fill city."
                    : "Loading address autocomplete..."
                  : null
              }
            />
          ))}
        {stepIndex === 1 && <HobbiesStep hobbies={hobbies} onChange={setHobbies} />}
        {stepIndex === 2 && (
          <GoalsStep
            goalTypes={goalTypes}
            onToggleGoal={toggleGoal}
            datingPreference={datingPreference}
            onDatingPreference={setDatingPreference}
            goalText={goalText}
            onGoalText={setGoalText}
          />
        )}
        {stepIndex === 3 && (
          <PreferencesStep concision={concision} onConcision={setConcision} radius={radius} onRadius={setRadius} />
        )}
        {stepIndex === INTEGRATIONS && (
          <IntegrationsStep
            processingStage={processingStage}
            connectUrl={(provider) => (token ? api.oauthUrl(provider, token) : null)}
            status={providerStatus}
          />
        )}
        {stepIndex === CONFIRMATION && <ConfirmationStep />}
      </section>

      {error && <p className="error-banner">{error}</p>}

      {showingWaitlist ? (
        <div className="wizard-actions">
          {waitlistMessage === null ? (
            <>
              <button type="button" onClick={resetPilotState} disabled={busy}>
                Use a pilot city
              </button>
              <button type="button" onClick={() => void joinWaitlist()} disabled={busy}>
                {busy ? "Joining..." : "Join waitlist"}
              </button>
            </>
          ) : (
            <Link className="cta-link" href="/">
              Back to landing page
            </Link>
          )}
        </div>
      ) : (
        <div className="wizard-actions">
          <button type="button" onClick={back} disabled={stepIndex === 0 || busy}>
            Back
          </button>
          <button type="button" onClick={() => void next()} disabled={busy}>
            {busy && stepIndex === INTEGRATIONS
              ? "Processing..."
              : busy
                ? "Saving..."
                : stepIndex === CONFIRMATION
                  ? "Finish"
                  : "Continue"}
          </button>
        </div>
      )}
    </div>
  );
}
