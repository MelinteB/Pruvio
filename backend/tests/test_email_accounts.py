"""Real DB/API coverage for email identity and shared-owner access; providers mocked."""
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from test_device_otp import db, delivery, user  # Shared in-memory fixtures.
from app.db import database
from app.db.database import get_db
from app.models.user import User
from app.models.verification_code import VerificationCode
from app.models.trusted_device import TrustedDevice
from app.services import phone_otp_service as phone
from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.case import Case
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.services import onboarding_otp_service as otp
from app.services import account_service as accounts
from app.services import trusted_device_service as devices
from app.services.auth_service import authenticate_with_password
from app.services.username_service import check_username_available, update_username
from app.services.split_bill_session_service import create_split_bill_session, join_split_bill_session_as_user, join_split_bill_session
from app.api.users import router as users_router
from app.api.onboarding_otp import router as onboarding_router
from app.api.account import router as account_router
from app.usernames import username_key


def add_receipt(db, case):
    document = Document(case_id=case.id, stored_filename='test.pdf', path='test.pdf')
    db.add(document); db.commit()
    db.add(ReceiptItem(case_id=case.id, document_id=document.id, name='Meal', quantity=1, total_price=30, currency='RON'))
    db.commit()


def registration(db, **changes):
    fields = dict(phone_number='+40733333333', display_name='New Person', username='New Person',
                  email='new@example.com', accepted_terms=True, accepted_privacy=True, password='new-password')
    fields.update(changes)
    return otp.start_registration(db, **fields)


def verify_login(db, account, result):
    return otp.verify_login_otp(db, account.email, result['debug_otp'], challenge_id=result['challenge_id'])


def test_signup_email_alone_activates(db, delivery):
    result = registration(db)
    account = result['user']
    assert account.status == 'pending_join' and not account.is_phone_verified
    assert result['phone_delivery'] is None and result['debug_phone_otp'] is None
    assert db.query(VerificationCode).filter_by(user_id=account.id).count() == 1
    assert db.query(VerificationCode).one().destination_type == 'email'
    otp.verify_registration_email(db, account.email, result['debug_email_otp'], challenge_id=result['challenge_id'])
    assert account.status == 'active' and account.is_email_verified and not account.is_phone_verified
    delivery[0].assert_not_called(); delivery[1].assert_not_called(); delivery[2].assert_called_once()


@pytest.mark.parametrize('value', ['test user', '  TEST   USER  ', 'Ｔｅｓｔ Ｕｓｅｒ'])
def test_username_uniqueness_normalized(db, value):
    with pytest.raises(ValueError, match='already taken'):
        check_username_available(db, value)


def test_username_duplicate_rejected_before_delivery(db, delivery):
    with pytest.raises(ValueError, match='already taken'):
        registration(db, username=' TEST  USER ')
    assert db.query(User).count() == 1
    delivery[2].assert_not_called()


def test_username_constraint_handles_concurrent_inserts(db):
    duplicate = User(username='TEST USER', username_key=username_key('TEST USER'), name='Another', phone_number='+40744444444')
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.query(User).count() == 1


def test_full_names_can_repeat_with_distinct_usernames(db, delivery):
    result = registration(db, display_name='Test User', username='Test User 2')
    assert result['user'].name == user(db).name
    assert result['user'].username != user(db).username


@pytest.mark.parametrize('identifier', ['  TEST  USER ', 'TEST@EXAMPLE.COM'])
def test_password_login_by_username_or_email(db, identifier):
    assert authenticate_with_password(db, identifier, 'testing-password').id == user(db).id


def test_phone_no_longer_authenticates(db, delivery):
    with pytest.raises(ValueError):
        authenticate_with_password(db, user(db).phone_number, 'testing-password')
    with pytest.raises(ValueError):
        otp.send_login_otp(db, user(db).phone_number)
    delivery[0].assert_not_called(); delivery[1].assert_not_called(); delivery[2].assert_not_called()


def test_username_change_changes_login_but_display_name_does_not(db):
    account = user(db)
    accounts.update_profile_name(db, account, 'Display only')
    assert otp.find_user_by_identifier(db, 'Test User').id == account.id
    assert otp.find_user_by_identifier(db, 'Display only') is None
    update_username(db, account, 'New Login')
    assert otp.find_user_by_identifier(db, 'Test User') is None
    assert authenticate_with_password(db, 'new login', 'testing-password').id == account.id


