from sqlalchemy.orm import Session

from app.models.message import Message
from app.schemas.message import MessageCreate


def create_message(db: Session, message_data: MessageCreate):
    message = Message(
        case_id=message_data.case_id,
        direction=message_data.direction,
        content=message_data.content
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message


def get_messages_by_case(db: Session, case_id: int):
    return (
        db.query(Message)
        .filter(Message.case_id == case_id)
        .order_by(Message.created_at.asc())
        .all()
    )