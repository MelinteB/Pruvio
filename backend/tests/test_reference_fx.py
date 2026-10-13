from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app.services import reference_fx


def test_bnr_multiplier_and_cross_currency():
    feed = (f'<DataSet><Body><Cube date="{date.today().isoformat()}">'
            '<Rate currency="EUR">5.0000</Rate><Rate currency="HUF" multiplier="100">1.2500</Rate>'
            '<Rate currency="USD">4.0000</Rate><Rate currency="GBP">6.0000</Rate>'
            '</Cube></Body></DataSet>').encode()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, length): return feed
    with patch.object(reference_fx, 'urlopen', return_value=Response()):
        reference_fx._cached = reference_fx._expires = None
        result = reference_fx.reference_quote('100', 'HUF', 'EUR')
    assert result['converted'] == '0.25'
    assert result['rate'] == '0.00250000'
    assert result['date'] == date.today().isoformat()
    assert result['provider'] == 'bnr'


def test_manual_rate_is_marked_and_never_fetches_feed():
    with patch.object(reference_fx, 'bnr_rates', side_effect=AssertionError('feed used')):
        result = reference_fx.reference_quote('22.50', 'USD', 'RON', manual_rate='4.5')
    assert Decimal(result['converted']) == Decimal('101.25')
    assert result['manual'] is True
    assert result['date'] is None
    assert result['source_url'] is None
