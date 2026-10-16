"""Personal expense reports. The server verifies ownership and freezes source values."""
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.db.database import get_db
from app.models.case import Case
from app.models.document import Document
from app.models.expense import ExpenseCompany, ExpenseReport, ExpenseTripProfile
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
    db.query(ExpenseTripProfile).filter_by(user_id=identity[0].id,company_id=company_id).delete()
    db.delete(row); db.commit()
    return {'ok': True}


def format_trip(row):
    return {'id':row.id,'company_id':row.company_id,'name':row.name,
            'defaults':json.loads(row.defaults_json),'enabled_fields':json.loads(row.enabled_json),
            'required_fields':json.loads(row.required_json)}


def trip_input(db,uid,body):
    if not isinstance(body,dict):raise ValueError('Invalid trip profile.')
    company_id=body.get('company_id')
    if type(company_id) is not int or not db.query(ExpenseCompany).filter_by(id=company_id,user_id=uid).first():
        raise ValueError('Choose one of your company profiles.')
    name=clean(body.get('name',''),180,required=True)
    defaults=body.get('defaults',{})
    enabled=body.get('enabled_fields',list(DETAILS))
    required=body.get('required_fields',['purpose'])
    if not isinstance(defaults,dict) or not isinstance(enabled,list) or not isinstance(required,list):
        raise ValueError('Invalid trip fields.')
    if any(not isinstance(k,str) or k not in DETAILS for k in defaults) or any(not isinstance(k,str) or k not in DETAILS for k in enabled+required):
        raise ValueError('Unknown trip field.')
    if len(set(enabled))!=len(enabled) or len(set(required))!=len(required) or 'purpose' not in enabled or 'purpose' not in required or not set(required)<=set(enabled):
        raise ValueError('Business purpose must be required, and every required field must be enabled.')
    return {'company_id':company_id,'name':name,
            'defaults_json':json.dumps({k:clean(v,DETAILS[k]) for k,v in defaults.items()},ensure_ascii=False),
            'enabled_json':json.dumps(enabled),'required_json':json.dumps(required)}


@router.get('/trip-profiles')
def trip_profiles(identity=Depends(current),db=Depends(get_db)):
    return [format_trip(p) for p in db.query(ExpenseTripProfile).filter_by(user_id=identity[0].id).order_by(ExpenseTripProfile.name).all()]


@router.post('/trip-profiles')
def create_trip_profile(body:dict,identity=Depends(current),db=Depends(get_db)):
    uid=identity[0].id
    if db.query(ExpenseTripProfile).filter_by(user_id=uid).count()>=100:raise ValueError('Maximum 100 trip profiles.')
    row=ExpenseTripProfile(user_id=uid,**trip_input(db,uid,body));db.add(row);db.commit();db.refresh(row)
    return format_trip(row)


@router.put('/trip-profiles/{profile_id}')
def update_trip_profile(profile_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    row=db.query(ExpenseTripProfile).filter_by(id=profile_id,user_id=identity[0].id).first()
    if not row:raise HTTPException(404,'Trip profile not found.')
    for key,value in trip_input(db,identity[0].id,body).items():setattr(row,key,value)
    row.updated_at=datetime.utcnow();db.commit();return format_trip(row)


@router.delete('/trip-profiles/{profile_id}')
def remove_trip_profile(profile_id:int,identity=Depends(current),db=Depends(get_db)):
    row=db.query(ExpenseTripProfile).filter_by(id=profile_id,user_id=identity[0].id).first()
    if not row:raise HTTPException(404,'Trip profile not found.')
    db.delete(row);db.commit();return {'ok':True}


def period(value,label):
    if value is None or value=='':return None
    try:
        parsed=date.fromisoformat(value)
        if parsed.isoformat()!=value:raise ValueError()
        return parsed
    except ValueError:raise HTTPException(400,f'Invalid {label}; use YYYY-MM-DD.') from None


def source(db, uid, kind, source_id, *, include_unavailable=False):
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
                'available_amount': str(amount(receipt['receipt_total'])), 'eligible': True, 'reason': ''}
    if kind == 'bill':
        from app.react_app.receipt_labels import receipt_label
        session = db.get(SplitBillSession, source_id)
        participant = db.query(SplitBillParticipant).filter_by(session_id=source_id, user_id=uid, status='joined').first()
        if not session or not participant:
            raise ValueError('Select only split bills in which you participated.')
        settled = session.status in ('settled', 'closed')
        if not settled and not include_unavailable:
            raise ValueError('Settle the split bill before claiming your share.')
        summary = get_split_bill_session_summary(db, session, ensure_translations=False)
        own = next((p for p in summary['participants'] if p['participant_id'] == participant.id), None)
        currency = summary['currency']
        if not own or not re.fullmatch('[A-Z]{3}', currency or ''):
            raise ValueError('This split bill has no confirmed currency or participant share.')
        name = receipt_label(db, session.case_id)
        personal_share = amount(own.get('total') or 0, positive=False)
        if personal_share == 0 and not include_unavailable:
            raise ValueError('No share was assigned to your account in this split.')
        return {'kind': kind, 'source_id': session.id, 'case_id': session.case_id,
                'source_url': f'/bill/{session.token}', 'document_id': None,
                'filename': f'Split · {name}', 'date': (session.settled_at or session.created_at).date().isoformat(),
                'merchant': f'Split · {name}', 'currency': currency,
                'available_amount': str(personal_share), 'eligible': settled and personal_share > 0,
                'reason': ('Settle this split before claiming your share.' if not settled else
                           'No share was assigned to your account.' if personal_share == 0 else ''),
                'split_status': session.status}
    raise ValueError('Unknown expense source.')


