import OnboardingWizard from "@/components/onboarding-wizard";

type OnboardingPageProps = {
  searchParams: Promise<{
    email?: string;
    token?: string;
    google?: string;
    spotify?: string;
  }>;
};

export default async function OnboardingPage({ searchParams }: OnboardingPageProps) {
  const params = await searchParams;

  return (
    <main className="section onboarding-page">
      <OnboardingWizard
        initialEmail={params.email ?? ""}
        initialToken={params.token ?? ""}
        googleStatus={params.google ?? ""}
        spotifyStatus={params.spotify ?? ""}
      />
    </main>
  );
}
