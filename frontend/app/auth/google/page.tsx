import Link from "next/link";

export default function GoogleAuthPage() {
  return (
    <main className="section auth-page">
      <h1>Google Calendar connected</h1>
      <p>You can return to onboarding to finish setup.</p>
      <Link href="/onboarding">Back to onboarding</Link>
    </main>
  );
}
