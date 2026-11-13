from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from itk import pipeline
from itk.models import User
from itk.seed import seed
from tests.conftest import CRON_HEADERS


def test_weekly_pipeline_runs_offline_end_to_end(db: Session, outbox: Path) -> None:
    seed(db)
    result = pipeline.run_weekly_pipeline(db)
    assert result["drafted_newsletters"] == 3
    assert result["sent_newsletters"] == 3
    assert "errors" not in result
    assert len(list(outbox.glob("*.html"))) == 3


def test_failed_step_does_not_stop_the_run(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seed(db)

    def boom(*_: object, **__: object) -> int:
        raise TimeoutError("search timed out")

    monkeypatch.setattr(pipeline, "search_events_for_pairs", boom)
    result = pipeline.run_weekly_pipeline(db)
    assert result["errors"] == ["searched_pairs: search timed out"]
    assert result["sent_newsletters"] == 3


def test_run_user_endpoint(client: TestClient, db: Session) -> None:
    seed(db)
    user = db.scalars(select(User).where(User.email == "priya.shah@example.com")).one()
    response = client.post(f"/api/pipeline/run-user/{user.id}", headers=CRON_HEADERS)
    assert response.status_code == 200
    assert response.json()["sent_newsletters"] == 1
    missing = client.post("/api/pipeline/run-user/00000000-0000-0000-0000-000000000000", headers=CRON_HEADERS)
    assert missing.status_code == 404
