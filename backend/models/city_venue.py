from __future__ import annotations

import uuid

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base_class import Base


class CityVenue(Base):
    __tablename__ = "city_venues"
    __table_args__ = (UniqueConstraint("city", "venue_name", name="uq_city_venues_city_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    venue_name: Mapped[str] = mapped_column(String(240), nullable=False)
    venue_type: Mapped[str] = mapped_column(String(50), nullable=False, default="music")
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_searched: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_events_searched: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cached_events: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