def test_default_username_for_legacy_internal_inserts(db):
    row = User(phone_number='+40722222222', name='Legacy')
    db.add(row); db.commit()
    assert row.username and row.username_key == username_key(row.username)


def test_unverified_legacy_email_requires_otp_before_trust(db, delivery):
    account = user(db)
    account.is_email_verified = False; db.commit()
    with pytest.raises(ValueError):
        devices.create_device_claim(db, account)
    result = otp.send_login_otp(db, account.username)
    verify_login(db, account, result)
    assert account.is_email_verified
    token = devices.consume_device_claim(db, devices.create_device_claim(db, account))
    assert devices.is_trusted_device(db, account, token)


def test_phone_codes_disabled_every_auth_path(db, delivery):
    account = user(db)
    for action in [lambda: otp.create_verification_code(db, account, 'phone', account.phone_number, 'login'),
                   lambda: otp._deliver('phone', account.phone_number, '123456'),
                   lambda: phone.send_phone_otp(account.phone_number, '123456', 10),
                   lambda: otp.verify_registration_phone(db, account.phone_number, '123456'),
                   lambda: otp.resend_registration_code(db, account, 'phone'),
                   lambda: otp.verify_code(db, destination_type='phone', destination=account.phone_number, code='123456', purpose='login')]:
        with pytest.raises(ValueError):
            action()
    assert db.query(VerificationCode).count() == 0
    phone.process_whatsapp_status(db, {'id': 'historical-id', 'status': 'failed'})
    for mock in delivery:
        mock.assert_not_called()


def test_registration_code_cannot_login_and_wrong_challenge_not_consumed(db, delivery):
    result = registration(db)
    account = result['user']
    account.status = 'active'; db.commit()
    with pytest.raises(ValueError):
        otp.verify_login_otp(db, account.email, result['debug_email_otp'], challenge_id=result['challenge_id'])
    row = db.query(VerificationCode).one()
    assert row.status == 'pending' and row.attempts == 0


def test_registration_resend_requires_latest_popup_challenge(db, delivery):
    first = registration(db)
    second = otp.resend_registration_code(db, first['user'])
    with pytest.raises(ValueError):
        otp.verify_registration_email(db, first['user'].email, first['debug_email_otp'], challenge_id=first['challenge_id'])
    otp.verify_registration_email(db, first['user'].email, second['debug_otp'], challenge_id=second['challenge_id'])


def test_phone_change_uses_current_verified_email_and_exact_value(db, delivery):
    account = user(db)
    token = devices.consume_device_claim(db, devices.create_device_claim(db, account))
    original = account.phone_number
    result = accounts.request_contact_change(db, account, 'phone', '0722222222')
    assert result['destination'] == account.email and result['destination_type'] == 'email'
    assert result['requested_value'] == '+40722222222'
    delivery[2].assert_called_once_with(account.email, result['debug_otp'], otp.get_otp_ttl_minutes())
    with pytest.raises(ValueError):
        accounts.confirm_contact_change(db, account, 'phone', '+40799999999', result['debug_otp'], challenge_id=result['challenge_id'])
    assert account.phone_number == original
    assert db.query(VerificationCode).one().status == 'pending'
    accounts.confirm_contact_change(db, account, 'phone', result['requested_value'], result['debug_otp'], challenge_id=result['challenge_id'])
    assert account.phone_number == '+40722222222' and not account.is_phone_verified
    assert not devices.is_trusted_device(db, account, token)
    delivery[0].assert_not_called(); delivery[1].assert_not_called()


def test_phone_change_requires_verified_email(db, delivery):
    account = user(db); account.is_email_verified = False; db.commit()
    with pytest.raises(ValueError, match='Verify your email'):
        accounts.request_contact_change(db, account, 'phone', '+40722222222')
    delivery[2].assert_not_called()


def test_wrong_login_code_cannot_confirm_phone_change(db, delivery):
    account = user(db)
    result = otp.send_login_otp(db, account.email)
    with pytest.raises(ValueError):
        accounts.confirm_contact_change(db, account, 'phone', '+40722222222', result['debug_otp'], challenge_id=result['challenge_id'])
    assert account.phone_number == '+40711111111'


