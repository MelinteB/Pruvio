"""Stripe Billing for Pruvs (NOT Stripe Connect and NOT a merchant wallet).

No card numbers or Stripe API keys are stored by Pruvs. Webhooks are the only
source of payment activation. Disabled by default until sandbox is configured.
"""
import html
import os
from datetime import datetime
from urllib.parse import urlparse
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from app.db.database import get_db, SessionLocal
from app.models.user import User
from app.models.pruvs_commerce import DemoSubscription
from app.models.pruvs_billing import (PruvsPlanConfig, PruvsStripeAccount,
    PruvsStripeCheckout, PruvsStripeEvent, PruvsInvoiceEmail)
from app.react_app.auth import current, admin
from app.react_app.plan_catalog import get_plan, plan_catalog, update_plan, credit_costs, update_credit_costs

router = APIRouter(prefix='/api/v1/commerce/billing', tags=['Stripe subscriptions'])
webhook_router = APIRouter(prefix='/api/v1/stripe', tags=['Stripe webhooks'])


def enabled():
    return os.getenv('PRUVS_STRIPE_ENABLED', 'false').lower() == 'true'


def stripe_sdk():
    try:
        import stripe
    except ImportError:
        raise HTTPException(503, 'Stripe SDK is unavailable. Install Python stripe dependency.')
    secret = os.getenv('STRIPE_SECRET_KEY', '')
    if not enabled() or not secret or not os.getenv('STRIPE_WEBHOOK_SECRET'):
        raise HTTPException(503, 'Subscription payments are not configured.')
    if os.getenv('PRUVS_STRIPE_MODE', 'test') == 'test' and not secret.startswith('sk_test_'):
        raise HTTPException(503, 'Refusing live credentials while Stripe test mode is selected.')
    if os.getenv('PRUVS_STRIPE_MODE', 'test') == 'live' and not secret.startswith('sk_live_'):
        raise HTTPException(503, 'Refusing test credentials in Stripe live mode.')
    stripe.api_key = secret
    return stripe


def base_url():
    public = os.getenv('PRUVS_PUBLIC_URL', 'https://pruvs.io').rstrip('/')
    parsed = urlparse(public)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path:
        raise HTTPException(503, 'PRUVS_PUBLIC_URL must be a secure site origin.')
    return public


def read(obj, key, default=None):
    return (obj.get(key, default) if hasattr(obj, 'get') else getattr(obj, key, default)) if obj is not None else default


def identifier(obj):
    return obj if isinstance(obj, str) else read(obj, 'id')


def dt(timestamp):
    return datetime.utcfromtimestamp(int(timestamp)) if timestamp else None


def period_end(subscription):
    timestamp = read(subscription, 'current_period_end')
    if not timestamp:
        items = read(read(subscription, 'items'), 'data', []) or []
        timestamp = read(items[0], 'current_period_end') if items else None
    return dt(timestamp)


def stripe_account(db, uid):
    row = db.get(PruvsStripeAccount, uid)
    if not row:
        row = PruvsStripeAccount(user_id=uid)
        db.add(row)
    return row


def billing_snapshot(db, uid):
    row = db.get(PruvsStripeAccount, uid)
    return {
        'payment_available': enabled() and bool(os.getenv('STRIPE_SECRET_KEY')) and bool(os.getenv('STRIPE_WEBHOOK_SECRET')),
        'mode': os.getenv('PRUVS_STRIPE_MODE', 'test'),
        'status': row.status if row else 'none',
        'plan': row.plan if row else None,
        'cancel_at_period_end': bool(row.cancel_at_period_end) if row else False,
        'period_end': row.current_period_end.isoformat() + 'Z' if row and row.current_period_end else None,
        'has_subscription': bool(row and row.subscription_id),
        'has_customer': bool(row and row.customer_id),
    }


