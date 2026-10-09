from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.push_notification import PushDevice, PushEvent
from app.services import push_service as service
import os

router = APIRouter(prefix='/notifications-api', tags=['Notifications'])


def authenticate(authorization: str = Header(default=''), db: Session = Depends(get_db)):
    token = authorization[7:] if authorization.startswith('Bearer ') else ''
    grant = service.grant_for(db, token)
    if not grant:
        raise HTTPException(401, 'Sign in again to manage notifications.')
    return grant


class SubscriptionRequest(BaseModel):
    subscription: dict
    label: str = Field(default='Browser', max_length=120)


class DeviceRequest(BaseModel):
    device_id: str = Field(max_length=36)


class ConfirmationRequest(BaseModel):
    code: str = Field(min_length=20, max_length=100)


class PreferenceRequest(BaseModel):
    push_enabled: bool
    email_enabled: bool
    receipts: bool
    bills: bool
    reminders: bool


@router.get('/state')
def state(response: Response, grant=Depends(authenticate), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    pref = service.preferences(db, grant.user_id)
    db.commit()
    devices = db.query(PushDevice).filter_by(user_id=grant.user_id).order_by(PushDevice.updated_at.desc()).limit(50).all()
    events = db.query(PushEvent).filter_by(user_id=grant.user_id).order_by(PushEvent.created_at.desc()).limit(50).all()
    return {'enabled': service.enabled(), 'public_key': os.getenv('PRUVS_VAPID_PUBLIC_KEY', ''),
            'preferences': {key: bool(getattr(pref, key)) for key in PreferenceRequest.model_fields},
            'devices': [{'id': d.id, 'label': d.label, 'active': d.active,
                         'current_login': d.grant_hash == grant.token_hash,
                         'confirmed_at': d.confirmed_at.isoformat() if d.confirmed_at else None} for d in devices],
            'events': [{'id': e.id, 'title': e.title, 'body': e.body, 'status': e.status,
                        'created_at': e.created_at.isoformat(), 'url': f'/notifications/open/{e.id}'} for e in events]}


@router.post('/subscribe')
def subscribe(payload: SubscriptionRequest, grant=Depends(authenticate), db: Session = Depends(get_db)):
    if not service.enabled():
        raise HTTPException(503, 'Device notifications have not been configured yet.')
    try:
        device = service.register_device(db, grant, payload.subscription, payload.label)
        return {'device_id': device.id}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post('/disable')
def disable(payload: DeviceRequest, grant=Depends(authenticate), db: Session = Depends(get_db)):
    device = db.get(PushDevice, payload.device_id)
    if not device or device.user_id != grant.user_id:
        raise HTTPException(404, 'Device not found.')
    device.active = False
    device.test_hash = None
    db.commit()
    return {'disabled': True}


@router.post('/test')
def test(payload: DeviceRequest, grant=Depends(authenticate), db: Session = Depends(get_db)):
    if not service.enabled():
        raise HTTPException(503, 'Device notifications have not been configured yet.')
    try:
        event = service.test_device(db, grant, payload.device_id)
        return {'queued': True, 'event_id': event.id}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post('/confirm')
def confirm(payload: ConfirmationRequest, grant=Depends(authenticate), db: Session = Depends(get_db)):
    try:
        device = service.confirm_test(db, grant, payload.code)
        return {'confirmed': True, 'device_id': device.id}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.put('/preferences')
def save_preferences(payload: PreferenceRequest, grant=Depends(authenticate), db: Session = Depends(get_db)):
    pref = service.preferences(db, grant.user_id)
    for key, value in payload.model_dump().items():
        setattr(pref, key, value)
    db.commit()
    return {'saved': True}
