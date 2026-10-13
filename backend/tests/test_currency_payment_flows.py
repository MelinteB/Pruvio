import json
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.payment_profile import PaymentProfile
from app.models.user import User
from app.react_app import api


def test_reference_uses_participant_total_with_tip():
    s = SimpleNamespace(fx_settings_json=json.dumps({'rate':'4.50000000','target':'RON'}),
                        case_id=1, owner_user_id=2)
    split = {'participants':[{'participant_id':3,'user_id':2,'total':'12.50','phone_number':'123'},
                             {'participant_id':4,'user_id':7,'total':'15.00','phone_number':'456'}]}
    with patch.object(api.bills,'get_split_bill_session_summary',return_value=split), \
         patch('app.react_app.receipt_labels.receipt_label',return_value='Lunch'):
        result=api.summary(None,s,7)
    assert result['participants'][0]['reference_total']=='56.25'
    assert result['participants'][1]['reference_total']=='67.50'


def test_payment_profile_is_scoped_to_owner():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine, tables=[User.__table__,PaymentProfile.__table__])
    with Session(engine) as db:
        db.add_all([User(id=1,phone_number='1',username='owner',username_key='owner'),
                    User(id=2,phone_number='2',username='guest',username_key='guest')]);db.commit()
        body={'label':'Bank A','recipient_name':'Owner','iban':'RO49AAAA1B31007593840000',
              'bank_name':'Bank A','bic':'','revolut_link':'','payment_note':''}
        row=api.save_payment_profile(body,identity=(SimpleNamespace(id=1),None),db=db)
        assert row['bank_name']=='Bank A'
        assert len(api.payment_profiles(identity=(SimpleNamespace(id=1),None),db=db))==1
        assert api.payment_profiles(identity=(SimpleNamespace(id=2),None),db=db)==[]
