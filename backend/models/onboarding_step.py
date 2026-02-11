from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base


class OnboardingStep(Base):
    __tablename__ = "onboarding_steps"
    __table_args__ = (UniqueConstraint("user_id", "step_name", name="uq_onboarding_steps_user_step"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    step_name: Mapped[str] = mapped_column(String(80), nullable=False)
    completed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="onboarding_steps")