@router.post('/checkout')
def checkout(body: dict, identity=Depends(current), db=Depends(get_db)):
    stripe = stripe_sdk()
    plan_key = str(body.get('plan', '')).lower()
    if plan_key not in ('plus', 'business'):
        raise HTTPException(422, 'Choose Plus or Business.')
    plan = get_plan(db, plan_key)
    if not plan['stripe_price_id']:
        raise HTTPException(409, 'This plan is not published to Stripe yet.')
    uid = identity[0].id
    existing = db.get(PruvsStripeAccount, uid)
    if existing and existing.subscription_id and existing.status not in ('canceled', 'incomplete_expired', 'none'):
        raise HTTPException(409, 'Manage or cancel your existing paid subscription first.')
    if not identity[0].email or not identity[0].is_email_verified:
        raise HTTPException(403, 'Verify your email address before subscribing.')
    from datetime import timedelta
    recent=db.query(PruvsStripeCheckout).filter(PruvsStripeCheckout.user_id==uid,
        PruvsStripeCheckout.created_at >= datetime.utcnow()-timedelta(minutes=10)).first()
    if recent:
        raise HTTPException(409, 'A checkout session was created recently. Complete or cancel it before retrying.')
    kwargs = {
        'mode': 'subscription',
        'line_items': [{'price': plan['stripe_price_id'], 'quantity': 1}],
        'client_reference_id': str(uid),
        'billing_address_collection': 'required',
        'success_url': base_url() + '/account?stripe=success&session_id={CHECKOUT_SESSION_ID}#membership',
        'cancel_url': base_url() + '/account?stripe=cancelled#membership',
        'metadata': {'pruvs_user_id': str(uid), 'pruvs_plan': plan_key},
        'subscription_data': {'metadata': {'pruvs_user_id': str(uid), 'pruvs_plan': plan_key}},
        'customer_update': {'address': 'auto', 'name': 'auto'} if existing and existing.customer_id else None,
    }
    kwargs = {key: value for key, value in kwargs.items() if value is not None}
    if existing and existing.customer_id:
        kwargs['customer'] = existing.customer_id
    else:
        kwargs['customer_email'] = identity[0].email
    try:
        session = stripe.checkout.Session.create(**kwargs)
    except Exception:
        raise HTTPException(502, 'Could not start Stripe Checkout. Try again.')
    session_id = identifier(session)
    url = read(session, 'url')
    if not session_id or not url or urlparse(url).scheme != 'https':
        raise HTTPException(502, 'Stripe Checkout did not return a valid session.')
    db.add(PruvsStripeCheckout(session_id=session_id, user_id=uid, plan=plan_key,
                               price_id=plan['stripe_price_id'], customer_id=identifier(read(session,'customer'))))
    db.commit()
    return {'checkout_url': url, 'session_id': session_id, 'activation': 'after_verified_payment'}


def subscribed(identity, db):
    row = db.get(PruvsStripeAccount, identity[0].id)
    if not row or not row.subscription_id or row.status in ('none','canceled','incomplete_expired'):
        raise HTTPException(409, 'No active Stripe subscription to manage.')
    return row


@router.post('/cancel')
def cancel(identity=Depends(current), db=Depends(get_db)):
    stripe = stripe_sdk()
    row = subscribed(identity, db)
    if row.cancel_at_period_end:
        return {'ok': True, 'cancel_at_period_end': True}
    try:
        subscription = stripe.Subscription.modify(row.subscription_id, cancel_at_period_end=True)
    except Exception:
        raise HTTPException(502, 'Unable to schedule cancellation. Try again.')
    row.cancel_at_period_end = bool(read(subscription, 'cancel_at_period_end'))
    row.current_period_end = period_end(subscription) or row.current_period_end
    db.commit()
    return {'ok': True, 'cancel_at_period_end': row.cancel_at_period_end,
            'period_end': row.current_period_end.isoformat() + 'Z' if row.current_period_end else None}


@router.post('/resume')
def resume(identity=Depends(current), db=Depends(get_db)):
    stripe = stripe_sdk()
    row = subscribed(identity, db)
    if not row.cancel_at_period_end:
        return {'ok': True, 'cancel_at_period_end': False}
    try:
        subscription = stripe.Subscription.modify(row.subscription_id, cancel_at_period_end=False)
    except Exception:
        raise HTTPException(502, 'Unable to resume renewal. Your plan may have expired.')
    row.cancel_at_period_end = bool(read(subscription, 'cancel_at_period_end'))
    db.commit()
    return {'ok': True, 'cancel_at_period_end': row.cancel_at_period_end}


@router.post('/portal')
def portal(identity=Depends(current), db=Depends(get_db)):
    stripe = stripe_sdk()
    row = db.get(PruvsStripeAccount, identity[0].id)
    if not row or not row.customer_id:
        raise HTTPException(409, 'There is no billing customer on this account.')
    try:
        session = stripe.billing_portal.Session.create(customer=row.customer_id,
                                                        return_url=base_url()+'/account#membership')
    except Exception:
        raise HTTPException(502, 'Billing portal is not yet configured in Stripe.')
    return {'url': read(session,'url')}


