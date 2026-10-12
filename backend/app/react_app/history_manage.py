from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from app.db.database import get_db
from app.models.case import Case
from app.models.history_visibility import HistoryVisibility
from app.models.split_bill_participant import SplitBillParticipant
from app.react_app.auth import current

router = APIRouter(prefix='/api/v1/history', tags=['History'])


def belongs(db, uid, kind, source_id):
    if kind == 'receipt':
        return db.query(Case.id).filter_by(id=source_id, user_id=uid).first() is not None
    if kind == 'bill':
        return db.query(SplitBillParticipant.id).filter_by(session_id=source_id, user_id=uid, status='joined').first() is not None
    return False


@router.patch('/{kind}/{source_id}')
def organize(kind: str, source_id: int, body: dict, identity=Depends(current), db=Depends(get_db)):
    uid = identity[0].id
    if not belongs(db, uid, kind, source_id):
        raise HTTPException(404, 'History item not found.')
    state = body.get('state')
    note = body.get('note', '')
    if state not in ('active', 'archived', 'removed') or not isinstance(note, str) or len(note) > 300:
        raise ValueError('Choose Active, Archived or Removed, and keep your note under 300 characters.')
    row = db.query(HistoryVisibility).filter_by(user_id=uid, kind=kind, source_id=source_id).first()
    if row is None:
        row = HistoryVisibility(user_id=uid, kind=kind, source_id=source_id)
        db.add(row)
    row.state, row.note, row.updated_at = state, note.strip(), datetime.utcnow()
    db.commit()
    return {'kind': kind, 'source_id': source_id, 'state': state, 'note': row.note}
