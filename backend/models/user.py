from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    concision_pref: Mapped[str] = mapped_column(String(20), nullable=False, default="brief")
    event_radius_miles: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    personality_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    onboarding_token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    hobbies = relationship("UserHobby", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("UserGoal", back_populates="user", cascade="all, delete-orphan")
    oauth_tokens = relationship("OAuthToken", back_populates="user", cascade="all, delete-orphan")
    newsletters = relationship("Newsletter", back_populates="user", cascade="all, delete-orphan")
    onboarding_steps = relationship("OnboardingStep", back_populates="user", cascade="all, delete-orphan")