@router.get('/invoices')
def invoices(identity=Depends(current), db=Depends(get_db)):
    stripe = stripe_sdk()
    row = db.get(PruvsStripeAccount, identity[0].id)
    if not row or not row.customer_id:
        return []
    try:
        result = stripe.Invoice.list(customer=row.customer_id, limit=20)
    except Exception:
        raise HTTPException(502, 'Cannot load invoices right now.')
    return [{'id': read(inv,'id'), 'status': read(inv,'status'),
             'created': dt(read(inv,'created')).isoformat()+'Z' if read(inv,'created') else None,
             'total_minor': read(inv,'total',0), 'currency': read(inv,'currency'),
             'invoice_url': read(inv,'hosted_invoice_url'), 'pdf_url': read(inv,'invoice_pdf')}
            for inv in read(result,'data',[]) or []]


@router.get('/admin/plans')
def all_plans(identity=Depends(admin), db=Depends(get_db)):
    return plan_catalog(db)


@router.put('/admin/plans/{key}')
def edit_plan(key: str, body: dict, identity=Depends(admin), db=Depends(get_db)):
    return update_plan(db, key, body, identity[0].id)


@router.get('/admin/pc-costs')
def admin_pc_costs(identity=Depends(admin), db=Depends(get_db)):
    return credit_costs(db)


@router.put('/admin/pc-costs')
def admin_update_pc_costs(body:dict, identity=Depends(admin), db=Depends(get_db)):
    return update_credit_costs(db,body,identity[0].id)


@router.post('/admin/plans/{key}/publish')
def publish_plan(key: str, body: dict, identity=Depends(admin), db=Depends(get_db)):
    """Create a new Stripe Price for this exact DB version, never rewrite live subscriptions."""
    if key not in ('plus','business'):
        raise HTTPException(422, 'Only paid plans can be published.')
    stripe = stripe_sdk()
    row = db.query(PruvsPlanConfig).filter_by(key=key).with_for_update().first()
    if row is None:
        raise HTTPException(409, 'Save this plan in Admin before publishing to Stripe.')
    if int(body.get('version', -1)) != row.version:
        raise HTTPException(409, 'Plan was edited; refresh before publishing.')
    product_id = row.stripe_product_id
    price_id = row.stripe_price_id
    try:
        if not product_id:
            product = stripe.Product.create(name='Pruvs '+key.title(),
                  description=row.description,
                  metadata={'pruvs_plan':key},
                  idempotency_key=f'pruvs-{key}-product')
            product_id = identifier(product)
        else:
            stripe.Product.modify(product_id, name='Pruvs '+key.title(),
                    description=row.description)
        if not price_id:
            price = stripe.Price.create(product=product_id, currency=row.currency,
                        unit_amount=row.price_minor,
                        recurring={'interval':row.interval,'interval_count':row.interval_count},
                        metadata={'pruvs_plan':key,'catalog_version':str(row.version)},
                        idempotency_key=f'pruvs-{key}-v{row.version}-price')
            price_id = identifier(price)
    except Exception:
        db.rollback()
        raise HTTPException(502, 'Stripe could not publish or synchronize this plan.')
    row.stripe_product_id = product_id
    row.stripe_price_id = price_id
    db.commit()
    return get_plan(db, key)


@router.post('/admin/plans/{key}/attach-price')
def attach_price(key: str, body: dict, identity=Depends(admin), db=Depends(get_db)):
    """Bind a pre-existing Stripe recurring Price to Pruvs after verifying all fields."""
    stripe = stripe_sdk()
    if key not in ('plus', 'business'):
        raise HTTPException(422, 'Only paid plans can accept Stripe prices.')
    row = db.query(PruvsPlanConfig).filter_by(key=key).with_for_update().first()
    if row is None:
        raise HTTPException(409, 'Save this plan before attaching a Stripe price.')
    price_id = str(body.get('price_id','')).strip()
    if not price_id.startswith('price_') or int(body.get('version',-1)) != row.version:
        raise HTTPException(422, 'Provide a valid Stripe Price ID and current version.')
    try:
        p = stripe.Price.retrieve(price_id)
    except Exception:
        raise HTTPException(422, 'Stripe Price not found in the configured account.')
    recurring = read(p,'recurring')
    if (not read(p,'active') or read(p,'type')!='recurring' or
        int(read(p,'unit_amount',-1)) != row.price_minor or read(p,'currency') != row.currency or
        read(recurring,'interval') != row.interval or int(read(recurring,'interval_count',1))!=row.interval_count):
        raise HTTPException(422, 'Stripe Price must match currency, amount and billing interval exactly.')
    row.stripe_price_id = price_id
    row.stripe_product_id = identifier(read(p,'product'))
    db.commit()
    return get_plan(db, key)


