"""Real NiceGUI ASGI/callback smoke checks. No outbound messages or OCR calls."""
import asyncio
import importlib
import inspect
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nicegui import app, ui
from nicegui.client import Client
from nicegui.elements.button import Button
from nicegui.elements.input import Input
from nicegui.elements.label import Label
from nicegui.elements.select import Select
from nicegui.elements.dialog import Dialog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ.update(OTP_SECRET='local-validation-'+'a'*32, OTP_DEBUG_RETURN_CODE='true', OTP_RESEND_COOLDOWN_SECONDS='0',
                  OTP_MAX_SENDS_PER_HOUR='50', WHATSAPP_OTP_ENABLED='false', DEV_TOTP_ENABLED='false', PASSKEY_ENABLED='false',
                  ENABLE_RECEIPT_TRANSLATION='false')
from app.db import database
for model in (root/'app/models').glob('*.py'):
    importlib.import_module('app.models.'+model.stem)
engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
database.Base.metadata.create_all(engine)
database.SessionLocal = sessionmaker(bind=engine)
from app.models.user import User
from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.case import Case
from app.models.verification_code import VerificationCode
from app.models.split_bill_participant import SplitBillParticipant
from app.services.password_service import hash_password
from app.services.trusted_device_service import DEVICE_COOKIE, create_device_claim, consume_device_claim
from app.services.split_bill_session_service import create_split_bill_session, get_owner_participant
from app.services import phone_otp_service, onboarding_otp_service
phone_otp_service.send_sms_verification_code = Mock(side_effect=AssertionError('SMS must not be sent'))
onboarding_otp_service.send_email_verification_code = Mock(return_value={'sent': True, 'provider': 'resend', 'status': 'queued'})
service = types.ModuleType('app.services.standalone_app_service')
service.list_recent_receipts = lambda *a, **kw: []
sys.modules[service.__name__] = service
from app.ui import home_ui, register_ui, account_ui, password_reset_ui, split_bill_session_widget_ui as shared_ui
from app.ui.auth_state import get_logged_in_user_id, logout_user, login_user, POST_LOGIN_PATH_KEY
from app.ui.email_otp_dialog import EmailOTPDialog
from app.i18n import t
from app.api.trusted_device import router as device_router
for module in [home_ui, register_ui, account_ui, password_reset_ui, shared_ui]:
    getattr(module, 'setup_' + ('split_bill_session_widget_ui' if module is shared_ui else module.__name__.split('.')[-1]))()
app.add_static_files('/static', str(root/'app/static'))
asgi=FastAPI(); asgi.include_router(device_router,prefix='/auth')
ui.run_with(asgi,storage_secret='local-validation-only')
with database.SessionLocal() as db:
    account=User(username='Test User', username_key='test user', name='Test User', email='test@example.com', phone_number='+40711111111',
        status='active', is_email_verified=True, accepted_terms=True, accepted_privacy=True, password_hash=hash_password('testing-password'))
    other=User(username='Other User', username_key='other user', name='Other User', email='other@example.com', phone_number='+40722222222',
        status='active', is_email_verified=True, accepted_terms=True, accepted_privacy=True)
    db.add_all([account,other]); db.commit()
    account_id=account.id; other_id=other.id
    trusted_token=consume_device_claim(db,create_device_claim(db,account))
    case=Case(user_id=account_id); db.add(case); db.commit()
    document=Document(case_id=case.id,stored_filename='test.pdf',path='test.pdf'); db.add(document); db.commit()
    db.add(ReceiptItem(case_id=case.id,document_id=document.id,name='Meal',quantity=1,total_price=30,currency='RON')); db.commit()
    bill=create_split_bill_session(db,case.id,account_id,3)
    token=bill.token; owner_participant_id=get_owner_participant(db,bill).id


def callback(button):
    listener=next(x for x in button._event_listeners.values() if x.type=='click')
    return inspect.getclosurevars(listener.handler).nonlocals.get('callback',listener.handler)


def buttons(page):
    return [e for e in page.elements.values() if isinstance(e,Button)]


def button(page,text):
    return next(e for e in buttons(page) if e.text==text)


def input_named(page,label):
    return next(e for e in page.elements.values() if isinstance(e,Input) and e._props.get('label')==label)


def dialog_for(element):
    current=element
    while current.parent_slot:
        current=current.parent_slot.parent
        if isinstance(current,Dialog): return current
    return None


def popups(page):
    return [callback(e).__self__ for e in buttons(page)
            if isinstance(getattr(callback(e),'__self__',None),EmailOTPDialog) and getattr(callback(e),'__name__','')=='verify']


def page_get(api,path):
    before=set(Client.instances)
    response=api.get(path)
    assert response.status_code==200, response.text[:500]
    return next(c for key,c in Client.instances.items() if key not in before)


def run_page(page,fn):
    async def run():
        from nicegui.storage import request_contextvar
        context=request_contextvar.set(page.request)
        try:
            with page:
                result=fn()
                if inspect.isawaitable(result): await result
        finally: request_contextvar.reset(context)
    asyncio.run(run())

