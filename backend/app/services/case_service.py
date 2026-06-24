from sqlalchemy.orm import Session

from app.models.case import Case
from app.schemas.case import CaseCreate


def get_cases(db: Session):
    return db.query(Case).order_by(Case.created_at.desc()).all()


def get_case_by_id(db: Session, case_id: int):
    return db.query(Case).filter(Case.id == case_id).first()


def create_case(db: Session, case_data: CaseCreate):
    case = Case(
        user_id=case_data.user_id,
        module=case_data.module,
        status=case_data.status
    )

    db.add(case)
    db.commit()
    db.refresh(case)

    return case