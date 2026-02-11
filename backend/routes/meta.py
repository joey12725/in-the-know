from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/meta")
def meta_webhook_stub() -> dict:
    return {"detail": "Meta webhook stubbed for future integration"}
