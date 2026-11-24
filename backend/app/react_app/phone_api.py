"""Public, non-sensitive country calling-code metadata for Core enrollment."""
from fastapi import APIRouter

from app.services.phone_numbers import country_dialing_options

router = APIRouter(prefix="/api/v1/phone", tags=["Core phone enrollment"])


@router.get("/countries")
def countries():
    return {"countries": country_dialing_options()}
