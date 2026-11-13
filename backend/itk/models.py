"""SQLAlchemy models. The Alembic migrations in `alembic/versions` are the source of truth
for the Postgres schema; `tests/test_migrations.py` checks the two stay in sync."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from itk.db import Base, JSONType, utcnow

Event = dict[str, Any]


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _created_at() -> Mapped[datetime]:
    # Python-side default keeps microsecond ordering on every backend; the server default
    # covers rows written outside the ORM.
    return mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_city", "city"),
        Index("ix_users_onboarding_token", "onboarding_token"),
    )

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    concision_pref: Mapped[str] = mapped_column(String(20), nullable=False, default="brief")
    event_radius_miles: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    is_subscribed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    personality_type: Mapped[str | None] = mapped_column(String(10))
    dating_preference: Mapped[str | None] = mapped_column(String(40))
    onboarding_token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    hobbies: Mapped[list["UserHobby"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    goals: Mapped[list["UserGoal"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    oauth_tokens: Mapped[list["OAuthToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    newsletters: Mapped[list["Newsletter"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    onboarding_steps: Mapped[list["OnboardingStep"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserHobby(Base):
    """The subscriber's free-text interests ("word vomit") plus the tags parsed from it."""

    __tablename__ = "user_hobbies"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_tags: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship(back_populates="hobbies")


class UserGoal(Base):
    __tablename__ = "user_goals"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    goal_types: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship(back_populates="goals")


class HobbyTag(Base):
    """A normalized interest shared across subscribers (e.g. "live jazz")."""

    __tablename__ = "hobby_tags"
    __table_args__ = (Index("ix_hobby_tags_tag_name", "tag_name"),)

    id: Mapped[uuid.UUID] = _pk()
    tag_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    search_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    hobby_city_pairs: Mapped[list["HobbyCityPair"]] = relationship(
        back_populates="hobby_tag", cascade="all, delete-orphan"
    )


class HobbyCityPair(Base):
    """One searchable (interest, city) combination. `frequency` counts how many subscribers
    share it, and `cached_results` holds the last event search so popular pairs are searched
    once per day instead of once per subscriber."""

    __tablename__ = "hobby_city_pairs"
    __table_args__ = (Index("ix_hobby_city_pairs_city", "city"),)

    id: Mapped[uuid.UUID] = _pk()
    hobby_tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("hobby_tags.id", ondelete="CASCADE"), nullable=False
    )
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_searched: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cached_results: Mapped[list[Event]] = mapped_column(JSONType, nullable=False, default=list)

    hobby_tag: Mapped[HobbyTag] = relationship(back_populates="hobby_city_pairs")


class CityVenue(Base):
    """A known venue in a pilot city whose calendar is searched directly each week."""

    __tablename__ = "city_venues"
    __table_args__ = (
        UniqueConstraint("city", "venue_name", name="uq_city_venues_city_name"),
        Index("ix_city_venues_city", "city"),
    )

    id: Mapped[uuid.UUID] = _pk()
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    venue_name: Mapped[str] = mapped_column(String(240), nullable=False)
    venue_type: Mapped[str] = mapped_column(String(50), nullable=False, default="music")
    address: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    last_searched: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_events_searched: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cached_events: Mapped[list[Event]] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = _created_at()


class OAuthToken(Base):
    """Google/Spotify credentials. Both token columns are Fernet-encrypted at rest."""

    __tablename__ = "oauth_tokens"
    __table_args__ = (Index("ix_oauth_tokens_provider", "provider"),)

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="oauth_tokens")


class Newsletter(Base):
    __tablename__ = "newsletters"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    events_included: Mapped[list[Event]] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship(back_populates="newsletters")


class NewsletterFeedback(Base):
    """A subscriber reply, rewritten by the reply agent into context-rich guidance that is
    fed back into the next issue's copywriting prompt."""

    __tablename__ = "newsletter_feedback"
    __table_args__ = (Index("ix_newsletter_feedback_user_created_at", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    newsletter_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("newsletters.id", ondelete="SET NULL"))
    raw_reply: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class OnboardingStep(Base):
    __tablename__ = "onboarding_steps"
    __table_args__ = (UniqueConstraint("user_id", "step_name", name="uq_onboarding_steps_user_step"),)

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    step_name: Mapped[str] = mapped_column(String(80), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="onboarding_steps")


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        Index("ix_waitlist_entries_email", "email"),
        Index("ix_waitlist_entries_city", "city"),
    )

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
