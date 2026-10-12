"""Personal expense reports. The server verifies ownership and freezes source values."""
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.database import get_db
from app.models.case import Case
from app.models.document import Document
from app.models.expense import ExpenseCompany, ExpenseReport
from app.models.history_visibility import HistoryVisibility
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_session import SplitBillSession
from app.react_app.auth import current
from app.react_app.bill_service import get_split_bill_session_summary
from app.services.standalone_app_service import get_receipt_view

router = APIRouter(prefix='/api/v1/expenses', tags=['Expenses'])
COMPANY = ('name', 'tax_id', 'registration_number', 'vat_number', 'address', 'country', 'department', 'cost_center')
LENGTHS = {'name': 180, 'tax_id': 80, 'registration_number': 80, 'vat_number': 80, 'address': 500,
           'country': 100, 'department': 120, 'cost_center': 120}
CATEGORIES = {'flight_outbound', 'flight_return', 'taxi_outbound', 'taxi_return',
              'ground_transport', 'accommodation', 'restaurant', 'parking', 'tolls',
              'fuel', 'public_transport', 'client_meeting', 'other'}
DETAILS = {'purpose': 500, 'destination': 180, 'origin': 180, 'departure_date': 10,
           'return_date': 10, 'project': 150, 'cost_center': 120, 'approver': 150,
           'flight_outbound': 300, 'flight_return': 300, 'taxi_outbound': 300,
           'taxi_return': 300, 'accommodation': 300, 'restaurant_attendees': 300,
           'other_notes': 1000, 'advance_currency': 3, 'advance_amount': 24}
MONEY = Decimal('0.01')


def clean(value, limit, required=False):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('A text field is invalid or too long.')
    value = value.strip()
    if required and not value:
        raise ValueError('Fill in the company name, report title and business purpose.')
    return value


def amount(value, *, positive=True):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or (positive and number == 0) or number > Decimal('1000000000'):
            raise ValueError()
        if number.as_tuple().exponent < -2:
            raise ValueError()
        return number.quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Use a positive amount with at most two decimal places.') from None


def format_company(row):
    return {'id': row.id, **{field: getattr(row, field) for field in COMPANY}}


@router.get('/companies')
def companies(identity=Depends(current), db=Depends(get_db)):
    return [format_company(row) for row in db.query(ExpenseCompany).filter_by(user_id=identity[0].id).order_by(ExpenseCompany.name).all()]


def company_input(body):
    if not isinstance(body, dict):
        raise ValueError('Invalid company details.')
    return {key: clean(body.get(key, ''), LENGTHS[key], required=key == 'name') for key in COMPANY}


@router.post('/companies')
def create_company(body: dict, identity=Depends(current), db=Depends(get_db)):
    uid = identity[0].id
    if db.query(ExpenseCompany).filter_by(user_id=uid).count() >= 20:
        raise ValueError('Maximum 20 company profiles.')
    row = ExpenseCompany(user_id=uid, **company_input(body))
    db.add(row); db.commit(); db.refresh(row)
    return format_company(row)


@router.put('/companies/{company_id}')
def update_company(company_id: int, body: dict, identity=Depends(current), db=Depends(get_db)):
    row = db.query(ExpenseCompany).filter_by(id=company_id, user_id=identity[0].id).first()
    if row is None:
        raise HTTPException(404, 'Company profile not found.')
    for key, value in company_input(body).items():
        setattr(row, key, value)
    row.updated_at = datetime.utcnow(); db.commit()
    return format_company(row)


@router.delete('/companies/{company_id}')
def remove_company(company_id: int, identity=Depends(current), db=Depends(get_db)):
    row = db.query(ExpenseCompany).filter_by(id=company_id, user_id=identity[0].id).first()
    if row is None:
        raise HTTPException(404, 'Company profile not found.')
    db.delete(row); db.commit()
    return {'ok': True}


