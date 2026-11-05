"""Authenticated v7.1.40 receipt-group API; folders do not own/delete receipts."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from app.db.database import get_db
from app.models.case import Case
from app.models.receipt_group import ReceiptGroup, ReceiptGroupMembership
from app.react_app.auth import current

router = APIRouter(prefix='/api/v1/receipt-groups', tags=['Receipt groups'])

def owned_group(db, user_id, group_id):
    obj = db.query(ReceiptGroup).filter_by(id=group_id,owner_user_id=user_id).first()
    if not obj:
        raise HTTPException(404,'Receipt group not found.')
    return obj

def owned_receipt(db, user_id, case_id):
    obj = db.query(Case).filter_by(id=case_id,user_id=user_id).first()
    if not obj:
        raise HTTPException(404,'Receipt not found.')
    return obj

def get_groups(db, user_id):
    groups=(db.query(ReceiptGroup, func.count(ReceiptGroupMembership.case_id))
              .outerjoin(ReceiptGroupMembership,ReceiptGroup.id==ReceiptGroupMembership.group_id)
              .filter(ReceiptGroup.owner_user_id==user_id)
              .group_by(ReceiptGroup.id)
              .order_by(ReceiptGroup.name.asc(),ReceiptGroup.id.asc()).all())
    return [{'id':g.id,'name':g.name,'receipt_count':count} for g,count in groups]

@router.get('')
def list_groups(identity=Depends(current),db=Depends(get_db)):
    return {'groups':get_groups(db,identity[0].id)}

@router.post('')
def create_group(body:dict,identity=Depends(current),db=Depends(get_db)):
    uid=identity[0].id
    name=str(body.get('name') or '').strip()
    if not 1<=len(name)<=100:raise ValueError('Group name must contain 1–100 characters.')
    if db.query(ReceiptGroup.id).filter_by(owner_user_id=uid,name=name).first():
        raise HTTPException(409,'A group with that name already exists.')
    row=ReceiptGroup(owner_user_id=uid,name=name)
    db.add(row);db.commit();db.refresh(row)
    return {'id':row.id,'name':row.name,'receipt_count':0}

@router.put('/{group_id}')
def rename_group(group_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    g=owned_group(db,identity[0].id,group_id)
    name=str(body.get('name') or '').strip()
    if not 1<=len(name)<=100:raise ValueError('Group name must contain 1–100 characters.')
    if db.query(ReceiptGroup.id).filter(ReceiptGroup.owner_user_id==identity[0].id,
           ReceiptGroup.name==name,ReceiptGroup.id!=group_id).first():
        raise HTTPException(409,'A group with that name already exists.')
    g.name=name;db.commit()
    return {'id':g.id,'name':g.name}

@router.delete('/{group_id}')
def delete_group(group_id:int,identity=Depends(current),db=Depends(get_db)):
    g=owned_group(db,identity[0].id,group_id)
    db.query(ReceiptGroupMembership).filter_by(group_id=group_id).delete(synchronize_session=False)
    db.delete(g);db.commit()
    return {'ok':True,'receipts_deleted':0}

@router.put('/{group_id}/receipts/{case_id}')
def assign_group(group_id:int,case_id:int,identity=Depends(current),db=Depends(get_db)):
    uid=identity[0].id
    owned_group(db,uid,group_id)
    owned_receipt(db,uid,case_id)
    # Serialize against group moves of the same receipt; upsert is dialect independent.
    db.query(Case).filter_by(id=case_id).with_for_update().first()
    row=db.get(ReceiptGroupMembership,case_id)
    if row:row.group_id=group_id
    else:db.add(ReceiptGroupMembership(case_id=case_id,group_id=group_id))
    db.commit()
    return {'case_id':case_id,'group_id':group_id}

@router.delete('/receipts/{case_id}')
def ungroup_receipt(case_id:int,identity=Depends(current),db=Depends(get_db)):
    owned_receipt(db,identity[0].id,case_id)
    db.query(Case).filter_by(id=case_id).with_for_update().first()
    db.query(ReceiptGroupMembership).filter_by(case_id=case_id).delete(synchronize_session=False)
    db.commit()
    return {'case_id':case_id,'group_id':None}