def test_email_change_uses_new_email_and_binds_value(db, delivery):
    account = user(db)
    result = accounts.request_contact_change(db, account, 'email', ' NEW@EXAMPLE.COM ')
    assert result['destination'] == 'new@example.com'
    accounts.confirm_contact_change(db, account, 'email', result['requested_value'], result['debug_otp'], challenge_id=result['challenge_id'])
    assert account.email == 'new@example.com' and account.is_email_verified


def test_deletion_rejects_phone_and_unverified_email(db, delivery):
    account = user(db)
    with pytest.raises(ValueError):
        accounts.request_account_deletion_otp(db, account, 'phone')
    with pytest.raises(ValueError):
        accounts.confirm_and_delete_account(db, account, 'phone', '123456')
    account.is_email_verified = False; db.commit()
    with pytest.raises(ValueError):
        accounts.request_account_deletion_otp(db, account)
    assert db.query(User).count() == 1
    delivery[2].assert_not_called()


def test_deletion_requires_correct_email_challenge_and_cleans_data(db, delivery):
    account = user(db); account_id = account.id
    token = devices.consume_device_claim(db, devices.create_device_claim(db, account))
    case = Case(user_id=account_id); db.add(case); db.commit()
    add_receipt(db, case)
    session = create_split_bill_session(db, case.id, account_id, 2)
    login = otp.send_login_otp(db, account.email)
    with pytest.raises(ValueError):
        accounts.confirm_and_delete_account(db, account, 'email', login['debug_otp'], challenge_id=login['challenge_id'])
    result = accounts.request_account_deletion_otp(db, account)
    with pytest.raises(ValueError):
        accounts.confirm_and_delete_account(db, account, 'email', '000000', challenge_id=result['challenge_id'])
    assert db.get(User, account_id)
    accounts.confirm_and_delete_account(db, account, 'email', result['debug_otp'], challenge_id=result['challenge_id'])
    for model in [User, Case, TrustedDevice, VerificationCode, SplitBillSession, SplitBillParticipant]:
        assert db.query(model).count() == 0


def test_codes_cannot_be_used_for_another_account(db, delivery):
    account = user(db)
    other = User(username='Other User', username_key='other user', phone_number='+40722222222', email='other@example.com', status='active', is_email_verified=True)
    db.add(other); db.commit()
    result = accounts.request_account_deletion_otp(db, account)
    with pytest.raises(ValueError):
        accounts.confirm_and_delete_account(db, other, 'email', result['debug_otp'], challenge_id=result['challenge_id'])
    assert db.query(User).count() == 2 and db.query(VerificationCode).one().status == 'pending'


def api_client(db):
    api = FastAPI()
    api.include_router(users_router, prefix='/users')
    api.include_router(onboarding_router, prefix='/onboarding')
    api.include_router(account_router, prefix='/auth')
    api.dependency_overrides[get_db] = lambda: db
    return TestClient(api)


def test_admin_key_alone_cannot_delete_and_phone_channel_invalid(db, delivery, monkeypatch):
    monkeypatch.setenv('PRUVIO_ADMIN_API_KEY', 'admin-test-key')
    with api_client(db) as api:
        headers = {'x-pruvio-admin-key': 'admin-test-key'}
        account_id = user(db).id
        assert api.delete(f'/users/{account_id}', headers=headers).status_code == 422
        assert api.request('DELETE', f'/users/{account_id}', headers=headers, json={'channel': 'phone', 'code': '123456'}).status_code == 422
        result = api.post(f'/users/{account_id}/deletion-otp', headers=headers).json()
        response = api.request('DELETE', f'/users/{account_id}', headers=headers, json={'channel': 'email', 'code': result['debug_otp'], 'challenge_id': result['challenge_id']})
        assert response.status_code == 200 and response.json()['deleted']


def test_phone_verify_api_disabled_username_availability(db):
    with api_client(db) as api:
        assert api.post('/onboarding/verify-phone', json={'phone_number': '+40711111111', 'code': '123456'}).status_code == 410
        assert not api.get('/auth/username/available', params={'username': ' TEST  USER '}).json()['available']
        assert api.get('/auth/username/available', params={'username': 'New Unique'}).json()['available']


