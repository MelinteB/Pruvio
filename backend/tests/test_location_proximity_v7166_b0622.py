from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from business.pilot_v06 import require_receipt_location


STORE = SimpleNamespace(latitude=44.4268, longitude=26.1025)


def test_location_check_allows_nearby_signed_coordinates(monkeypatch):
    monkeypatch.setenv('PRUVS_RECEIPT_LOCATION_CHECK_ENABLED', 'true')
    monkeypatch.setenv('PRUVS_RECEIPT_LOCATION_RADIUS_METERS', '500')
    require_receipt_location({'location': {
        'latitude': 44.4270, 'longitude': 26.1027, 'source': 'manual_test'
    }}, STORE)


def test_location_check_rejects_missing_or_distant_coordinates(monkeypatch):
    monkeypatch.setenv('PRUVS_RECEIPT_LOCATION_CHECK_ENABLED', 'true')
    monkeypatch.setenv('PRUVS_RECEIPT_LOCATION_RADIUS_METERS', '500')
    with pytest.raises(HTTPException, match='location is required'):
        require_receipt_location({}, STORE)
    with pytest.raises(HTTPException, match='within 500 metres'):
        require_receipt_location({'location': {
            'latitude': 44.5000, 'longitude': 26.2000, 'source': 'manual_test'
        }}, STORE)


def test_location_check_is_explicitly_feature_gated(monkeypatch):
    monkeypatch.delenv('PRUVS_RECEIPT_LOCATION_CHECK_ENABLED', raising=False)
    require_receipt_location({}, STORE)
