"""Atomic, opt-in v7.1.40 equal and shared-line allocations.

Every mutation runs inside the authenticated API's locked session transaction.
The server remains the authority: never trust a client-supplied amount or owner.
"""
from __future__ import annotations
import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from app.models.receipt_item import ReceiptItem
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_v7140 import SplitAllocationState, SplitSharedItem
from app.react_app.bill_service import get_joined_participants, get_session_items, get_session_assignments, _item_quantity
from app.services.split_math_v7140 import equal_minor


def _minor(value):
    dec=Decimal(str(value))
    if not dec.is_finite():raise ValueError('Invalid receipt amount.')
    rounded=dec.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    if dec!=rounded:raise ValueError('Receipt item has more than two decimal places. Review its amount first.')
    return int(rounded*100)


def allocate_evenly(total_minor:int, ids:list[int])->dict[int,int]:
    """Core v7.1.40 uses the independently tested exact-cent allocation module."""
    if not ids or len(set(ids))!=len(ids) or any(type(pid) is not int or pid<1 for pid in ids):
        raise ValueError('Invalid allocation participant identifiers.')
    padded=[f'{pid:020d}' for pid in ids]
    return {int(pid):cents for pid,cents in equal_minor(total_minor,padded).items()}

def state_for(db,session_id:int,create:bool=False):
    state=db.get(SplitAllocationState,session_id)
    if state is None and create:
        state=SplitAllocationState(session_id=session_id,mode='items',revision=0)
        db.add(state)
        db.flush()
    return state


def check_revision(state,expected_revision):
    if expected_revision is None or type(expected_revision) is not int:
        raise HTTPException(409,'Please refresh the bill before changing the allocation.')
    revision=state.revision if state else 0
    if expected_revision!=revision:
        raise HTTPException(409,'The bill changed. Refresh before applying your selection.')


def bump(state):
    state.revision += 1
    state.modified_at = datetime.utcnow()


def validate_open_owner(session,owner_id):
    if session.owner_user_id!=owner_id:raise HTTPException(403,'Only the bill owner can change allocation mode.')
    if session.status!='open':raise ValueError('Only an open bill can change allocations.')


def set_equal_mode(db,session:SplitBillSession,owner_id:int,expected_revision:int):
    validate_open_owner(session,owner_id)
    state=state_for(db,session.id,True)
    check_revision(state,expected_revision)
    if state.mode=='equal':return
    if db.query(SplitSharedItem).filter_by(session_id=session.id).first():
        raise ValueError('Remove shared-item allocations before splitting the entire bill equally.')
    participants=get_joined_participants(db,session)
    if len(participants)<2 or len(participants)!=session.expected_participants_count:
        raise ValueError('All invited participants must join before using Split Equally (at least two people).')
    if any(p.payment_status not in ('unpaid',None) for p in participants):
        raise ValueError('Resolve payment reports before changing the split.')
    items=get_session_items(db,session)
    if not items:raise ValueError('Bill has no items.')
    existing=get_session_assignments(db,session)
    snapshot=[{'participant_id':a.participant_id,'receipt_item_id':a.receipt_item_id,
               'quantity':a.quantity,'amount':a.amount} for a in existing]
    ids=[p.id for p in participants]
    pending=[]
    for item in items:
        total=_minor(item.total_price)
        if total<0:raise ValueError('Negative discount rows require item-by-item allocation.')
        if total>0 and total<len(ids):
            raise ValueError('An item is too small to split across all people. Use item-by-item splitting.')
        shares=allocate_evenly(total,ids)
        for pid, cents in shares.items():
            pending.append(SplitBillItemAssignment(
                session_id=session.id,participant_id=pid,receipt_item_id=item.id,
                quantity=_item_quantity(item)/len(ids),amount=cents/100))
    db.query(SplitBillItemAssignment).filter_by(session_id=session.id).delete(synchronize_session='fetch')
    db.add_all(pending)
    state.mode='equal'
    state.snapshot_json=json.dumps(snapshot,separators=(',',':'))
    bump(state)
    db.commit()


def restore_item_mode(db,session:SplitBillSession,owner_id:int,expected_revision:int):
    validate_open_owner(session,owner_id)
    state=state_for(db,session.id,True)
    check_revision(state,expected_revision)
    if state.mode=='items':return
    participants={p.id for p in get_joined_participants(db,session)}
    items={i.id for i in get_session_items(db,session)}
    snapshot=json.loads(state.snapshot_json or '[]')
    if any(a['participant_id'] not in participants or a['receipt_item_id'] not in items for a in snapshot):
        raise ValueError('Participant or item list changed. Contact support before restoring original allocations.')
    rows=[SplitBillItemAssignment(session_id=session.id,participant_id=a['participant_id'],
            receipt_item_id=a['receipt_item_id'],quantity=a['quantity'],amount=a['amount']) for a in snapshot]
    db.query(SplitBillItemAssignment).filter_by(session_id=session.id).delete(synchronize_session='fetch')
    db.add_all(rows)
    state.mode='items'
    state.snapshot_json=None
    bump(state)
    db.commit()


