from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.rate_limit import limiter
from db.session import get_db
from models import OnboardingStep, User, UserGoal, UserHobby
from schemas.public import (
    OnboardingStatusResponse,
    OnboardingStepRequest,
    OnboardingStepResponse,
    SignupRequest,
    SignupResponse,
)
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
def signup(request: Request, response: Response, payload: SignupRequest = Body(...), db: Session = Depends(get_db)) -> SignupResponse:
    ensure_csrf(request)

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
        user.personality_type = payload.personality_type
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
            personality_type=payload.personality_type,
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

    return SignupResponse(user_id=user.id, onboarding_token=user.onboarding_token)


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
