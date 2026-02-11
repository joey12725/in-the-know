"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

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

type WaitlistResponse = {
  joined: boolean;
  message: string;
};

type OnboardingWizardProps = {
  initialEmail: string;
  initialToken: string;
  googleStatus: string;
  spotifyStatus: string;
};

const stepNames = ["name-location", "hobbies", "goals", "preferences", "integrations", "confirmation"];

const goalOptions = ["dating", "friends", "charity", "community", "hobby-growth", "music-discovery"];
const placesApiKey = process.env.NEXT_PUBLIC_GOOGLE_PLACES_API_KEY ?? "";
const processingStages = [
  "Analyzing your interests...",
  "Finding events near you...",
  "Personalizing your experience...",
];
const pilotCities = new Set(["austin", "san antonio"]);

type GoogleAddressComponent = {
  long_name: string;
  short_name: string;
  types: string[];
};

type GooglePlaceResult = {
  address_components?: GoogleAddressComponent[];
  formatted_address?: string;
  geometry?: {
    location?: {
      lat: () => number;
      lng: () => number;
    };
  };
};

type GoogleAutocompleteInstance = {
  addListener: (eventName: "place_changed", handler: () => void) => void;
  getPlace: () => GooglePlaceResult;
};

type GoogleMapsWindow = Window & {
  google?: {
    maps?: {
      LatLng: new (lat: number, lng: number) => unknown;
      LatLngBounds: new (sw: unknown, ne: unknown) => unknown;
      places?: {
        Autocomplete: new (
          input: HTMLInputElement,
          options: {
            types: string[];
            componentRestrictions: { country: string };
            fields: string[];
            bounds: unknown;
          }
        ) => GoogleAutocompleteInstance;
      };
    };
  };
};

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
  const [lat, setLat] = useState<number | null>(null);
  const [lng, setLng] = useState<number | null>(null);
  const [placesReady, setPlacesReady] = useState(false);
  const [concision, setConcision] = useState(40);
  const [radius, setRadius] = useState(20);
  const [token, setToken] = useState(initialToken);
  const [signupComplete, setSignupComplete] = useState(Boolean(initialToken));
  const [csrfToken, setCsrfToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [waitlistBusy, setWaitlistBusy] = useState(false);
  const [waitlistSubmitted, setWaitlistSubmitted] = useState(false);
  const [waitlistMessage, setWaitlistMessage] = useState("");
  const [outsidePilot, setOutsidePilot] = useState(false);
  const [processingStageIndex, setProcessingStageIndex] = useState(-1);
  const [finished, setFinished] = useState(false);
  const addressInputRef = useRef<HTMLInputElement | null>(null);
  const placesAutocompleteRef = useRef<GoogleAutocompleteInstance | null>(null);

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

  useEffect(() => {
    if (!placesApiKey || !addressInputRef.current) {
      return;
    }

    const getCityFromComponents = (components: GoogleAddressComponent[] = []) => {
      const locality = components.find((entry) => entry.types.includes("locality"))?.long_name;
      if (locality) {
        return locality;
      }
      const sublocality = components.find((entry) => entry.types.includes("sublocality"))?.long_name;
      if (sublocality) {
        return sublocality;
      }
      const county = components.find((entry) => entry.types.includes("administrative_area_level_2"))?.long_name;
      return county?.replace(/ County$/i, "") ?? "";
    };

    const initializeAutocomplete = () => {
      const googleMaps = (window as GoogleMapsWindow).google;
      if (!googleMaps?.maps?.places || !addressInputRef.current || placesAutocompleteRef.current) {
        return;
      }

      const bounds = new googleMaps.maps.LatLngBounds(
        new googleMaps.maps.LatLng(29.02, -99.75),
        new googleMaps.maps.LatLng(30.91, -97.02)
      );

      const autocomplete = new googleMaps.maps.places.Autocomplete(addressInputRef.current, {
        types: ["address"],
        componentRestrictions: { country: "us" },
        fields: ["address_components", "formatted_address", "geometry"],
        bounds,
      });

      autocomplete.addListener("place_changed", () => {
        const place = autocomplete.getPlace() as GooglePlaceResult;
        if (place.formatted_address) {
          setAddress(place.formatted_address);
        }
        if (place.address_components) {
          const derivedCity = getCityFromComponents(place.address_components);
          if (derivedCity) {
            setCity(derivedCity);
            setOutsidePilot(false);
            setWaitlistSubmitted(false);
            setWaitlistMessage("");
          }
        }
        const selectedLat = place.geometry?.location?.lat();
        const selectedLng = place.geometry?.location?.lng();
        setLat(typeof selectedLat === "number" ? selectedLat : null);
        setLng(typeof selectedLng === "number" ? selectedLng : null);
      });

      placesAutocompleteRef.current = autocomplete;
      setPlacesReady(true);
    };

    const existingScript = document.getElementById("google-places-script") as HTMLScriptElement | null;
    if ((window as GoogleMapsWindow).google?.maps?.places) {
      initializeAutocomplete();
      return;
    }

    if (!existingScript) {
      const script = document.createElement("script");
      script.id = "google-places-script";
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(placesApiKey)}&libraries=places`;
      script.async = true;
      script.defer = true;
      script.addEventListener("load", initializeAutocomplete);
      document.head.appendChild(script);

      return () => {
        script.removeEventListener("load", initializeAutocomplete);
      };
    }

    existingScript.addEventListener("load", initializeAutocomplete);
    return () => {
      existingScript.removeEventListener("load", initializeAutocomplete);
    };
  }, []);

  const completionPercent = useMemo(() => Math.round(((stepIndex + 1) / stepNames.length) * 100), [stepIndex]);

  const normalizeCity = (value: string) => {
    let trimmed = " ".join(value.trim().toLowerCase().replaceAll(".", "").split());
    if (trimmed.includes(",")) {
      [trimmed] = trimmed.split(",", 1);
    }
    for (const suffix of [", tx", ", texas", " tx", " texas"]) {
      if (trimmed.endsWith(suffix)) {
        trimmed = trimmed.slice(0, trimmed.length - suffix.length).trim();
        break;
      }
    }
    return trimmed
      .split(" ")
      .filter((token) => Number.isNaN(Number(token)))
      .join(" ");
  };

  const isPilotCity = (value: string) => pilotCities.has(normalizeCity(value));

  const toggleGoal = (goal: string) => {
    setGoalTypes((current) =>
      current.includes(goal) ? current.filter((entry) => entry !== goal) : [...current, goal]
    );
  };

  const runProcessingAnimation = async () => {
    for (let index = 0; index < processingStages.length; index += 1) {
      setProcessingStageIndex(index);
      await new Promise((resolve) => setTimeout(resolve, 950));
    }
  };

  const joinWaitlist = async () => {
    if (waitlistSubmitted) {
      return;
    }

    setError("");
    try {
      setWaitlistBusy(true);
      const response = await fetch("/api/waitlist", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "x-csrf-token": csrfToken,
        },
        body: JSON.stringify({
          name,
          email,
          address,
          city,
          source: "outside-pilot-onboarding",
        }),
      });

      if (!response.ok) {
        const details = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(details?.detail || "Unable to join waitlist right now.");
      }

      const data = (await response.json()) as WaitlistResponse;
      setWaitlistMessage(data.message);
      setWaitlistSubmitted(true);
    } catch (waitlistError) {
      setError(waitlistError instanceof Error ? waitlistError.message : "Unexpected waitlist error.");
    } finally {
      setWaitlistBusy(false);
    }
  };

  const createSignup = async () => {
    const payload: SignupPayload = {
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

    if (stepIndex === 0 && outsidePilot) {
      await joinWaitlist();
      return;
    }

    if (stepIndex === 0 && (!name.trim() || !address.trim() || !city.trim())) {
      setError("Please complete your name, address, and city.");
      return;
    }

    if (stepIndex === 0 && !isPilotCity(city)) {
      setOutsidePilot(true);
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
      try {
        setBusy(true);
        await runProcessingAnimation();
        await markStep("integrations");
      } catch (integrationError) {
        setError(integrationError instanceof Error ? integrationError.message : "Unable to complete integrations step.");
        return;
      } finally {
        setBusy(false);
      }
      setProcessingStageIndex(-1);
      setStepIndex((current) => Math.min(current + 1, stepNames.length - 1));
      return;
    }

    if (stepIndex === 5) {
      try {
        setBusy(true);
        await markStep("confirmation");
        setFinished(true);
      } catch (confirmationError) {
        setError(confirmationError instanceof Error ? confirmationError.message : "Unable to finish onboarding.");
      } finally {
        setBusy(false);
      }
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
      {finished && (
        <section className="onboarding-card success-panel">
          <div className="confetti-rain" aria-hidden="true">
            {Array.from({ length: 16 }).map((_, index) => (
              <span
                key={`confetti-${index}`}
                style={{ left: `${(index * 13 + 6) % 100}%`, animationDelay: `${index * 90}ms` }}
              />
            ))}
          </div>
          <p className="eyebrow">You are all set</p>
          <h2>Welcome to ITK, John.</h2>
          <p>Your personalized Austin + San Antonio event briefing is now in motion.</p>
          <Link className="cta-link" href="/">
            Return to landing page
          </Link>
        </section>
      )}

      {!finished && (
        <>
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
                {!outsidePilot && (
                  <>
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
                        ref={addressInputRef}
                        value={address}
                        onChange={(event) => {
                          setAddress(event.target.value);
                          setLat(null);
                          setLng(null);
                          setOutsidePilot(false);
                          setWaitlistSubmitted(false);
                          setWaitlistMessage("");
                        }}
                        placeholder="Street + city + state"
                        required
                      />
                    </label>
                    {placesApiKey && (
                      <p className="status-line">
                        {placesReady
                          ? "Address autocomplete is on. Pick a suggestion to auto-fill city."
                          : "Loading address autocomplete..."}
                      </p>
                    )}
                    <label>
                      City
                      <input
                        value={city}
                        onChange={(event) => {
                          setCity(event.target.value);
                          setOutsidePilot(false);
                          setWaitlistSubmitted(false);
                          setWaitlistMessage("");
                        }}
                        required
                      />
                    </label>
                  </>
                )}
                {outsidePilot && !waitlistSubmitted && (
                  <div className="waitlist-panel">
                    <h2>ITK is in pilot mode right now.</h2>
                    <p>
                      We are currently available only in Austin and San Antonio. Join the waitlist and we will notify you
                      as soon as we open in {city || "your city"}.
                    </p>
                    <p className="status-line">You can also go back and enter an Austin or San Antonio address to continue now.</p>
                  </div>
                )}
                {outsidePilot && waitlistSubmitted && (
                  <div className="waitlist-panel">
                    <h2>You are on the waitlist.</h2>
                    <p>{waitlistMessage || "Thanks. We will email you when ITK launches in your city."}</p>
                    <p className="status-line">Pilot access is currently Austin and San Antonio only.</p>
                  </div>
                )}
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
                {busy ? (
                  <>
                    <h2>Making ITK smarter...</h2>
                    <div className="ai-loader" aria-hidden="true">
                      <span />
                      <span />
                      <span />
                    </div>
                    <p className="status-line status-active">{processingStages[processingStageIndex] || processingStages[0]}</p>
                  </>
                ) : (
                  <>
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
                  </>
                )}
              </div>
            )}

            {stepIndex === 5 && (
              <div className="step-group">
                <h2>Ready to launch your first issue?</h2>
                <p>
                  ITK will curate a weekly email based on your profile, goals, and optional integrations. Keep this onboarding
                  token for debugging/support:
                </p>
                <code>{token || "pending"}</code>
                <p className="status-line">Click Finish to lock everything in and start receiving your personalized briefings.</p>
              </div>
            )}
          </section>

          {error && <p className="error-banner">{error}</p>}

          {stepIndex === 0 && outsidePilot ? (
            <div className="wizard-actions">
              {!waitlistSubmitted && (
                <button
                  type="button"
                  onClick={() => {
                    setOutsidePilot(false);
                    setWaitlistSubmitted(false);
                    setWaitlistMessage("");
                    setError("");
                  }}
                  disabled={waitlistBusy}
                >
                  Use Austin / San Antonio
                </button>
              )}
              {!waitlistSubmitted ? (
                <button type="button" onClick={() => void joinWaitlist()} disabled={waitlistBusy}>
                  {waitlistBusy ? "Joining..." : "Join waitlist"}
                </button>
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
                {busy && stepIndex === 4 ? "Processing..." : busy ? "Saving..." : stepIndex === 5 ? "Finish" : "Continue"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