@router.get('/sources/tree')
def source_tree(offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
                from_date: str | None = None, to_date: str | None = None,
                identity=Depends(current), db=Depends(get_db)):
    """Group owned receipts and joined splits by the underlying receipt."""
    from app.react_app.receipt_labels import receipt_label

    uid = identity[0].id
    start,end=period(from_date,'start date'),period(to_date,'end date')
    if start and end and end<start:raise HTTPException(400,'End date must be on or after start date.')
    def in_period(when):
        day=when.date()
        return (start is None or day>=start) and (end is None or day<=end)
    cases = db.query(Case).filter(Case.user_id == uid,
                                  Case.status.notin_(('processing', 'processing_failed'))).all()
    sessions = (db.query(SplitBillSession)
                .join(SplitBillParticipant, SplitBillParticipant.session_id == SplitBillSession.id)
                .filter(SplitBillParticipant.user_id == uid, SplitBillParticipant.status == 'joined')
                .distinct().all())
    removed = {(row.kind, row.source_id) for row in db.query(HistoryVisibility)
               .filter_by(user_id=uid, state='removed').all()}
    grouped = {}
    for case in cases:
        if ('receipt', case.id) not in removed and in_period(case.created_at):
            grouped[case.id] = {'date': case.created_at, 'receipt_id': case.id, 'session_ids': []}
    for session in sessions:
        if ('bill', session.id) in removed or not in_period(session.settled_at or session.created_at):
            continue
        group = grouped.setdefault(session.case_id, {'date': session.created_at,
                                                      'receipt_id': None, 'session_ids': []})
        if group['receipt_id'] is None:
            group['date'] = min(group['date'], session.settled_at or session.created_at)
        group['session_ids'].append(session.id)
    ordered = sorted(grouped.items(), key=lambda item: (item[1]['date'], item[0]))
    rows = []
    for case_id, group in ordered[offset:offset + limit]:
        receipt = None
        if group['receipt_id'] is not None:
            try:
                receipt = source(db, uid, 'receipt', group['receipt_id'])
            except ValueError:
                pass
        bills = []
        for session_id in sorted(group['session_ids']):
            try:
                bills.append(source(db, uid, 'bill', session_id, include_unavailable=True))
            except ValueError:
                continue
        if receipt or bills:
            rows.append({'case_id': case_id, 'title': (receipt['merchant'] if receipt else None) or receipt_label(db, case_id),
                         'receipt': receipt, 'bills': bills})
    return {'rows': rows, 'total': len(ordered), 'has_more': offset + limit < len(ordered)}


