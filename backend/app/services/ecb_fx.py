"""Indicative currency conversions from the ECB's dated EUR reference feed."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from threading import Lock
from urllib.request import Request, urlopen
from xml.etree import ElementTree

FEED = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'
SOURCE = 'European Central Bank euro foreign exchange reference rates'
_lock = Lock()
_cache = None
_expires = None
MONEY = Decimal('0.01')


def rates():
    """Never silently invent or indefinitely reuse a reference rate."""
    global _cache, _expires
    with _lock:
        now = datetime.now(timezone.utc)
        if _cache and _expires and now < _expires:
            return _cache
        try:
            with urlopen(Request(FEED, headers={'User-Agent': 'Pruvs/7.1.7'}), timeout=6) as response:
                content = response.read(65537)
            if len(content) > 65536:
                raise ValueError('ECB response is too large.')
            root = ElementTree.fromstring(content)
            days = [node for node in root.iter() if 'time' in node.attrib]
            if len(days) != 1:
                raise ValueError('ECB publication date is missing.')
            published = date.fromisoformat(days[0].attrib['time'])
            # A weekend or holiday can span several days; older values are not current.
            if not date.today() - timedelta(days=5) <= published <= date.today():
                raise ValueError('ECB reference rates are out of date.')
            parsed = {'EUR': Decimal('1')}
            for item in days[0]:
                currency, rate = item.attrib.get('currency'), item.attrib.get('rate')
                if currency and rate:
                    value = Decimal(rate)
                    if value.is_finite() and value > 0:
                        parsed[currency] = value
            if len(parsed) < 5:
                raise ValueError('ECB reference rates are incomplete.')
            _cache = (published.isoformat(), parsed)
            _expires = now + timedelta(hours=1)
            return _cache
        except Exception as exc:
            raise ValueError('ECB reference rates are unavailable. Try again later; no conversion was estimated.') from exc


def quote(value, base, target, *, table=None):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal('1000000000'):
            raise ValueError()
    except Exception:
        raise ValueError('Enter a valid amount for conversion.') from None
    if not isinstance(base, str) or not isinstance(target, str):
        raise ValueError('Choose valid currency codes.')
    base, target = base.upper(), target.upper()
    if base == target:
        return {'base': base, 'target': target, 'original': str(amount),
                'converted': str(amount.quantize(MONEY, rounding=ROUND_HALF_UP)),
                'rate': '1', 'date': None, 'source': 'Same currency'}
    published, values = table or rates()
    if base not in values or target not in values:
        raise ValueError('The ECB does not publish a reference rate for this currency pair.')
    cross = values[target] / values[base]
    return {'base': base, 'target': target, 'original': str(amount),
            'converted': str((amount * cross).quantize(MONEY, rounding=ROUND_HALF_UP)),
            'rate': str(cross.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)),
            'date': published, 'source': SOURCE, 'source_url': FEED}