def source(db, uid, kind, source_id):
    if kind == 'receipt':
        case = db.query(Case).filter_by(id=source_id, user_id=uid).first()
        if not case or case.status in ('processing', 'processing_failed'):
            raise ValueError('A selected receipt is unavailable or still processing.')
        receipt = get_receipt_view(db, case.id, user_id=uid, ensure_translations=False)
        currency = receipt['currency']
        if not re.fullmatch('[A-Z]{3}', currency or ''):
            raise ValueError('Confirm the receipt currency before adding it to an expense.')
        doc = db.query(Document).filter_by(case_id=case.id).order_by(Document.id.desc()).first()
        return {'kind': kind, 'source_id': case.id, 'case_id': case.id,
                'source_url': f'/receipt/{case.id}', 'document_id': doc.id if doc else None,
                'filename': doc.original_filename if doc else '', 'date': case.created_at.date().isoformat(),
                'merchant': receipt['merchant_name'], 'currency': currency,
                'available_amount': str(amount(receipt['receipt_total']))}
    if kind == 'bill':
        session = db.get(SplitBillSession, source_id)
        participant = db.query(SplitBillParticipant).filter_by(session_id=source_id, user_id=uid, status='joined').first()
        if not session or not participant or session.status not in ('settled', 'closed'):
            raise ValueError('Select only settled bills in which you participated.')
        summary = get_split_bill_session_summary(db, session, ensure_translations=False)
        own = next((p for p in summary['participants'] if p['participant_id'] == participant.id), None)
        currency = summary['currency']
        if not own or not re.fullmatch('[A-Z]{3}', currency or ''):
            raise ValueError('This split bill has no confirmed currency or participant share.')
        return {'kind': kind, 'source_id': session.id, 'case_id': session.case_id,
                'source_url': f'/bill/{session.token}', 'document_id': None,
                'filename': f'Split bill #{session.id}', 'date': (session.settled_at or session.created_at).date().isoformat(),
                'merchant': f'Shared bill #{session.id}', 'currency': currency,
                'available_amount': str(amount(own.get('total') or 0))}
    raise ValueError('Unknown expense source.')


@router.get('/sources')
def sources(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
            identity=Depends(current), db=Depends(get_db)):
    uid = identity[0].id
    receipts = [(c.created_at, 'receipt', c.id) for c in db.query(Case).filter(Case.user_id == uid,
                Case.status.notin_(('processing', 'processing_failed'))).all()]
    bills = [(s.settled_at or s.created_at, 'bill', s.id) for s in db.query(SplitBillSession)
             .join(SplitBillParticipant, SplitBillParticipant.session_id == SplitBillSession.id)
             .filter(SplitBillParticipant.user_id == uid, SplitBillParticipant.status == 'joined',
                     SplitBillSession.status.in_(('settled', 'closed'))).distinct().all()]
    choices = sorted(receipts + bills, key=lambda entry: (entry[0], entry[2]), reverse=True)
    removed = {(row.kind, row.source_id) for row in db.query(HistoryVisibility)
               .filter_by(user_id=uid, state='removed').all()}
    choices = [choice for choice in choices if (choice[1], choice[2]) not in removed]
    rows = []
    for _, kind, source_id in choices[offset:offset + limit]:
        try:
            rows.append(source(db, uid, kind, source_id))
        except ValueError:
            continue
    return {'rows': rows, 'total': len(choices), 'has_more': offset + limit < len(choices)}


def details_input(body):
    if not isinstance(body, dict):
        raise ValueError('Provide the trip and business details.')
    result = {key: clean(body.get(key, ''), size, required=key == 'purpose') for key, size in DETAILS.items()}
    for field in ('departure_date', 'return_date'):
        if result[field]:
            try:
                if date.fromisoformat(result[field]).isoformat() != result[field]:
                    raise ValueError()
            except ValueError:
                raise ValueError('Use a valid date in YYYY-MM-DD format.') from None
    if result['departure_date'] and result['return_date'] and result['return_date'] < result['departure_date']:
        raise ValueError('Return date must follow departure date.')
    advance = amount(result['advance_amount'] or '0', positive=False)
    if advance and not re.fullmatch('[A-Z]{3}', result['advance_currency']):
        raise ValueError('Select the currency for the company advance.')
    result['advance_amount'] = str(advance)
    return result


