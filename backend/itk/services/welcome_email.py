"""Welcome email sent right after signup, linking back to the optional onboarding steps."""

from html import escape
from urllib.parse import quote

from itk.cities import pilot_cities_label
from itk.config import get_settings
from itk.services.mailer import send_email


def render_welcome_html(name: str, onboarding_token: str) -> str:
    app_url = get_settings().app_url.rstrip("/")
    onboarding_url = escape(f"{app_url}/onboarding?token={quote(onboarding_token)}")
    name = escape(name)

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
          <li><strong>Connect Spotify</strong>: we'll match you with live music you'll actually like</li>
          <li><strong>Connect Google Calendar</strong>: we'll only suggest events when you're free</li>
        </ul>
      </div>

      <a href="{onboarding_url}" style="display:inline-block;background:#1a1a1a;color:white;font-size:15px;font-weight:600;padding:14px 32px;border-radius:50px;text-decoration:none;">
        Complete Your Profile →
      </a>

      <p style="font-size:13px;color:#999;margin:24px 0 0;line-height:1.5;">
        Your first newsletter arrives this week. In the meantime, keep doing cool stuff. We'll find the events to match.
      </p>
    </div>

    <p style="text-align:center;font-size:12px;color:#aaa;margin:24px 0 0;">
      ITK, In The Know · {escape(pilot_cities_label())} pilot
    </p>
  </div>
</body>
</html>"""


def send_welcome_email(name: str, email: str, onboarding_token: str) -> bool:
    return send_email(email, f"Welcome to ITK, {name}!", render_welcome_html(name, onboarding_token))
