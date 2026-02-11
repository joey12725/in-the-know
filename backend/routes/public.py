from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.rate_limit import limiter
from db.session import get_db
from models import OnboardingStep, User, UserGoal, UserHobby, WaitlistEntry
from schemas.public import (
    OnboardingStatusResponse,
    OnboardingStepRequest,
    OnboardingStepResponse,
    SignupRequest,
    SignupResponse,
    WaitlistRequest,
    WaitlistResponse,
)
from services.onboarding_email import send_onboarding_email
from services.venues import discover_major_music_venues
from utils.sanitization import sanitize_text
from utils.security import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    ensure_csrf,
    generate_random_token,
    make_signed_value,
)

router = APIRouter(prefix="/api", tags=["public"])
settings = get_settings()
pilot_cities = {"austin", "san antonio"}


def _normalize_city_for_pilot(city: str) -> str:
    normalized = " ".join(city.strip().lower().replace(".", "").split())
    if "," in normalized:
        normalized = normalized.split(",", 1)[0].strip()
    for suffix in (", tx", ", texas", " tx", " texas"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
            break
    normalized = " ".join(token for token in normalized.split() if not token.isdigit())
    return normalized


def _is_pilot_city(city: str) -> bool:
    return _normalize_city_for_pilot(city) in pilot_cities


@router.get("/csrf-token")
def issue_csrf_token(response: Response) -> dict:
    token = generate_random_token(16)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=60 * 60,
        path="/",
    )
    return {"csrf_token": token}


@router.post("/signup", response_model=SignupResponse)
@limiter.limit(settings.rate_limit_signup)
def signup(request: Request, response: Response, payload: SignupRequest, db: Session = Depends(get_db)) -> SignupResponse:
    ensure_csrf(request)
    if not _is_pilot_city(payload.city):
        raise HTTPException(
            status_code=409,
            detail="Pilot currently available only in Austin and San Antonio. Join the waitlist instead.",
        )

    existing_user = db.scalar(select(User).where(User.email == payload.email.lower()))
    onboarding_token = generate_random_token(24)

    if existing_user:
        user = existing_user
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
        user.onboarding_token = onboarding_token
    else:
        user = User(
            name=sanitize_text(payload.name),
            email=payload.email.lower(),
            address=sanitize_text(payload.address),
            city=sanitize_text(payload.city),
            lat=payload.lat,
            lng=payload.lng,
            concision_pref=payload.concision_pref,
            event_radius_miles=payload.event_radius_miles,
            is_subscribed=True,
            personality_type=payload.personality_type,
            dating_preference=payload.dating_preference,
            onboarding_token=onboarding_token,
        )
        db.add(user)
        db.flush()

    db.add(
        UserHobby(
            user_id=user.id,
            raw_text=sanitize_text(payload.hobbies_raw_text),
            parsed_tags=[],
        )
    )

    db.add(
        UserGoal(
            user_id=user.id,
            raw_text=sanitize_text(payload.goals_raw_text),
            goal_types=[sanitize_text(goal) for goal in payload.goal_types],
        )
    )

    db.commit()
    db.refresh(user)

    session_value = make_signed_value(str(user.id))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_value,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )

    # Fire onboarding email (non-blocking, don't fail signup if email fails)
    try:
        send_onboarding_email(user.name, user.email, user.onboarding_token)
    except Exception:
        pass  # Email failure shouldn't block signup

    # Prime venue knowledge for pilot-city users on enrollment.
    try:
        discover_major_music_venues(db, city=user.city)
    except Exception:
        db.rollback()

    return SignupResponse(user_id=user.id, onboarding_token=user.onboarding_token)


@router.post("/waitlist", response_model=WaitlistResponse)
def join_waitlist(request: Request, payload: WaitlistRequest, db: Session = Depends(get_db)) -> WaitlistResponse:
    ensure_csrf(request)
    email = payload.email.lower()

    existing_entry = db.scalar(select(WaitlistEntry).where(WaitlistEntry.email == email))
    if existing_entry:
        existing_entry.name = sanitize_text(payload.name)
        existing_entry.address = sanitize_text(payload.address)
        existing_entry.city = sanitize_text(payload.city)
        existing_entry.source = sanitize_text(payload.source) if payload.source else None
    else:
        db.add(
            WaitlistEntry(
                email=email,
                name=sanitize_text(payload.name),
                address=sanitize_text(payload.address),
                city=sanitize_text(payload.city),
                source=sanitize_text(payload.source) if payload.source else None,
            )
        )

    db.commit()
    return WaitlistResponse(joined=True, message="You are on the waitlist. We will email when ITK launches in your city.")


@router.get("/onboarding/{token}", response_model=OnboardingStatusResponse)
def onboarding_status(token: str, db: Session = Depends(get_db)) -> OnboardingStatusResponse:
    user = db.scalar(select(User).where(User.onboarding_token == token))
    if not user:
        raise HTTPException(status_code=404, detail="Onboarding token not found")

    completed_steps = db.scalars(select(OnboardingStep.step_name).where(OnboardingStep.user_id == user.id)).all()
    return OnboardingStatusResponse(user_id=user.id, email=user.email, completed_steps=sorted(set(completed_steps)))


@router.post("/onboarding/{token}/step", response_model=OnboardingStepResponse)
def complete_onboarding_step(
    request: Request,
    token: str,
    payload: OnboardingStepRequest,
    db: Session = Depends(get_db),
) -> OnboardingStepResponse:
    ensure_csrf(request)
    user = db.scalar(select(User).where(User.onboarding_token == token))
    if not user:
        raise HTTPException(status_code=404, detail="Onboarding token not found")

    existing = db.scalar(
        select(OnboardingStep).where(OnboardingStep.user_id == user.id, OnboardingStep.step_name == payload.step_name)
    )
    if existing:
        return OnboardingStepResponse(step_name=payload.step_name, completed=True)

    db.add(OnboardingStep(user_id=user.id, step_name=payload.step_name))
    db.commit()
    return OnboardingStepResponse(step_name=payload.step_name, completed=True)
