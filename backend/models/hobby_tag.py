from __future__ import annotations

import uuid

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base


class HobbyTag(Base):
    __tablename__ = "hobby_tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tag_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    search_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    hobby_city_pairs = relationship("HobbyCityPair", back_populates="hobby_tag", cascade="all, delete-orphan")
