"""Payment-profile default regression, isolated SQLite only."""
from types import SimpleNamespace, ModuleType
import sys

# The payment-profile tests do not perform OCR. Stub the optional Azure SDK
# only when it is absent in the isolated test environment.
try:
    from azure.ai.documentintelligence import DocumentIntelligenceClient  # noqa: F401
except ModuleNotFoundError:
    azure=ModuleType('azure');azure.__path__=[]
    core=ModuleType('azure.core');core.__path__=[]
    credentials=ModuleType('azure.core.credentials')
    credentials.AzureKeyCredential=type('AzureKeyCredential',(),{})
    ai=ModuleType('azure.ai');ai.__path__=[]
    di=ModuleType('azure.ai.documentintelligence')
    di.DocumentIntelligenceClient=type('DocumentIntelligenceClient',(),{})
    sys.modules.update({'azure':azure,'azure.core':core,
        'azure.core.credentials':credentials,'azure.ai':ai,
        'azure.ai.documentintelligence':di})
try:
    from openai import OpenAI  # noqa: F401
except ImportError:
    openai_stub=ModuleType('openai')
    openai_stub.OpenAI=type('OpenAI',(),{})
    sys.modules['openai']=openai_stub

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.payment_profile import PaymentProfile
from app.models.user import User
from app.react_app import api


def create_db():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine,tables=[User.__table__,PaymentProfile.__table__])
    db=Session(engine)
    db.add_all([
        User(id=71,phone_number='7100',username='a',username_key='a'),
        User(id=72,phone_number='7200',username='b',username_key='b'),
    ])
    db.commit()
    return db


def data(label):
    return {'label':label,'recipient_name':'Test owner','iban':'RO49AAAA1B31007593840000','bank_name':'Test bank',
            'bic':'','revolut_link':''}


def test_first_profile_becomes_default_and_is_user_scoped():
    with create_db() as db:
        first=api.save_payment_profile(data('First'),identity=(SimpleNamespace(id=71),None),db=db)
        second=api.save_payment_profile(data('Second'),identity=(SimpleNamespace(id=71),None),db=db)
        api.save_payment_profile(data('Other'),identity=(SimpleNamespace(id=72),None),db=db)
        assert api.default_payment_profile(db,71).id == first['id']
        assert api.default_payment_profile(db,72).user_id == 72
        assert [x['id'] for x in api.payment_profiles(identity=(SimpleNamespace(id=71),None),db=db)] == [first['id'],second['id']]


def test_deleting_default_promotes_next_profile():
    with create_db() as db:
        a=api.save_payment_profile(data('A'),identity=(SimpleNamespace(id=71),None),db=db)
        b=api.save_payment_profile(data('B'),identity=(SimpleNamespace(id=71),None),db=db)
        api.delete_payment_profile(a['id'],identity=(SimpleNamespace(id=71),None),db=db)
        assert api.default_payment_profile(db,71).id==b['id']


def test_edit_preserves_legacy_payment_note_when_omitted():
    with create_db() as db:
        old=data('Legacy')|{'payment_note':'old note'}
        saved=api.save_payment_profile(old,identity=(SimpleNamespace(id=71),None),db=db)
        update=data('Renamed')
        result=api.save_payment_profile(update,profile_id=saved['id'],identity=(SimpleNamespace(id=71),None),db=db)
        assert result['payment_note']=='old note'
        assert result['label']=='Renamed'


def test_closed_bill_snapshots_not_mutated_on_profile_change():
    with create_db() as db:
        a=api.save_payment_profile(data('Primary'),identity=(SimpleNamespace(id=71),None),db=db)
        snapshot=api.payment_profile_data(db.query(PaymentProfile).filter_by(id=a['id']).one())
        api.save_payment_profile(data('Updated'),profile_id=a['id'],identity=(SimpleNamespace(id=71),None),db=db)
        assert snapshot['label']=='Primary'
        assert api.default_payment_profile(db,71).label=='Updated'


def test_owner_cannot_select_other_users_payment_profile():
    with create_db() as db:
        other=api.save_payment_profile(data('Private'),identity=(SimpleNamespace(id=72),None),db=db)
        owner=(SimpleNamespace(id=71),None)
        session=SimpleNamespace(payment_details_json=None)
        with patch.object(api,'member',return_value=(session,None)):
            with pytest.raises(ValueError,match='saved payment profiles'):
                api.bill_action('test','settle',{'payment_profile_id':other['id']},identity=owner,db=db)


def test_bill_close_requires_profile_if_none_saved():
    with create_db() as db:
        owner=(SimpleNamespace(id=71),None)
        session=SimpleNamespace(payment_details_json=None)
        with patch.object(api,'member',return_value=(session,None)):
            with pytest.raises(HTTPException) as ex:
                api.bill_action('test','settle',{},identity=owner,db=db)
            assert ex.value.status_code==409


def test_default_profile_selected_when_bill_closed():
    with create_db() as db:
        a=api.save_payment_profile(data('First'),identity=(SimpleNamespace(id=71),None),db=db)
        api.save_payment_profile(data('Second'),identity=(SimpleNamespace(id=71),None),db=db)
        owner=(SimpleNamespace(id=71),None)
        session=SimpleNamespace(payment_details_json=None)
        with patch.object(api,'member',return_value=(session,None)), \
             patch.object(api.bills,'close_split_bill_session',return_value=None), \
             patch.object(api,'summary',return_value={'status':'closed'}):
            result=api.bill_action('test','settle',{},identity=owner,db=db)
        import json
        snapshot=json.loads(session.payment_details_json)
        assert snapshot['label']=='First' and snapshot['id']==a['id']
        assert result['status']=='closed'
