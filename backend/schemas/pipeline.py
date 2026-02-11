from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ParseHobbiesRequest(BaseModel):
    user_id: UUID


class SearchEventsRequest(BaseModel):
    city: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class DraftEmailsRequest(BaseModel):
    user_id: UUID | None = None


class SendEmailsRequest(BaseModel):
    user_id: UUID | None = None


class PipelineResponse(BaseModel):
    detail: str
    processed: int = 0
