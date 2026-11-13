"""The weekly pipeline, as a sequence of independent steps.

Each step is isolated: if event search times out, drafting and sending still run on
whatever is cached. Step failures are collected and returned rather than raised.
"""

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from itk.models import User
from itk.services.events import search_events_for_pairs
from itk.services.hobbies import parse_and_store_user_hobbies
from itk.services.newsletter import draft_newsletters, send_newsletters
from itk.services.venues import discover_pilot_city_venues, search_venue_events

log = logging.getLogger(__name__)


class PipelineRun:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.result: dict[str, Any] = {}
        self.errors: list[str] = []

    def step(self, name: str, fn: Callable[[], int]) -> None:
        try:
            self.result[name] = fn()
        except Exception as exc:
            log.exception("Pipeline step %s failed", name)
            self.db.rollback()
            self.result[name] = 0
            self.errors.append(f"{name}: {exc}")

    def report(self) -> dict[str, Any]:
        return {**self.result, "errors": self.errors} if self.errors else dict(self.result)


def _parse_all_hobbies(db: Session) -> int:
    users = db.scalars(select(User).where(User.is_subscribed.is_(True))).all()
    return sum(1 for user in users if parse_and_store_user_hobbies(db, user.id))


def run_weekly_pipeline(db: Session) -> dict[str, Any]:
    """Everything, for everyone: parse → research → draft → send."""
    run = PipelineRun(db)
    run.step("parsed_hobbies", lambda: _parse_all_hobbies(db))
    run.step("searched_pairs", lambda: search_events_for_pairs(db))
    run.step("discovered_venues", lambda: discover_pilot_city_venues(db))
    run.step("searched_venue_events", lambda: search_venue_events(db))
    run.step("drafted_newsletters", lambda: draft_newsletters(db))
    run.step("sent_newsletters", lambda: send_newsletters(db))
    return run.report()


def run_user_pipeline(db: Session, user_id: UUID) -> dict[str, Any]:
    """One subscriber, using cached research. Fits inside a short serverless timeout."""
    run = PipelineRun(db)
    run.result["user_id"] = str(user_id)
    run.step("parsed_hobbies", lambda: int(bool(parse_and_store_user_hobbies(db, user_id))))
    run.step("drafted_newsletters", lambda: draft_newsletters(db, user_id))
    run.step("sent_newsletters", lambda: send_newsletters(db, user_id))
    return run.report()
