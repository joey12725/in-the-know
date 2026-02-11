from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base


class HobbyCityPair(Base):
    __tablename__ = "hobby_city_pairs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hobby_tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hobby_tags.id", ondelete="CASCADE"), nullable=False
    )
    city: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_searched: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cached_results: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    hobby_tag = relationship("HobbyTag", back_populates="hobby_city_pairs")