@router.get('/sources')
def sources(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
            kind: str | None = Query(None, pattern='^(receipt|bill)$'),
            identity=Depends(current), db=Depends(get_db)):
    uid = identity[0].id
    receipts = [(c.created_at, 'receipt', c.id) for c in db.query(Case).filter(Case.user_id == uid,
                Case.status.notin_(('processing', 'processing_failed'))).all()]
    bills = [(s.settled_at or s.created_at, 'bill', s.id) for s in db.query(SplitBillSession)
             .join(SplitBillParticipant, SplitBillParticipant.session_id == SplitBillSession.id)
             .filter(SplitBillParticipant.user_id == uid, SplitBillParticipant.status == 'joined').distinct().all()]
    choices = sorted(receipts if kind == 'receipt' else bills if kind == 'bill' else receipts + bills,
                     key=lambda entry: (entry[0], entry[2]))
    removed = {(row.kind, row.source_id) for row in db.query(HistoryVisibility)
               .filter_by(user_id=uid, state='removed').all()}
    choices = [choice for choice in choices if (choice[1], choice[2]) not in removed]
    rows = []
    for _, kind, source_id in choices[offset:offset + limit]:
        try:
            rows.append(source(db, uid, kind, source_id, include_unavailable=True))
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
def create_report(request: Request, body: dict, identity=Depends(current), db=Depends(get_db)):
    uid = identity[0].id
    profile = db.query(ExpenseCompany).filter_by(id=body.get('company_id'), user_id=uid).first()
    if not profile:
        raise ValueError('Choose a company profile from your account.')
    title = clean(body.get('title', ''), 180, required=True)
    details = details_input(body.get('details'))
    report_currency = str(body.get('report_currency') or 'RON').upper()
    if not re.fullmatch('[A-Z]{3}', report_currency):
        raise ValueError('Choose a valid report reference currency.')
    trip=None
    if body.get('trip_profile_id') is not None:
        trip=db.query(ExpenseTripProfile).filter_by(id=body['trip_profile_id'],user_id=uid,company_id=profile.id).first()
        if not trip:raise ValueError('Choose a trip profile for the selected company.')
        for field in json.loads(trip.required_json):
            if not details.get(field):raise ValueError(f'Required trip field is missing: {field}.')
    raw = body.get('items')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 1000:
        raise ValueError('Choose between 1 and 1000 saved receipts or settled split shares.')
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
            raise ValueError('Choose the full receipt or one personal split share for each receipt, not both.')
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
    rows.sort(key=lambda item: (item['expense_date'], item['case_id'], item['source_id']))
    from app.services.reference_fx import reference_quote, bnr_rates
    from app.services.ecb_fx import rates as ecb_rates
    fx_settings = body.get('fx_settings') or {}
    if not isinstance(fx_settings, dict):
        raise ValueError('Invalid currency setup.')
    provider = fx_settings.get('provider') or 'bnr'
    if provider not in ('bnr', 'ecb'):
        raise ValueError('Choose BNR or ECB as the reference source.')
    overrides = fx_settings.get('overrides') or {}
    if not isinstance(overrides, dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in overrides.items()):
        raise ValueError('Invalid manual rates.')
    used = {row['currency'] for row in rows if row['currency'] != report_currency}
    if set(overrides) - used:
        raise ValueError('A manual rate does not match a selected expense currency.')
    table = (bnr_rates() if provider == 'bnr' else ecb_rates()) if used-set(overrides) else None
    converted = Decimal('0')
    for row in rows:
        conversion = reference_quote(row['claimed_amount'], row['currency'], report_currency,
                                     provider, overrides.get(row['currency']), table=table)
        row['converted_amount'] = conversion['converted']
        row['fx_rate'] = conversion['rate']
        row['fx_date'] = conversion['date']
        row['fx_manual'] = conversion['manual']
        row['fx_provider'] = conversion['provider']
        converted += Decimal(conversion['converted'])
    snapshot = {'title': title, 'employee': identity[0].name, 'company': format_company(profile),
                'trip_profile':trip.name if trip else None,
                'details': details, 'items': rows, 'totals': {k: str(v) for k, v in totals.items()},
                'reference_conversion': {'currency': report_currency, 'total': str(converted), 'provider':provider,
                                         'manual':bool(overrides), 'overrides':overrides,
                                         'date': table[0] if table else None,
                                         'source': ('BNR' if provider=='bnr' else 'ECB') if table else ('Manual rates' if overrides else 'Same currency'),
                                         'source_url': ('https://curs.bnr.ro/nbrfxrates.xml' if provider=='bnr' else 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml') if table else None},
                'employee_paid': {k: str(v) for k, v in reimburse.items()},
                'reimbursement': {k: str(v - (Decimal(details['advance_amount']) if k == details['advance_currency'] else 0))
                                  for k, v in reimburse.items()}}
    report = ExpenseReport(user_id=uid, company_id=profile.id, title=title,
                           snapshot_json=json.dumps(snapshot, ensure_ascii=False))
    from app.react_app.commerce import account_plan
    from app.react_app.plan_catalog import plan_catalog
    from app.react_app.usage import reserve, finish
    token=reserve(uid,'expense_report',plan_catalog(db),account_plan(db,uid),
                  use_credits=request.headers.get('X-Pruvs-Use-Credits','false').lower()=='true')
    try:
        db.add(report); db.commit(); db.refresh(report)
    except Exception:
        db.rollback()
        finish(token,False)
        raise
    finish(token,True)
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
    snapshot = json.loads(row.snapshot_json)
    snapshot['items'].sort(key=lambda item: (item.get('expense_date',''), item.get('case_id',0), item.get('source_id',0)))
    return {'id': row.id, 'created_at': row.created_at.isoformat(), **snapshot}


@router.get('/reports/{report_id}/pdf')
def report_pdf(report_id: int, identity=Depends(current), db=Depends(get_db)):
    row = db.query(ExpenseReport).filter_by(id=report_id, user_id=identity[0].id).first()
    if not row:
        raise HTTPException(404, 'Expense report not found.')
    from app.react_app.expense_pdf import render_expense_pdf
    try:
        snapshot = json.loads(row.snapshot_json)
        snapshot['items'].sort(key=lambda item: (item.get('expense_date',''), item.get('case_id',0), item.get('source_id',0)))
        output = render_expense_pdf(db, identity[0].id, row.id, snapshot, row.created_at)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return StreamingResponse(output, media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="pruvs-expense-{row.id}.pdf"',
        'Cache-Control': 'private, no-store',
    })