def test_bad_password_does_not_consume_reset_code_or_create_registration(db, delivery):
    result = accounts.request_password_reset(db, user(db).email)
    with pytest.raises(ValueError):
        accounts.confirm_password_reset(db, user(db).email, result['debug_otp'], 'short', challenge_id=result['challenge_id'])
    assert db.query(VerificationCode).one().status == 'pending'
    with pytest.raises(ValueError):
        registration(db, password='short')
    assert db.query(User).count() == 1


def test_migration_unique_names_preserves_accounts_and_is_idempotent(monkeypatch):
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR, phone_number VARCHAR, email VARCHAR, username VARCHAR, username_key VARCHAR)'))
        rows = [(1, ' Test  User ', None, None), (2, 'TEST USER', None, None), (3, 'Ｔｅｓｔ Ｕｓｅｒ', None, None), (4, 'Test User', 'Custom User', 'custom user')]
        for i, name, username, key in rows:
            conn.execute(text('INSERT INTO users VALUES (:id,:name,:phone,:email,:username,:key)'), dict(id=i,name=name,phone=f'+4071111111{i}',email=f'user{i}@example.com',username=username,key=key))
        conn.execute(text('CREATE TABLE verification_codes (id INTEGER PRIMARY KEY, destination_type VARCHAR, status VARCHAR, code_ciphertext VARCHAR)'))
        conn.execute(text("INSERT INTO verification_codes VALUES (1,'phone','pending','old-secret')"))
    monkeypatch.setattr(database, 'engine', engine)
    database.ensure_compatibility_schema()
    with engine.connect() as conn:
        first = conn.execute(text('SELECT id, username, username_key, phone_number, email FROM users ORDER BY id')).all()
        assert [r.username for r in first] == ['Test User', 'TEST USER (2)', 'Test User (3)', 'Custom User']
        assert len({r.username_key for r in first}) == 4
        assert [(r.phone_number, r.email) for r in first] == [(f'+4071111111{i}', f'user{i}@example.com') for i in range(1,5)]
        assert conn.execute(text('SELECT status,code_ciphertext FROM verification_codes')).one() == ('expired',None)
    database.ensure_compatibility_schema()
    with engine.connect() as conn:
        assert conn.execute(text('SELECT id, username, username_key, phone_number, email FROM users ORDER BY id')).all() == first
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE users SET username_key='test user' WHERE id=2"))


@pytest.mark.parametrize('status', ['open', 'closed', 'settled'])
def test_owner_cannot_join_shared_bill_even_existing_participant(db, status):
    owner = user(db)
    case = Case(user_id=owner.id); db.add(case); db.commit()
    add_receipt(db, case)
    session = create_split_bill_session(db, case.id, owner.id, 3)
    before = db.query(SplitBillParticipant).one()
    before.display_name = 'Do not overwrite'; session.status=status; db.commit()
    with pytest.raises(ValueError, match='owner of this bill'):
        join_split_bill_session_as_user(db, session, owner)
    assert db.query(SplitBillParticipant).count() == 1
    assert db.query(SplitBillParticipant).one().display_name == 'Do not overwrite'
    if status == 'open':
        with pytest.raises(ValueError, match='owner of this bill'):
            join_split_bill_session(db, session, owner.phone_number, 'Fake name')


def test_other_user_joins_and_reopens_without_duplicate(db):
    owner = user(db)
    case = Case(user_id=owner.id); db.add(case); db.commit()
    add_receipt(db, case)
    session = create_split_bill_session(db, case.id, owner.id, 3)
    other = User(username='Guest User', username_key='guest user', phone_number='+40722222222', email='other@example.com', name='Guest', status='active', is_email_verified=True)
    db.add(other); db.commit()
    result = join_split_bill_session_as_user(db, session, other)
    again = join_split_bill_session_as_user(db, session, other)
    assert result['status'] == 'joined' and again['status'] == 'already_joined'
    assert result['participant_id'] == again['participant_id']
    assert db.query(SplitBillParticipant).count() == 2


def test_direct_whatsapp_otp_disabled_even_with_old_env(monkeypatch):
    monkeypatch.setenv('WHATSAPP_OTP_ENABLED', 'true')
    assert phone.whatsapp_otp_enabled() is False
    with pytest.raises(ValueError, match='disabled'):
        phone.send_whatsapp_otp('+40711111111', '123456')
