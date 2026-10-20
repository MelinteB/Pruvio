"""Only unambiguous, receipt-specific extracted identities are persisted."""
from datetime import datetime
from sqlalchemy import Column,DateTime,ForeignKey,Integer,String,UniqueConstraint
from app.db.database import Base
class ReceiptIdentity(Base):
    __tablename__='pruvs_receipt_identities'
    __table_args__=(UniqueConstraint('user_id','identity_hash',name='uq_pruvs_receipt_identity'),)
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False,index=True)
    case_id=Column(Integer,ForeignKey('cases.id'),nullable=False,index=True)
    identity_hash=Column(String(64),nullable=False)
    created_at=Column(DateTime,default=datetime.utcnow,nullable=False)
