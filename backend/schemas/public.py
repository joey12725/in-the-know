from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    address: str = Field(min_length=3, max_length=300)
    city: str = Field(min_length=2, max_length=120)
    lat: float | None = None
    lng: float | None = None
    concision_pref: Literal["brief", "detailed"] = "brief"
    event_radius_miles: int = Field(default=15, ge=1, le=250)
    hobbies_raw_text: str = Field(min_length=5, max_length=4000)
    goals_raw_text: str = Field(default="", max_length=4000)
    goal_types: list[str] = Field(default_factory=list)
    dating_preference: Literal["date_night_spots", "meeting_people", "both"] | None = None
    personality_type: str | None = Field(default=None, max_length=10)

    @field_validator("name", "address", "city", "hobbies_raw_text", "goals_raw_text", mode="before")
    @classmethod
    def normalize_fields(cls, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("Expected text input")
        return _normalize_text(value)

    @field_validator("goal_types")
    @classmethod
    def normalize_goal_types(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            normalized = _normalize_text(item).lower()
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned


class SignupResponse(BaseModel):
    user_id: UUID
    onboarding_token: str


class WaitlistRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    address: str = Field(min_length=3, max_length=300)
    city: str = Field(min_length=2, max_length=120)
    source: str | None = Field(default=None, max_length=120)

    @field_validator("name", "address", "city", "source", mode="before")
    @classmethod
    def normalize_waitlist_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("Expected text input")
        return _normalize_text(value)


class WaitlistResponse(BaseModel):
    joined: bool
    message: str


class OnboardingStatusResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    completed_steps: list[str]


class OnboardingStepRequest(BaseModel):
    step_name: str = Field(min_length=2, max_length=80)
    metadata: dict = Field(default_factory=dict)


class OnboardingStepResponse(BaseModel):
    step_name: str
    completed: bool