navigations=[]
original_navigate=ui.navigate.to
ui.navigate.to=lambda target,**kw:navigations.append(target)
with TestClient(asgi) as api:
    async def remember_cookie(script,**kw):
        claim=script.split('JSON.stringify({claim: ')[1].split('})')[0]
        return api.post('/auth/device/remember',json={'claim':json.loads(claim)}).is_success
    original_js=ui.run_javascript; ui.run_javascript=remember_cookie
    try:
        for language,trusted in [('en',False),('en',True),('ro',False),('ro',True)]:
            home_ui.get_ui_language=lambda:language
            api.cookies.delete(DEVICE_COOKIE)
            if trusted: api.cookies.set(DEVICE_COOKIE,trusted_token)
            page=page_get(api,'/')
            async def check_login():
                navigations.clear()
                popup=popups(page)[0]
                assert popup.dialog.value is False
                assert dialog_for(popup.code)==popup.dialog
                assert not any(isinstance(e,Select) for e in page.elements.values())
                identifier=input_named(page,'Nume utilizator sau email' if language=='ro' else 'Username or email')
                email_button=button(page,'Autentificare cu un cod pe email' if language=='ro' else 'Sign in with email code')
                assert not email_button.visible
                identifier.set_value(' TEST  USER ')
                assert email_button.visible is not trusted
                assert not popup.dialog.value
                input_named(page,t('Password',language)).set_value('testing-password')
                sent_before=onboarding_otp_service.send_email_verification_code.call_count
                await callback(button(page,t('Sign in with password',language)))()
                if trusted:
                    assert get_logged_in_user_id()==account_id and navigations==['/']
                    assert not popup.dialog.value and onboarding_otp_service.send_email_verification_code.call_count==sent_before
                else:
                    assert not get_logged_in_user_id() and not navigations and popup.dialog.value
                    popup.code.set_value('12')
                    await popup.verify()
                    assert popup.dialog.value and not get_logged_in_user_id()
                    popup.code.set_value(onboarding_otp_service.send_email_verification_code.call_args.args[1])
                    await popup.verify()
                    assert get_logged_in_user_id()==account_id and navigations==['/'] and not popup.dialog.value, popup.error.text
                logout_user()
            run_page(page,check_login)
        print('PASS: EN/RO new and trusted browser login, username, email-only hidden modal, real OTP/cookie handoff')

        register_ui.get_ui_language=lambda:'en'
        page=page_get(api,'/register')
        async def check_registration():
            navigations.clear()
            popup=popups(page)[0]
            assert not popup.dialog.value
            name=input_named(page,t('Full name','en')); name.set_value('New Person')
            assert input_named(page,'Username').value=='New Person'
            input_named(page,t('Email address','en')).set_value('new@example.com')
            input_named(page,'Phone number (contact only)').set_value('+40733333333')
            input_named(page,t('Password','en')).set_value('new-password')
            input_named(page,t('Confirm password','en')).set_value('new-password')
            legal=next(e for e in page.elements.values() if isinstance(e,Button) and e.text==t('View Terms of Use','en'))
            # Mark actual legal documents as reviewed through their dialog callbacks.
            for e in buttons(page):
                if e.text==t('I have reviewed this document','en'): callback(e)()
            from nicegui.elements.checkbox import Checkbox
            for e in page.elements.values():
                if isinstance(e,Checkbox) and e.text in [t('I accept the Terms of Use','en'),t('I acknowledge the Privacy Notice','en')]: e.set_value(True)
            submit=button(page,'Create account')
            input_named(page,'Username').set_value(' TEST  USER ')
            sent_before=onboarding_otp_service.send_email_verification_code.call_count
            callback(submit)()
            assert not popup.dialog.value and onboarding_otp_service.send_email_verification_code.call_count==sent_before
            input_named(page,'Username').set_value('New Person')
            callback(submit)()
            assert popup.dialog.value
            with database.SessionLocal() as db:
                created=db.query(User).filter_by(email='new@example.com').one()
                assert created.status=='pending_join'
                assert db.query(VerificationCode).filter_by(user_id=created.id).count()==1
            popup.code.set_value(onboarding_otp_service.send_email_verification_code.call_args.args[1])
            await popup.verify()
            assert get_logged_in_user_id()==created.id and navigations==['/account'], popup.error.text
            logout_user()
        run_page(page,check_registration)
        print('PASS: registration availability/full-name default and email-only activation popup')

        # Establish owner session using the same signed NiceGUI test-client session.
        run_page(page,lambda: login_user(database.SessionLocal().get(User,account_id)))
        page=page_get(api,'/account')
        async def check_contact():
            navigations.clear()
            all_popups=popups(page)
            assert len(all_popups)==3 and all(not p.dialog.value for p in all_popups)
            otp_inputs=[e for e in page.elements.values() if isinstance(e,Input) and e._props.get('autocomplete')=='one-time-code']
            assert len(otp_inputs)==3 and all(dialog_for(e) for e in otp_inputs)
            phone_popup=all_popups[1]
            input_named(page,t('New phone number','en')).set_value('+40744444444')
            callback(button(page,'Change phone number'))()
            assert phone_popup.dialog.value and phone_popup.destination=='test@example.com'
            with database.SessionLocal() as db:
                assert db.get(User,account_id).phone_number=='+40711111111'
            # Editing the underlying field cannot change the OTP's proposed phone value.
            input_named(page,t('New phone number','en')).set_value('+40755555555')
            phone_popup.code.set_value(onboarding_otp_service.send_email_verification_code.call_args.args[1])
            await phone_popup.verify()
            assert not phone_popup.dialog.value and navigations==['/account'], phone_popup.error.text
            with database.SessionLocal() as db:
                assert db.get(User,account_id).phone_number=='+40744444444'
            # Start deletion but verify only when the explicit popup is confirmed.
            deletion=all_popups[2]
            callback(button(page,t('Delete account','en')))()
            assert deletion.dialog.value and deletion.destination=='test@example.com'
            deletion.code.set_value('000000'); await deletion.verify()
            with database.SessionLocal() as db: assert db.get(User,account_id)
            deletion.close()
            # Switching accounts in a different tab must not let an old account popup mutate its original account.
            logout_user()
            with database.SessionLocal() as db: login_user(db.get(User,other_id))
            sent_before=onboarding_otp_service.send_email_verification_code.call_count
            callback(button(page,t('Delete account','en')))()
            assert not deletion.dialog.value and onboarding_otp_service.send_email_verification_code.call_count==sent_before
            with database.SessionLocal() as db: login_user(db.get(User,account_id))
        run_page(page,check_contact)
        print('PASS: account popup visibility, phone change confirmed by bound email OTP, deletion requires correct code')

        for language in ['en','ro']:
            with database.SessionLocal() as db:
                owner=db.get(User,account_id); owner.preferred_language=language; db.commit()
            management=page_get(api,f'/split-bill/sessions/{token}/widget-ui?participant_id={owner_participant_id}')
            assert any(e.text == ('Distribuie' if language == 'ro' else 'Share') for e in buttons(management))
            page=page_get(api,f'/split-bill/sessions/{token}/join')
            def check_owner():
                navigations.clear()
                labels=[e.text for e in page.elements.values() if isinstance(e,Label)]
                assert ('Ești proprietarul acestei note' if language=='ro' else 'You are the owner of this bill') in labels
                assert not any(e.text in ['Join bill','Open split','Deschide împărțirea'] for e in buttons(page))
                callback(button(page,'Folosește alt cont' if language=='ro' else 'Use another account'))()
                assert get_logged_in_user_id() is None and navigations==['/']
                assert app.storage.user[POST_LOGIN_PATH_KEY]==f'/split-bill/sessions/{token}/join'
                with database.SessionLocal() as db:
                    target=login_user(db.get(User,account_id))
                    assert target==f'/split-bill/sessions/{token}/join'
            run_page(page,check_owner)
        participant_page=page_get(api,f'/split-bill/sessions/{token}/p/not-an-owner-route/widget-ui')
        run_page(participant_page,lambda: callback(button(participant_page,'Deconectare'))())
        run_page(participant_page,lambda: login_user(database.SessionLocal().get(User,other_id)))
        page=page_get(api,f'/split-bill/sessions/{token}/join')
        def check_other():
            navigations.clear()
            callback(button(page,t('Join bill','en')))()
            assert len(navigations)==1 and '/p/' in navigations[0]
            with database.SessionLocal() as db: assert db.query(SplitBillParticipant).count()==2
            logout_user()
        run_page(page,check_other)
        print('PASS: EN/RO owners blocked on shared routes, sign-out/account switching, other users can join')

        password_reset_ui.get_ui_language=lambda:'en'
        page=page_get(api,'/reset-password')
        async def check_reset():
            popup=popups(page)[0]
            assert not popup.dialog.value
            input_named(page,t('Email address','en')).set_value('other@example.com')
            input_named(page,t('New password','en')).set_value('new-other-password')
            input_named(page,t('Confirm new password','en')).set_value('new-other-password')
            callback(button(page,t('Send reset code','en')))()
            assert popup.dialog.value
            popup.code.set_value(onboarding_otp_service.send_email_verification_code.call_args.args[1])
            await popup.verify()
            assert not popup.dialog.value, popup.error.text
        run_page(page,check_reset)
        print('PASS: password reset email popup')
        run_page(page,lambda: login_user(database.SessionLocal().get(User,other_id)))
        page=page_get(api,'/account')
        async def check_delete_success():
            popup=popups(page)[2]
            assert not popup.dialog.value
            callback(button(page,t('Delete account','en')))()
            assert popup.dialog.value
            popup.code.set_value(onboarding_otp_service.send_email_verification_code.call_args.args[1])
            await popup.verify()
            assert not popup.dialog.value and get_logged_in_user_id() is None, popup.error.text
            with database.SessionLocal() as db:
                assert db.get(User,other_id) is None
                assert db.get(User,account_id) is not None
        run_page(page,check_delete_success)
        print('PASS: explicit email deletion popup removes only that account and signs out')

    finally:
        ui.run_javascript=original_js
        ui.navigate.to=original_navigate
