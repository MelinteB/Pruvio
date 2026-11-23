"""Country-specific registration phone length and E.164 checks."""
import pytest

from app.services.phone_numbers import country_dialing_options, normalize_signup_phone


@pytest.mark.parametrize(("country", "input_value", "expected"), [
    ("RO", "0722 123 456", "+40722123456"),
    ("RO", "722123456", "+40722123456"),
    ("RO", "+40 722 123 456", "+40722123456"),
    ("RO", "0040 722 123 456", "+40722123456"),
    ("US", "(415) 555-2671", "+14155552671"),
    ("GB", "07911 123456", "+447911123456"),
    ("GB", "+44 7911 123456", "+447911123456"),
    ("FR", "06 12 34 56 78", "+33612345678"),
])
def test_normalizes_different_country_numbers(country, input_value, expected):
    assert normalize_signup_phone(input_value, country) == expected


@pytest.mark.parametrize(("country", "input_value"), [
    ("RO", "0722 123"),
    ("RO", "0722 1234 567 99999"),
    ("US", "415 555 2"),
    ("GB", "07911 123"),
    ("FR", "06 12 34"),
    ("RO", ""),
    ("RO", "+44 7911 123456"),
    ("RO", "ABC123456"),
    ("RO", "+40722123456 ext 2"),
    ("ZZ", "0722123456"),
])
def test_rejects_wrong_lengths_prefixes_and_countries(country, input_value):
    with pytest.raises(ValueError):
        normalize_signup_phone(input_value, country)


def test_country_metadata_is_available_for_country_picker():
    countries = {row["country"]: row for row in country_dialing_options()}
    assert len(countries) > 190
    assert countries["RO"]["calling_code"] == "+40"
    assert 9 in countries["RO"]["possible_lengths"]
    assert countries["US"]["calling_code"] == "+1"
    assert 10 in countries["US"]["possible_lengths"]
    assert countries["GB"]["calling_code"] == "+44"
