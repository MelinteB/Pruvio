"""Country-aware phone number checks for Pruvs Core registration and sharing.

The selected ISO country is authoritative for national-number input. Validate
using Google's libphonenumber metadata (via python-phonenumbers), never a fixed
'10 digits' rule. Persist only canonical E.164 phone numbers.
"""
from functools import lru_cache
import re

import phonenumbers
from phonenumbers import PhoneMetadata, PhoneNumberFormat, NumberParseException

_ALLOWED_INPUT = re.compile(r"^\+?[0-9\s().-]+$")


def normalize_signup_phone(phone_number: str, country: str = "RO") -> str:
    region = str(country or "").strip().upper()
    if region not in phonenumbers.SUPPORTED_REGIONS:
        raise ValueError("Choose a supported phone country.")
    raw = str(phone_number or "").strip()
    if not raw:
        raise ValueError("Phone number is required for sharing.")
    if len(raw) > 48 or not _ALLOWED_INPUT.fullmatch(raw):
        raise ValueError("Enter a phone number using digits and standard separators.")
    # Accept pasting an E.164 number or an international 00 prefix as well as
    # the national number typed after selecting a calling code.
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    try:
        parsed = phonenumbers.parse(raw, region)
    except NumberParseException:
        raise ValueError("Enter a valid phone number for the selected country.") from None

    expected_calling_code = phonenumbers.country_code_for_region(region)
    if parsed.country_code != expected_calling_code:
        raise ValueError("The phone prefix does not match the selected country.")
    if parsed.extension:
        raise ValueError("Phone extensions cannot be used for sharing.")
    # A number suitable for sharing must be complete (not a short local-only
    # dial string). Some countries treat six- or seven-digit local numbers as
    # "possible"; require the country's full mobile national length as well.
    metadata = PhoneMetadata.metadata_for_region(region)
    mobile_lengths = {
        n for n in (metadata.mobile.possible_length if metadata and metadata.mobile else ())
        if n > 0
    }
    general_lengths = {
        n for n in (metadata.general_desc.possible_length if metadata and metadata.general_desc else ())
        if n > 0
    }
    permitted_lengths = mobile_lengths or general_lengths
    national_length = len(phonenumbers.national_significant_number(parsed))
    if (phonenumbers.is_possible_number_with_reason(parsed) != phonenumbers.ValidationResult.IS_POSSIBLE
            or (permitted_lengths and national_length not in permitted_lengths)):
        raise ValueError("Phone number length is invalid for the selected country.")
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


@lru_cache(maxsize=1)
def country_dialing_options() -> tuple[dict, ...]:
    options = []
    for region in sorted(phonenumbers.SUPPORTED_REGIONS):
        calling_code = phonenumbers.country_code_for_region(region)
        if not calling_code:
            continue
        metadata = PhoneMetadata.metadata_for_region(region)
        mobile_lengths = [
            length for length in (metadata.mobile.possible_length if metadata and metadata.mobile else ())
            if length > 0
        ]
        general_lengths = [
            length for length in (metadata.general_desc.possible_length if metadata and metadata.general_desc else ())
            if length > 0
        ]
        possible_lengths = sorted(set(mobile_lengths or general_lengths))
        options.append({
            "country": region,
            "calling_code": f"+{calling_code}",
            "national_prefix": metadata.national_prefix if metadata and metadata.national_prefix and metadata.national_prefix.isdigit() else "",
            "possible_lengths": possible_lengths,
        })
    return tuple(options)