def _invoice_subscription_id(invoice):
    subscription_id = identifier(read(invoice,'subscription'))
    if subscription_id:
        return subscription_id
    parent = read(invoice, 'parent')
    sid = identifier(read(read(parent,'subscription_details'), 'subscription'))
    if sid:return sid
    lines = read(read(invoice, 'lines'),'data',[]) or []
    for line in lines:
        details = read(read(line,'parent'),'subscription_item_details')
        sid = identifier(read(details,'subscription'))
        if sid:return sid
    return None


def _match_user(db, subscription):
    """Subscription metadata was set only by authenticated Pruvs Checkout."""
    metadata = read(subscription, 'metadata') or {}
    try:
        uid = int(read(metadata, 'pruvs_user_id'))
    except (ValueError, TypeError):
        return None
    if uid <= 0 or not db.get(User,uid):
        return None
    plan = str(read(metadata, 'pruvs_plan',''))
    if plan not in ('plus','business'):
        return None
    return uid


def _sync_paid(db, subscription):
    uid = _match_user(db, subscription)
    if not uid:
        return None
    sub_id = identifier(subscription)
    customer_id = identifier(read(subscription, 'customer'))
    if not sub_id or not customer_id:
        return None
    # A Checkout request for this user and plan must exist. No arbitrary
    # subscription to the Stripe account can grant Pruvs entitlements.
    plan = read(read(subscription,'metadata'), 'pruvs_plan')
    checkout = db.query(PruvsStripeCheckout).filter_by(user_id=uid, plan=plan).order_by(PruvsStripeCheckout.created_at.desc()).first()
    if not checkout:
        return None
    previous=db.get(PruvsStripeAccount,uid)
    if previous and previous.customer_id and previous.customer_id != customer_id:
        return None
    if previous and previous.subscription_id and previous.subscription_id != sub_id and previous.status not in ('canceled','none','incomplete_expired'):
        return None
    items = read(read(subscription,'items'),'data',[]) or []
    paid_price_id = identifier(read(items[0],'price')) if items else None
    if paid_price_id and paid_price_id != checkout.price_id:
        # Customer portal changes must not activate unrecognized replacement subscriptions.
        if not (previous and previous.subscription_id == sub_id):
            return None
    row = previous or stripe_account(db,uid)
    row.customer_id = customer_id
    row.subscription_id = sub_id
    row.plan = plan
    row.price_id = paid_price_id or checkout.price_id
    row.status = str(read(subscription,'status','active'))
    row.cancel_at_period_end = bool(read(subscription,'cancel_at_period_end',False))
    row.current_period_end = period_end(subscription)
    row.paid_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    current = db.get(DemoSubscription,uid)
    if current is None:
        current=DemoSubscription(user_id=uid)
        db.add(current)
    current.plan=plan
    current.status='stripe_paid'
    current.activated_at=datetime.utcnow()
    return uid


def _on_event(db, event, stripe):
    event_type = read(event,'type','')
    data = read(read(event,'data'),'object')
    invoice_for_email = None
    if event_type == 'checkout.session.completed':
        # Associate the signed Checkout Session with our previously created DB row.
        row = db.get(PruvsStripeCheckout, identifier(data))
        if row and str(read(data,'client_reference_id'))==str(row.user_id):
            row.customer_id = identifier(read(data,'customer'))
    elif event_type in ('invoice.paid','invoice.payment_succeeded'):
        sid = _invoice_subscription_id(data)
        if sid and read(data,'paid') is True:
            subscription = stripe.Subscription.retrieve(sid)
            if read(subscription,'status') in ('active','trialing'):
                uid = _sync_paid(db, subscription)
                if uid:
                    user = db.get(User,uid)
                    invoice_id = identifier(data)
                    url = read(data,'hosted_invoice_url')
                    if invoice_id and user and user.email and not db.get(PruvsInvoiceEmail, invoice_id):
                        db.add(PruvsInvoiceEmail(invoice_id=invoice_id,user_id=uid,
                            email=user.email,hosted_invoice_url=url))
                        invoice_for_email = invoice_id
    elif event_type in ('customer.subscription.updated','customer.subscription.deleted'):
        sub_id = identifier(data)
        row = db.query(PruvsStripeAccount).filter_by(subscription_id=sub_id).first()
        if row:
            status = read(data,'status')
            if event_type == 'customer.subscription.deleted' or status in ('canceled','incomplete_expired','unpaid'):
                row.status = 'canceled'
                active = db.get(DemoSubscription,row.user_id)
                if active and active.status=='stripe_paid':
                    active.plan='free';active.status='stripe_canceled'
            else:
                row.status = str(status)
            row.cancel_at_period_end = bool(read(data,'cancel_at_period_end',False))
            row.current_period_end = period_end(data) or row.current_period_end
            row.updated_at = datetime.utcnow()
    elif event_type == 'invoice.payment_failed':
        sid = _invoice_subscription_id(data)
        row = db.query(PruvsStripeAccount).filter_by(subscription_id=sid).first() if sid else None
        if row:
            row.status = 'past_due'
            row.updated_at = datetime.utcnow()
            # Access through end of already-paid period; account_plan enforces expiry.
    return invoice_for_email


