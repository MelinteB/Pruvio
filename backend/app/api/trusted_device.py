import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.db.database import get_db
from app.services.trusted_device_service import (
    DEVICE_COOKIE, consume_device_claim, trusted_device_days,
)

router = APIRouter()


class DeviceClaim(BaseModel):
    claim: str = Field(min_length=30, max_length=128)


@router.post("/device/remember", include_in_schema=False)
def remember_device(payload: DeviceClaim, request: Request, response: Response, db=Depends(get_db)):
    try:
        token = consume_device_claim(db, payload.claim)
    except ValueError as error:
        raise HTTPException(400, detail=str(error))
    secure = os.getenv("PUBLIC_BASE_URL", "").startswith("https://") or request.url.scheme == "https"
    response.set_cookie(
        DEVICE_COOKIE, token, max_age=trusted_device_days() * 86400,
        httponly=True, secure=secure, samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"remembered": True}

