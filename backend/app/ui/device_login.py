import json

from nicegui import ui

from app.services.trusted_device_service import create_device_claim
from app.ui.auth_state import login_user


async def finish_verified_device_login(db, user) -> str:
    claim = create_device_claim(db, user)
    success = await ui.run_javascript(
        "return await fetch('/auth/device/remember', {method: 'POST', credentials: 'same-origin', "
        "headers: {'Content-Type': 'application/json'}, body: JSON.stringify({claim: "
        + json.dumps(claim) + "})}).then(r => r.ok)", timeout=15,
    )
    if not success:
        raise ValueError("Could not remember this browser. Sign in again.")
    return login_user(user)

