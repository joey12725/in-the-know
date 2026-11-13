// Browser-side client for the FastAPI backend (reached through the /api proxy route).

export type SignupPayload = {
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
  dating_preference: DatingPreference | null;
  personality_type: string | null;
};

export type DatingPreference = "date_night_spots" | "meeting_people" | "both";

export type SignupResponse = { user_id: string; onboarding_token: string };
export type WaitlistPayload = { name: string; email: string; address: string; city: string; source: string };
export type WaitlistResponse = { joined: boolean; message: string };
export type OnboardingStatus = {
  user_id: string;
  name: string;
  email: string;
  city: string;
  completed_steps: string[];
  connected_providers: string[];
};

export class ApiError extends Error {}

let csrfToken: Promise<string> | null = null;

function getCsrfToken(): Promise<string> {
  csrfToken ??= fetch("/api/csrf-token", { credentials: "include" })
    .then((response) => (response.ok ? response.json() : { csrf_token: "" }))
    .then((data: { csrf_token: string }) => data.csrf_token);
  return csrfToken;
}

async function request<T>(path: string, init: RequestInit = {}, fallbackError = "Something went wrong."): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.method && init.method !== "GET") {
    headers.set("Content-Type", "application/json");
    headers.set("x-csrf-token", await getCsrfToken());
  }
  const response = await fetch(path, { ...init, headers, credentials: "include" });
  if (!response.ok) {
    const details = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new ApiError(typeof details?.detail === "string" ? details.detail : fallbackError);
  }
  return (await response.json()) as T;
}

const post = <T>(path: string, body: unknown, fallbackError?: string) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) }, fallbackError);

export const api = {
  signup: (payload: SignupPayload) =>
    post<SignupResponse>("/api/signup", payload, "Unable to save onboarding data."),
  joinWaitlist: (payload: WaitlistPayload) =>
    post<WaitlistResponse>("/api/waitlist", payload, "Unable to join waitlist right now."),
  completeStep: (token: string, stepName: string) =>
    post<{ completed: boolean }>(`/api/onboarding/${encodeURIComponent(token)}/step`, { step_name: stepName }),
  onboardingStatus: (token: string) => request<OnboardingStatus>(`/api/onboarding/${encodeURIComponent(token)}`),
  oauthUrl: (provider: "google" | "spotify", token: string) =>
    `/api/auth/${provider}?token=${encodeURIComponent(token)}`,
};
