"""Internal endpoints that drive the weekly pipeline. All require the cron secret."""

import logging
from typing import Any
from uuid import UUID

import anyio
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.config import get_settings
from itk.db import get_db
from itk.models import User
from itk.pipeline import run_user_pipeline, run_weekly_pipeline
from itk.schemas import (
    CityRefreshRequest,
    ParseHobbiesRequest,
    PipelineResponse,
    SearchEventsRequest,
    UserScopedRequest,
)
from itk.security import require_cron_secret
from itk.services.events import search_events_for_pairs
from itk.services.hobbies import parse_and_store_user_hobbies
from itk.services.newsletter import draft_newsletters, send_newsletters
from itk.services.venues import discover_major_music_venues, discover_pilot_city_venues, search_venue_events

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pipeline", tags=["pipeline"], dependencies=[Depends(require_cron_secret)])

# Fan-out only waits long enough for each per-user request to be delivered; the per-user
# invocations then run (and time out) independently of this one.
FANOUT_TIMEOUT = httpx.Timeout(connect=5.0, write=5.0, pool=5.0, read=1.0)
FANOUT_CONCURRENCY = 10


@router.post("/run")
def run_pipeline(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Run every step for every subscriber in this request. Fine locally or on a long-running host."""
    return run_weekly_pipeline(db)


@router.post("/run-user/{user_id}")
def run_pipeline_for_user(user_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    return run_user_pipeline(db, user_id)


async def _dispatch(client: httpx.AsyncClient, url: str, limiter: anyio.CapacityLimiter) -> bool:
    async with limiter:
        try:
            await client.post(url, headers={"X-Cron-Secret": get_settings().api_cron_secret})
        except httpx.ReadTimeout:
            return True  # delivered; the per-user run continues on its own
        except httpx.HTTPError:
            log.warning("Could not dispatch %s", url)
            return False
        return True


@router.api_route("/run-all", methods=["GET", "POST"])
async def run_pipeline_all_users(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Fan out one `/run-user/{id}` request per subscriber.

    Serverless hosts cap a single invocation at a few seconds, so the weekly cron calls this
    endpoint (GET, as Vercel Cron does) and each subscriber gets their own invocation.
    """
    user_ids = db.scalars(select(User.id).where(User.is_subscribed.is_(True))).all()
    base_url = str(request.base_url).rstrip("/")
    limiter = anyio.CapacityLimiter(FANOUT_CONCURRENCY)
    results: list[bool] = []

    async with httpx.AsyncClient(timeout=FANOUT_TIMEOUT) as client:

        async def dispatch(user_id: UUID) -> None:
            results.append(await _dispatch(client, f"{base_url}/api/pipeline/run-user/{user_id}", limiter))

        async with anyio.create_task_group() as tg:
            for user_id in user_ids:
                tg.start_soon(dispatch, user_id)

    return {"detail": "Pipeline dispatched", "users": len(user_ids), "dispatched": sum(results)}


@router.post("/parse-hobbies", response_model=PipelineResponse)
def parse_hobbies(payload: ParseHobbiesRequest, db: Session = Depends(get_db)) -> PipelineResponse:
    tags = parse_and_store_user_hobbies(db, payload.user_id)
    return PipelineResponse(detail="Hobbies parsed", processed=len(tags))


@router.post("/search-events", response_model=PipelineResponse)
def search_events(payload: SearchEventsRequest, db: Session = Depends(get_db)) -> PipelineResponse:
    processed = search_events_for_pairs(db, city=payload.city, limit=payload.limit)
    return PipelineResponse(detail="Events searched", processed=processed)


@router.post("/discover-venues", response_model=PipelineResponse)
def discover_venues(payload: CityRefreshRequest, db: Session = Depends(get_db)) -> PipelineResponse:
    if payload.city:
        processed = discover_major_music_venues(db, city=payload.city, force_refresh=payload.force_refresh)
    else:
        processed = discover_pilot_city_venues(db, force_refresh=payload.force_refresh)
    return PipelineResponse(detail="Venues discovered", processed=processed)


@router.post("/search-venue-events", response_model=PipelineResponse)
def search_city_venue_events(payload: CityRefreshRequest, db: Session = Depends(get_db)) -> PipelineResponse:
    processed = search_venue_events(db, city=payload.city, force_refresh=payload.force_refresh)
    return PipelineResponse(detail="Venue events searched", processed=processed)


@router.post("/draft-emails", response_model=PipelineResponse)
def draft_emails(payload: UserScopedRequest, db: Session = Depends(get_db)) -> PipelineResponse:
    return PipelineResponse(detail="Newsletters drafted", processed=draft_newsletters(db, payload.user_id))


@router.post("/send-emails", response_model=PipelineResponse)
def send_emails(payload: UserScopedRequest, db: Session = Depends(get_db)) -> PipelineResponse:
    return PipelineResponse(detail="Newsletters sent", processed=send_newsletters(db, payload.user_id))
