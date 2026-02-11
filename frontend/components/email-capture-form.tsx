"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function EmailCaptureForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = email.trim();
    if (!normalized) {
      return;
    }
    router.push(`/onboarding?email=${encodeURIComponent(normalized)}`);
  };

  return (
    <form className="capture-form" onSubmit={onSubmit}>
      <label htmlFor="hero-email" className="sr-only">
        Email
      </label>
      <input
        id="hero-email"
        type="email"
        required
        placeholder="you@yourcity.com"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <button type="submit">Get My First Newsletter</button>
    </form>
  );
}
