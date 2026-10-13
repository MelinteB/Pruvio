"""Dated ECB or BNR reference rates and explicitly marked manual overrides."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from threading import Lock
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from app.services import ecb_fx

BNR_URL = 'https://curs.bnr.ro/nbrfxrates.xml'
_lock = Lock()
_cached = None
_expires = None
MONEY = Decimal('0.01')


def bnr_rates():
    """BNR quotes RON per multiplier units of each foreign currency."""
    global _cached, _expires
    with _lock:
        now = datetime.now(timezone.utc)
        if _cached and _expires and now < _expires:
            return _cached
        try:
            with urlopen(Request(BNR_URL, headers={'User-Agent': 'Pruvs/7.1.8'}), timeout=6) as response:
                content = response.read(65537)
            if len(content) > 65536:
                raise ValueError('BNR response is too large.')
            root = ElementTree.fromstring(content)
            days = [node for node in root.iter() if node.tag.rsplit('}',1)[-1] == 'Cube' and 'date' in node.attrib]
            if len(days) != 1:
                raise ValueError('BNR publication date is missing.')
            published = date.fromisoformat(days[0].attrib['date'])
            if not date.today() - timedelta(days=5) <= published <= date.today():
                raise ValueError('BNR reference rates are out of date.')
            values = {'RON': Decimal('1')}
            for entry in days[0]:
                if entry.tag.rsplit('}',1)[-1] != 'Rate':
                    continue
                code = entry.attrib.get('currency')
                multiplier = Decimal(entry.attrib.get('multiplier','1'))
                value = Decimal((entry.text or '').strip()) / multiplier
                if code and len(code) == 3 and value.is_finite() and value > 0 and multiplier > 0:
                    values[code] = value
            if len(values) < 5:
                raise ValueError('BNR reference rates are incomplete.')
            _cached = (published.isoformat(), values)
            _expires = now + timedelta(hours=1)
            return _cached
        except Exception as exc:
            raise ValueError('BNR reference rates are unavailable. Choose a manual rate or try later.') from exc


def reference_quote(value, base, target, provider='bnr', manual_rate=None, *, table=None):
    base, target = str(base).upper(), str(target).upper()
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal('1000000000'):
            raise ValueError()
    except (ValueError, InvalidOperation):
        raise ValueError('Enter a valid amount.') from None
    if provider not in ('bnr','ecb') or len(base) != 3 or len(target) != 3 or not base.isalpha() or not target.isalpha():
        raise ValueError('Choose a valid provider and currency pair.')
    if base == target:
        if manual_rate not in (None,'','1','1.0','1.00'):
            raise ValueError('The rate for the same currency must be 1.')
        cross, published, url = Decimal('1'), None, None
        manual = False
    elif manual_rate is not None and str(manual_rate).strip():
        try:
            cross = Decimal(str(manual_rate))
            if not cross.is_finite() or not Decimal('0.00000001') <= cross <= Decimal('1000000') or cross.as_tuple().exponent < -8:
                raise ValueError()
        except (ValueError,InvalidOperation):
            raise ValueError('Enter a positive manual rate with at most eight decimal places.') from None
        published, url, manual = None, None, True
    else:
        published, values = table or (bnr_rates() if provider == 'bnr' else ecb_fx.rates())
        if base not in values or target not in values:
            raise ValueError('The selected provider does not publish this currency pair. Use a clearly marked manual rate.')
        cross = values[base] / values[target] if provider == 'bnr' else values[target] / values[base]
        url = BNR_URL if provider == 'bnr' else ecb_fx.FEED
        manual = False
    return {'base':base,'target':target,'original':str(amount),
            'converted':str((amount*cross).quantize(MONEY,rounding=ROUND_HALF_UP)),
            'rate':str(cross.quantize(Decimal('0.00000001'),rounding=ROUND_HALF_UP)),
            'date':published,'provider':provider,'manual':manual,
            'source':'Manual rate entered by the user' if manual else ('BNR' if provider=='bnr' else 'ECB'),
            'source_url':url}