@router.post('/reports')
def create_report(body: dict, identity=Depends(current), db=Depends(get_db)):
    uid = identity[0].id
    profile = db.query(ExpenseCompany).filter_by(id=body.get('company_id'), user_id=uid).first()
    if not profile:
        raise ValueError('Choose a company profile from your account.')
    title = clean(body.get('title', ''), 180, required=True)
    details = details_input(body.get('details'))
    raw = body.get('items')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 200:
        raise ValueError('Choose between 1 and 200 saved receipts or settled bills.')
    rows, unique, cases, totals, reimburse = [], set(), set(), {}, {}
    for item in raw:
        if not isinstance(item, dict) or type(item.get('source_id')) is not int:
            raise ValueError('Invalid expense source.')
        kind, source_id = item.get('kind'), item['source_id']
        if (kind, source_id) in unique:
            raise ValueError('The same bill was selected more than once.')
        unique.add((kind, source_id))
        current = source(db, uid, kind, source_id)
        if current['case_id'] in cases:
            raise ValueError('Choose either a saved receipt or your share of its split bill, not both.')
        cases.add(current['case_id'])
        category = item.get('category')
        if category not in CATEGORIES:
            raise ValueError('Select a category for every expense.')
        claimed = amount(item.get('claimed_amount'))
        if claimed > Decimal(current['available_amount']):
            raise ValueError('Claimed amount cannot exceed the source receipt or your settled share.')
        vat = amount(item.get('vat_amount', '0'), positive=False)
        if vat > claimed:
            raise ValueError('VAT amount cannot exceed the claimed amount.')
        paid_by = item.get('paid_by')
        if paid_by not in ('employee', 'company'):
            raise ValueError('Select who paid for every expense.')
        expense_date = clean(item.get('expense_date', ''), 10, required=True)
        try:
            if date.fromisoformat(expense_date).isoformat() != expense_date:
                raise ValueError()
        except ValueError:
            raise ValueError('Invalid expense date.') from None
        row = {**current, 'category': category, 'claimed_amount': str(claimed), 'vat_amount': str(vat),
               'paid_by': paid_by, 'expense_date': expense_date,
               'business_reason': clean(item.get('business_reason', ''), 500),
               'invoice_number': clean(item.get('invoice_number', ''), 120),
               'notes': clean(item.get('notes', ''), 500)}
        rows.append(row)
        currency = current['currency']
        totals[currency] = totals.get(currency, Decimal('0')) + claimed
        if paid_by == 'employee':
            reimburse[currency] = reimburse.get(currency, Decimal('0')) + claimed
    if details['advance_amount'] != '0.00':
        currency = details['advance_currency']
        if currency not in reimburse:
            raise ValueError('Advance currency must match an employee-paid expense currency.')
    snapshot = {'title': title, 'employee': identity[0].name, 'company': format_company(profile),
                'details': details, 'items': rows, 'totals': {k: str(v) for k, v in totals.items()},
                'employee_paid': {k: str(v) for k, v in reimburse.items()},
                'reimbursement': {k: str(v - (Decimal(details['advance_amount']) if k == details['advance_currency'] else 0))
                                  for k, v in reimburse.items()}}
    report = ExpenseReport(user_id=uid, company_id=profile.id, title=title,
                           snapshot_json=json.dumps(snapshot, ensure_ascii=False))
    db.add(report); db.commit(); db.refresh(report)
    return {'id': report.id}


@router.get('/reports')
def reports(identity=Depends(current), db=Depends(get_db)):
    return [{'id': r.id, 'title': r.title, 'created_at': r.created_at.isoformat()}
            for r in db.query(ExpenseReport).filter_by(user_id=identity[0].id)
            .order_by(ExpenseReport.created_at.desc(), ExpenseReport.id.desc()).limit(100).all()]


@router.get('/reports/{report_id}')
def report(report_id: int, identity=Depends(current), db=Depends(get_db)):
    row = db.query(ExpenseReport).filter_by(id=report_id, user_id=identity[0].id).first()
    if not row:
        raise HTTPException(404, 'Expense report not found.')
    return {'id': row.id, 'created_at': row.created_at.isoformat(), **json.loads(row.snapshot_json)}
