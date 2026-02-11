"""Welcome / onboarding email sent immediately after signup."""
from __future__ import annotations

import httpx

from core.config import get_settings


def _render_onboarding_html(name: str, onboarding_token: str) -> str:
    settings = get_settings()
    app_url = settings.app_url.rstrip("/")
    onboarding_url = f"{app_url}/onboarding?token={onboarding_token}"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f1ec;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:560px;margin:0 auto;padding:40px 24px;">
    <div style="background:white;border-radius:16px;padding:40px 32px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
      
      <p style="font-size:12px;text-transform:uppercase;letter-spacing:2px;color:#7dc7a8;margin:0 0 16px;">In The Know</p>
      
      <h1 style="font-size:28px;font-weight:700;color:#1a1a1a;margin:0 0 8px;">Welcome, {name}!</h1>
      
      <p style="font-size:16px;color:#555;line-height:1.6;margin:0 0 24px;">
        You're in. Every week, we'll send you a personalized guide to the best events in your city, built around your interests, schedule, and taste.
      </p>

      <p style="font-size:16px;color:#555;line-height:1.6;margin:0 0 24px;">
        But first, help us make your newsletter even better. These optional steps take 2 minutes and make a big difference:
      </p>

      <div style="background:#f9f7f4;border-radius:12px;padding:20px 24px;margin:0 0 24px;">
        <p style="font-size:14px;font-weight:600;color:#1a1a1a;margin:0 0 12px;">🎯 Make ITK smarter:</p>
        <ul style="margin:0;padding:0 0 0 20px;color:#555;font-size:14px;line-height:2;">
          <li><strong>Connect Spotify</strong> — we'll match you with live music you'll actually like</li>
          <li><strong>Connect Google Calendar</strong> — we'll only suggest events when you're free</li>
          <li><strong>Quick personality quiz</strong> — helps us nail the vibe</li>
        </ul>
      </div>

      <a href="{onboarding_url}" style="display:inline-block;background:#1a1a1a;color:white;font-size:15px;font-weight:600;padding:14px 32px;border-radius:50px;text-decoration:none;">
        Complete Your Profile →
      </a>

      <p style="font-size:13px;color:#999;margin:24px 0 0;line-height:1.5;">
        Your first newsletter arrives this week. In the meantime, keep doing cool stuff — we'll find the events to match.
      </p>
    </div>

    <p style="text-align:center;font-size:12px;color:#aaa;margin:24px 0 0;">
      ITK — In The Know · Austin & San Antonio pilot
    </p>
  </div>
</body>
</html>"""


def send_onboarding_email(name: str, email: str, onboarding_token: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        return

    html = _render_onboarding_html(name, onboarding_token)

    with httpx.Client(timeout=20) as client:
        client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": [email],
                "subject": f"Welcome to ITK, {name}! 🎉",
                "html": html,
            },
        ).raise_for_status()
