from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from db.session import get_db
from models import User
from pipeline.runner import run_user_pipeline, run_weekly_pipeline
from schemas.pipeline import (
    DiscoverVenuesRequest,
    DraftEmailsRequest,
    ParseHobbiesRequest,
    PipelineResponse,
    SearchEventsRequest,
    SearchVenueEventsRequest,
    SendEmailsRequest,
)
from services.email import draft_newsletters, send_newsletters
from services.events import search_events_for_pairs
from services.hobbies import parse_and_store_user_hobbies
from services.venues import discover_major_music_venues, discover_pilot_city_venues, search_venue_events

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


@router.post("/run-user/{user_id}")
def run_pipeline_for_user(
    user_id: UUID,
    x_cron_secret: str | None = Header(default=None),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Run pipeline for a single user. Completes in <10s."""
    _check_internal_auth(x_cron_secret, secret)
    
    # Verify user exists
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return run_user_pipeline(db, user_id)


@router.post("/run-all")
async def run_pipeline_all_users(
    request: Request,
    x_cron_secret: str | None = Header(default=None),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Trigger per-user pipeline runs asynchronously. Fire-and-forget pattern."""
    _check_internal_auth(x_cron_secret, secret)
    
    # Get all users
    users = db.scalars(select(User)).all()
    user_ids = [user.id for user in users]
    
    # Build the base URL for webhooks
    base_url = str(request.base_url).rstrip("/")
    secret_param = x_cron_secret or secret
    
    # Fire off async requests (fire-and-forget)
    async def trigger_user_pipeline(user_id: UUID):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{base_url}/api/pipeline/run-user/{user_id}"
                headers = {"X-Cron-Secret": secret_param} if secret_param else {}
                # Fire and forget - we don't await the response
                await client.post(url, headers=headers)
        except Exception:
            # Silently fail - this is fire-and-forget
            pass
    
    # Trigger all user pipelines in the background
    tasks = [trigger_user_pipeline(user_id) for user_id in user_ids]
    # Don't await - let them run in background
    asyncio.create_task(asyncio.gather(*tasks, return_exceptions=True))
    
    return {
        "detail": "Pipeline triggered for all users",
        "users_triggered": len(user_ids),
        "user_ids": [str(uid) for uid in user_ids],
    }


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


@router.post("/discover-venues", response_model=PipelineResponse)
def discover_venues(
    payload: DiscoverVenuesRequest,
    x_cron_secret: str | None = Header(default=None),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    _check_internal_auth(x_cron_secret, secret)
    if payload.city:
        processed = discover_major_music_venues(db, city=payload.city, force_refresh=payload.force_refresh)
    else:
        processed = discover_pilot_city_venues(db, force_refresh=payload.force_refresh)
    return PipelineResponse(detail="Venues discovered", processed=processed)


@router.post("/search-venue-events", response_model=PipelineResponse)
def search_city_venue_events(
    payload: SearchVenueEventsRequest,
    x_cron_secret: str | None = Header(default=None),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    _check_internal_auth(x_cron_secret, secret)
    processed = search_venue_events(db, city=payload.city, force_refresh=payload.force_refresh)
    return PipelineResponse(detail="Venue events searched", processed=processed)


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
