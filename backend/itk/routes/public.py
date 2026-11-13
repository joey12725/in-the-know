"""Signup, waitlist, onboarding progress and unsubscribe.

No `from __future__ import annotations` here: slowapi's decorator wraps the endpoint and
FastAPI must be able to resolve the body annotations at import time.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.cities import is_pilot_city, pilot_cities_label
from itk.config import get_settings
from itk.db import get_db
from itk.models import OAuthToken, OnboardingStep, User, UserGoal, UserHobby, WaitlistEntry
from itk.schemas import (
    OnboardingStatusResponse,
    OnboardingStepRequest,
    OnboardingStepResponse,
    SignupRequest,
    SignupResponse,
    WaitlistRequest,
    WaitlistResponse,
)
from itk.security import (
    CSRF_COOKIE_NAME,
    ensure_csrf,
    generate_random_token,
    limiter,
    sanitize_text,
    verify_signed_value,
)
from itk.services.venues import discover_major_music_venues
from itk.services.welcome_email import send_welcome_email

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["public"])


def _user_by_token(db: Session, token: str) -> User:
    user = db.scalar(select(User).where(User.onboarding_token == token))
    if not user:
        raise HTTPException(status_code=404, detail="Onboarding token not found")
    return user


@router.get("/csrf-token")
def issue_csrf_token(response: Response) -> dict[str, str]:
    token = generate_random_token(16)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,  # the browser must read it to echo it back in the header
        secure=get_settings().is_production,
        samesite="lax",
        max_age=60 * 60,
        path="/",
    )
    return {"csrf_token": token}


@router.post("/signup", response_model=SignupResponse)
@limiter.limit(lambda: get_settings().rate_limit_signup)
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)) -> SignupResponse:
    ensure_csrf(request)
    if not is_pilot_city(payload.city):
        raise HTTPException(
            status_code=409,
            detail=f"Pilot currently available only in {pilot_cities_label()}. Join the waitlist instead.",
        )

    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        db.add(user)

    user.name = sanitize_text(payload.name)
    user.address = sanitize_text(payload.address)
    user.city = sanitize_text(payload.city)
    user.lat = payload.lat
    user.lng = payload.lng
    user.concision_pref = payload.concision_pref
    user.event_radius_miles = payload.event_radius_miles
    user.is_subscribed = True
    user.personality_type = payload.personality_type
    user.dating_preference = payload.dating_preference
    user.onboarding_token = generate_random_token(24)
    db.flush()

    db.add(UserHobby(user_id=user.id, raw_text=sanitize_text(payload.hobbies_raw_text), parsed_tags=[]))
    db.add(
        UserGoal(
            user_id=user.id,
            raw_text=sanitize_text(payload.goals_raw_text),
            goal_types=[sanitize_text(goal) for goal in payload.goal_types],
        )
    )
    db.commit()

    # Neither side effect may fail the signup itself.
    try:
        send_welcome_email(user.name, user.email, user.onboarding_token)
    except Exception:
        log.exception("Welcome email failed for user %s", user.id)
    try:
        discover_major_music_venues(db, city=user.city)
    except Exception:
        log.exception("Venue discovery failed for %s", user.city)
        db.rollback()

    return SignupResponse(user_id=user.id, onboarding_token=user.onboarding_token)


@router.post("/waitlist", response_model=WaitlistResponse)
def join_waitlist(request: Request, payload: WaitlistRequest, db: Session = Depends(get_db)) -> WaitlistResponse:
    ensure_csrf(request)
    email = payload.email.lower()
    entry = db.scalar(select(WaitlistEntry).where(WaitlistEntry.email == email))
    if entry is None:
        entry = WaitlistEntry(email=email)
        db.add(entry)
    entry.name = sanitize_text(payload.name)
    entry.address = sanitize_text(payload.address)
    entry.city = sanitize_text(payload.city)
    entry.source = sanitize_text(payload.source) if payload.source else None
    db.commit()
    return WaitlistResponse(
        joined=True, message="You are on the waitlist. We will email when ITK launches in your city."
    )


@router.get("/onboarding/{token}", response_model=OnboardingStatusResponse)
def onboarding_status(token: str, db: Session = Depends(get_db)) -> OnboardingStatusResponse:
    user = _user_by_token(db, token)
    steps = db.scalars(select(OnboardingStep.step_name).where(OnboardingStep.user_id == user.id)).all()
    providers = db.scalars(select(OAuthToken.provider).where(OAuthToken.user_id == user.id)).all()
    return OnboardingStatusResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        city=user.city,
        completed_steps=sorted(set(steps)),
        connected_providers=sorted(set(providers)),
    )


@router.post("/onboarding/{token}/step", response_model=OnboardingStepResponse)
def complete_onboarding_step(
    request: Request,
    token: str,
    payload: OnboardingStepRequest,
    db: Session = Depends(get_db),
) -> OnboardingStepResponse:
    ensure_csrf(request)
    user = _user_by_token(db, token)
    exists = db.scalar(
        select(OnboardingStep).where(OnboardingStep.user_id == user.id, OnboardingStep.step_name == payload.step_name)
    )
    if not exists:
        db.add(OnboardingStep(user_id=user.id, step_name=payload.step_name))
        db.commit()
    return OnboardingStepResponse(step_name=payload.step_name, completed=True)


UNSUBSCRIBED_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Unsubscribed | ITK</title></head>
<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1.5rem;color:#0f172a">
<h1 style="font-size:1.6rem">{heading}</h1><p style="color:#475569;line-height:1.6">{body}</p></body></html>"""


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(token: str = Query(...), db: Session = Depends(get_db)) -> HTMLResponse:
    """One-click unsubscribe from the signed link in every issue's footer."""
    user_id = verify_signed_value(token)
    try:
        user = db.get(User, UUID(user_id)) if user_id else None
    except ValueError:
        user = None
    if not user:
        page = UNSUBSCRIBED_PAGE.format(
            heading="That link has expired",
            body="Reply to any ITK email with “unsubscribe” and we will take care of it.",
        )
        return HTMLResponse(page, status_code=400)

    user.is_subscribed = False
    db.commit()
    page = UNSUBSCRIBED_PAGE.format(
        heading="You're unsubscribed", body="No more weekly issues. Sign up again any time to restart."
    )
    return HTMLResponse(page)
