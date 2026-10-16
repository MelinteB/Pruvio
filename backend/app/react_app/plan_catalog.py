"""Database-backed plan entitlements and admin validation.

Stripe Prices are immutable: changing billing amount/period unpublishes the
current purchasable price, but leaves existing Stripe subscriptions untouched.
"""
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime
from fastapi import HTTPException
from app.models.pruvs_billing import PruvsPlanConfig

DEFAULTS = {
    'free': {'price_minor': 0, 'ocr_allowance': 3, 'expense_reports': 1,
             'description': 'Free receipt and expense management'},
    'plus': {'price_minor': 299, 'ocr_allowance': 50, 'expense_reports': 10,
             'description': 'AI receipt scanning and expense reports for individuals'},
    'business': {'price_minor': 599, 'ocr_allowance': 75, 'expense_reports': 25,
                 'description': 'Additional AI scans and reporting for business users'},
}
FEATURES = ['Split bill and settlement history', 'Receipt history and corrections',
            'Expense tracking and reporting', 'Company and trip profiles',
            'Notifications and shared bills']


def as_dict(row, key):
    if row is None:
        d = dict(DEFAULTS[key])
        d.update(key=key, currency='eur', interval='month', interval_count=1,
                 stripe_price_id=None, stripe_product_id=None, version=0,
                 features=FEATURES)
    else:
        d = {'key': key, 'price_minor': row.price_minor, 'currency': row.currency,
             'interval': row.interval, 'interval_count': row.interval_count,
             'ocr_allowance': row.ocr_allowance, 'expense_reports': row.expense_reports,
             'description': row.description, 'version': row.version,
             'stripe_price_id': row.stripe_price_id, 'stripe_product_id': row.stripe_product_id,
             'features': json.loads(row.features_json or '[]')}
    d['price_eur'] = f"{d['price_minor'] / 100:.2f}" if d['currency'] == 'eur' else None
    d['price_display'] = f"{d['price_minor'] / 100:.2f} {d['currency'].upper()}"
    d['stripe_ready'] = bool(d.get('stripe_price_id'))
    return d


def plan_catalog(db):
    rows = {r.key: r for r in db.query(PruvsPlanConfig).all()}
    return {key: as_dict(rows.get(key), key) for key in DEFAULTS}


def get_plan(db, key):
    if key not in DEFAULTS:
        raise HTTPException(422, 'Unknown subscription plan.')
    return as_dict(db.get(PruvsPlanConfig, key), key)


def _minor(raw):
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise HTTPException(422, 'Enter a valid non-negative amount.')
    if not amount.is_finite() or amount < 0 or amount > 100000 or amount.as_tuple().exponent < -2:
        raise HTTPException(422, 'Enter a price with no more than two decimals.')
    return int(amount * 100)


def _count(raw, label, max_value):
    if isinstance(raw, bool):
        raise HTTPException(422, f'{label} must be an integer.')
    try:
        value = int(str(raw))
    except (ValueError, TypeError):
        raise HTTPException(422, f'{label} must be an integer.')
    if str(value) != str(raw) or value < 0 or value > max_value:
        raise HTTPException(422, f'{label} must be between 0 and {max_value}.')
    return value


def update_plan(db, key, body, admin_id):
    if key not in DEFAULTS:
        raise HTTPException(404, 'Plan not found.')
    if not isinstance(body, dict):
        raise HTTPException(422, 'Invalid plan configuration.')
    if 'version' not in body:
        raise HTTPException(422, 'Plan version required to prevent conflicting updates.')
    existing = db.query(PruvsPlanConfig).filter_by(key=key).with_for_update().first()
    previous = as_dict(existing, key)
    if int(body['version']) != previous['version']:
        raise HTTPException(409, 'Plan was changed by another administrator. Refresh and retry.')
    minor = _minor(body.get('price', previous['price_minor'] / 100))
    currency = str(body.get('currency', previous['currency'])).lower().strip()
    interval = str(body.get('interval', previous['interval'])).lower().strip()
    interval_count = _count(body.get('interval_count', previous['interval_count']), 'Billing interval count', 12)
    if interval not in ('month', 'year') or not 1 <= interval_count <= (12 if interval == 'month' else 3):
        raise HTTPException(422, 'Choose 1–12 months or 1–3 years per billing period.')
    if currency != 'eur':
        raise HTTPException(422, 'Only EUR is supported in this release.')
    if key == 'free' and minor != 0:
        raise HTTPException(422, 'The Free plan must remain free.')
    if key != 'free' and minor < 50:
        raise HTTPException(422, 'Paid plans must be at least €0.50.')
    ocr = _count(body.get('ocr_allowance', previous['ocr_allowance']), 'OCR allowance', 100000)
    reports = _count(body.get('expense_reports', previous['expense_reports']), 'Expense reports', 100000)
    description = str(body.get('description', previous['description'])).strip()
    if not description or len(description) > 400:
        raise HTTPException(422, 'Description must contain 1–400 characters.')
    features = body.get('features', previous['features'])
    if not isinstance(features, list) or len(features) > 30 or any(not isinstance(x,str) or not x.strip() or len(x)>150 for x in features):
        raise HTTPException(422, 'Provide up to 30 valid feature labels.')
    if existing is None:
        existing = PruvsPlanConfig(key=key, price_minor=minor,
                                   ocr_allowance=ocr, expense_reports=reports)
        db.add(existing)
    changing_price = (minor != previous['price_minor'] or currency != previous['currency'] or
                      interval != previous['interval'] or interval_count != previous['interval_count'])
    existing.price_minor = minor
    existing.currency = currency
    existing.interval = interval
    existing.interval_count = interval_count
    existing.ocr_allowance = ocr
    existing.expense_reports = reports
    existing.description = description
    existing.features_json = json.dumps(features)
    existing.updated_at = datetime.utcnow()
    existing.updated_by = admin_id
    existing.version = previous['version'] + 1
    if changing_price:
        existing.stripe_price_id = None  # publish new immutable Stripe Price explicitly
    db.commit()
    return get_plan(db, key)


def credit_costs(db):
    from app.models.pruvs_billing import PruvsCreditCostConfig
    row=db.get(PruvsCreditCostConfig,1)
    return {'ocr':row.ocr_pc if row else 2,
            'expense_report':row.report_pc if row else 5,
            'version':row.version if row else 0}


def update_credit_costs(db, body, admin_id):
    from app.models.pruvs_billing import PruvsCreditCostConfig
    row=db.query(PruvsCreditCostConfig).filter_by(id=1).with_for_update().first()
    before=credit_costs(db)
    if int(body.get('version',-1))!=before['version']:
        raise HTTPException(409,'PC prices were changed. Refresh and retry.')
    ocr=_count(body.get('ocr_pc',before['ocr']), 'OCR PC cost', 10000)
    reports=_count(body.get('report_pc',before['expense_report']), 'Report PC cost', 10000)
    if row is None:
        row=PruvsCreditCostConfig(id=1)
        db.add(row)
    row.ocr_pc=ocr
    row.report_pc=reports
    row.updated_by=admin_id
    row.version=before['version']+1
    db.commit()
    return credit_costs(db)
