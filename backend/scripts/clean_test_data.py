import os
from dotenv import load_dotenv

from app.db.database import SessionLocal
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_session import SplitBillSession
from app.models.receipt_item import ReceiptItem
from app.models.external_ocr_request import ExternalOCRRequest
from app.models.external_ocr_usage import ExternalOCRUsage
from app.models.verification_code import VerificationCode
from app.models.document import Document
from app.models.case import Case
from app.models.message import Message
from app.models.reminder import Reminder


load_dotenv()


def clean_test_data():
    db = SessionLocal()

    try:
        print("Cleaning test data...")

        db.query(SplitBillItemAssignment).delete(synchronize_session=False)
        db.query(SplitBillParticipant).delete(synchronize_session=False)
        db.query(SplitBillSession).delete(synchronize_session=False)

        db.query(ReceiptItem).delete(synchronize_session=False)

        db.query(ExternalOCRRequest).delete(synchronize_session=False)
        db.query(ExternalOCRUsage).delete(synchronize_session=False)
        db.query(VerificationCode).delete(synchronize_session=False)

        db.query(Document).delete(synchronize_session=False)
        db.query(Message).delete(synchronize_session=False)
        db.query(Reminder).delete(synchronize_session=False)
        db.query(Case).delete(synchronize_session=False)

        db.commit()

        print("Done. Test data cleaned.")
        print("Users were NOT deleted.")

    except Exception as error:
        db.rollback()
        print(f"Cleanup failed: {error}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    clean_test_data()