def _stripe_https(url):
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        return None
    return url if parsed.hostname=='stripe.com' or parsed.hostname.endswith('.stripe.com') else None


def send_invoice_notice(invoice_id):
    """Optional Resend email with Stripe-hosted invoice URL; Stripe handles invoice PDF.

    On failure email remains in outbox so an admin can retry. Stripe dashboard
    must still be configured for invoice/payment email notifications.
    """
    token = os.getenv('RESEND_API_KEY')
    sender = os.getenv('PRUVS_INVOICE_FROM_EMAIL')
    if not token or not sender:
        return False
    with SessionLocal() as db:
        notice = db.get(PruvsInvoiceEmail, invoice_id)
        if not notice or notice.state=='sent' or notice.attempts>=5:
            return False
        link = _stripe_https(notice.hosted_invoice_url)
        if not link:
            notice.state='error';notice.error='Missing secure Stripe invoice URL.';db.commit();return False
        notice.attempts += 1
        db.commit()
        user = db.get(User, notice.user_id)
        name = (user.name or 'Pruvs customer') if user else 'Pruvs customer'
        message = ('Your Pruvs subscription invoice is ready. '+
                   'View or download the invoice from Stripe using the secure link below.')
        data = {'from':sender,'to':[notice.email],
                'subject':'Your Pruvs subscription invoice',
                'html':f'<p>Hello {html.escape(name)},</p><p>{html.escape(message)}</p>'+
                       f'<p><a href="{html.escape(link,quote=True)}">View invoice</a></p><p>Pruvs — https://pruvs.io</p>'}
        try:
            result = requests.post('https://api.resend.com/emails',json=data,timeout=12,
                  headers={'Authorization':'Bearer '+token,
                           'Content-Type':'application/json',
                           'Idempotency-Key':'pruvs-invoice-'+invoice_id})
            result.raise_for_status()
        except Exception as error:
            notice.state='error';notice.error=str(error)[:400]
            db.commit()
            return False
        notice.state='sent';notice.sent_at=datetime.utcnow();notice.error=None
        db.commit()
        return True


@router.get('/admin/invoice-emails')
def invoice_email_status(identity=Depends(admin), db=Depends(get_db)):
    rows = db.query(PruvsInvoiceEmail).order_by(PruvsInvoiceEmail.invoice_id.desc()).limit(100).all()
    return [{'invoice_id':r.invoice_id,'user_id':r.user_id,'state':r.state,
             'attempts':r.attempts,'error':r.error} for r in rows]


@router.post('/admin/invoice-emails/{invoice_id}/retry')
def retry_invoice(invoice_id:str, identity=Depends(admin), db=Depends(get_db)):
    notice = db.get(PruvsInvoiceEmail,invoice_id)
    if not notice:
        raise HTTPException(404,'Invoice email not found.')
    if notice.state=='sent':
        return {'ok':True,'status':'sent'}
    return {'ok':send_invoice_notice(invoice_id)}


@webhook_router.post('/webhook')
async def webhook(request: Request, db=Depends(get_db)):
    stripe = stripe_sdk()
    body = await request.body()
    if len(body)>1024*1024:
        raise HTTPException(413,'Webhook payload too large.')
    try:
        event = stripe.Webhook.construct_event(
            body, request.headers.get('stripe-signature',''),
            os.environ['STRIPE_WEBHOOK_SECRET'])
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(400,'Invalid Stripe webhook signature.')
    event_id=identifier(event)
    if not event_id:
        raise HTTPException(400,'Missing Stripe event id.')
    if db.get(PruvsStripeEvent,event_id):
        return {'received':True,'duplicate':True}
    invoice_email = None
    try:
        # Work and event marker commit together; failing work can be safely retried.
        invoice_email = _on_event(db,event,stripe)
        db.add(PruvsStripeEvent(event_id=event_id,event_type=read(event,'type','unknown')))
        db.commit()
    except IntegrityError:
        db.rollback()  # concurrent retry already wrote the event
        return {'received':True,'duplicate':True}
    except Exception:
        db.rollback()
        raise HTTPException(503,'Webhook processing failed; Stripe should retry.')
    if invoice_email:
        send_invoice_notice(invoice_email)  # best effort; visible in admin retry queue
    return {'received':True}