def share_item(db,session:SplitBillSession,owner_id:int,item_id:int,
               participant_ids:list[int],expected_revision:int):
    validate_open_owner(session,owner_id)
    state=state_for(db,session.id,True)
    check_revision(state,expected_revision)
    if state.mode!='items':raise ValueError('Switch back to item selection first.')
    participants={p.id:p for p in get_joined_participants(db,session)}
    if len(participant_ids)<2 or len(set(participant_ids))!=len(participant_ids) or any(pid not in participants for pid in participant_ids):
        raise ValueError('Select at least two distinct joined participants.')
    item=next((i for i in get_session_items(db,session) if i.id==item_id),None)
    if not item:raise HTTPException(404,'Item not found in this bill.')
    if db.query(SplitBillItemAssignment.id).filter_by(session_id=session.id,receipt_item_id=item.id).first():
        raise ValueError('This item is already allocated. Remove its existing selections first.')
    total=_minor(item.total_price)
    if total<len(participant_ids):
        raise ValueError('Item price is too small to give each participant at least 0.01.')
    shares=allocate_evenly(total,participant_ids)
    db.add_all([SplitBillItemAssignment(session_id=session.id,participant_id=pid,
      receipt_item_id=item.id,quantity=_item_quantity(item)/len(participant_ids),amount=cents/100)
      for pid,cents in shares.items()])
    db.add(SplitSharedItem(session_id=session.id,receipt_item_id=item.id))
    bump(state)
    db.commit()


def unshare_item(db,session:SplitBillSession,owner_id:int,item_id:int,expected_revision:int):
    validate_open_owner(session,owner_id)
    state=state_for(db,session.id,True)
    check_revision(state,expected_revision)
    if state.mode!='items':raise ValueError('Switch back to item selection first.')
    marker=db.get(SplitSharedItem,(session.id,item_id))
    if not marker:raise HTTPException(404,'Shared item not found.')
    db.query(SplitBillItemAssignment).filter_by(session_id=session.id,receipt_item_id=item_id).delete(synchronize_session='fetch')
    db.delete(marker)
    bump(state)
    db.commit()



def assign_all_to_participant(db,session:SplitBillSession,owner_id:int,
                              participant_id:int,expected_revision:int):
    """Owner-only atomic transfer of every receipt item to one joined participant.

    This replaces existing unpaid item selections; it never changes payment records.
    The explicit revision check prevents overwriting concurrent split edits.
    """
    validate_open_owner(session,owner_id)
    state=state_for(db,session.id,True)
    check_revision(state,expected_revision)
    if state.mode!='items':
        raise ValueError('Return to individual items before assigning a whole bill.')
    participants=get_joined_participants(db,session)
    if type(participant_id) is not int or participant_id not in {p.id for p in participants}:
        raise ValueError('Choose a joined participant.')
    if any(p.payment_status not in ('unpaid',None) for p in participants):
        raise ValueError('Resolve existing payment reports before reassigning the bill.')
    if db.query(SplitSharedItem).filter_by(session_id=session.id).first():
        raise ValueError('Undo shared items before assigning every item to one person.')
    items=get_session_items(db,session)
    if not items:raise ValueError('There are no receipt items to assign.')
    rows=[]
    for item in items:
        if _minor(item.total_price)<0:raise ValueError('Review negative discount rows before assigning all items.')
        rows.append(SplitBillItemAssignment(session_id=session.id,
            participant_id=participant_id,receipt_item_id=item.id,
            quantity=round(_item_quantity(item),3),amount=_minor(item.total_price)/100))
    db.query(SplitBillItemAssignment).filter_by(session_id=session.id).delete(synchronize_session='fetch')
    db.add_all(rows)
    bump(state)
    db.commit()

def annotate_summary(db,session,summary):
    state=state_for(db,session.id)
    summary['allocation_mode']=state.mode if state else 'items'
    summary['allocation_revision']=state.revision if state else 0
    shared={row.receipt_item_id for row in db.query(SplitSharedItem).filter_by(session_id=session.id).all()}
    for item in summary['items']:
        item['shared_item']=item['item_id'] in shared
    return summary
