from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app.services import ecb_fx


def test_cross_rate_and_source_date():
    feed = (f'<Envelope><Cube><Cube time="{date.today().isoformat()}">'
            '<Cube currency="USD" rate="1.25"/><Cube currency="RON" rate="5.00"/>'
            '<Cube currency="GBP" rate="0.80"/><Cube currency="CHF" rate="1.00"/>'
            '</Cube></Cube></Envelope>').encode()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, length): return feed
    with patch.object(ecb_fx, 'urlopen', return_value=Response()):
        ecb_fx._cache = ecb_fx._expires = None
        quote = ecb_fx.quote('12.50', 'USD', 'RON')
    assert Decimal(quote['converted']) == Decimal('50.00')
    assert quote['date'] == date.today().isoformat()
    assert quote['rate'] == '4.00000000'


def test_unpublished_currency_never_gets_an_estimated_rate():
    try:
        ecb_fx.quote('10', 'XXX', 'RON', table=('2026-10-13', {'EUR': Decimal(1), 'RON': Decimal(5)}))
    except ValueError as exc:
        assert 'does not publish' in str(exc)
    else:
        raise AssertionError('Unsupported currency was converted')
