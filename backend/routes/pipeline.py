from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from core.config import get_settings
from db.session import get_db
from pipeline.runner import run_weekly_pipeline
from schemas.pipeline import (
    DraftEmailsRequest,
    ParseHobbiesRequest,
    PipelineResponse,
    SearchEventsRequest,
    SendEmailsRequest,
)
from services.email import draft_newsletters, send_newsletters
from services.events import search_events_for_pairs
from services.hobbies import parse_and_store_user_hobbies

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


def _check_internal_auth(header_value: str | None, query_value: str | None = None) -> None:
    expected = get_settings().api_cron_secret
    provided = header_value or query_value
    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/run")
def run_pipeline(
    x_cron_secret: str | None = Header(default=None),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    _check_internal_auth(x_cron_secret, secret)
    return run_weekly_pipeline(db)


@router.post("/parse-hobbies", response_model=PipelineResponse)
def parse_hobbies(
    payload: ParseHobbiesRequest,
    x_cron_secret: str | None = Header(default=None),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    _check_internal_auth(x_cron_secret, secret)
    tags = parse_and_store_user_hobbies(db, payload.user_id)
    return PipelineResponse(detail="Hobbies parsed", processed=len(tags))


@router.post("/search-events", response_model=PipelineResponse)
def search_events(
    payload: SearchEventsRequest,
    x_cron_secret: str | None = Header(default=None),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    _check_internal_auth(x_cron_secret, secret)
    processed = search_events_for_pairs(db, city=payload.city, limit=payload.limit)
    return PipelineResponse(detail="Events searched", processed=processed)


@router.post("/draft-emails", response_model=PipelineResponse)
def draft_emails(
    payload: DraftEmailsRequest,
    x_cron_secret: str | None = Header(default=None),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    _check_internal_auth(x_cron_secret, secret)
    processed = draft_newsletters(db, payload.user_id)
    return PipelineResponse(detail="Newsletters drafted", processed=processed)


@router.post("/send-emails", response_model=PipelineResponse)
def send_emails(
    payload: SendEmailsRequest,
    x_cron_secret: str | None = Header(default=None),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    _check_internal_auth(x_cron_secret, secret)
    processed = send_newsletters(db, payload.user_id)
    return PipelineResponse(detail="Newsletters sent", processed=processed)
