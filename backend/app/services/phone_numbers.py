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
    # Possible-number checks are metadata-backed length checks, deliberately
    # avoiding over-restricting new allocations with strict prefix lists.
    if not phonenumbers.is_possible_number(parsed):
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
        possible_lengths = sorted({
            length
            for desc in (
                metadata.general_desc,
                metadata.mobile,
                metadata.fixed_line,
            )
            for length in (desc.possible_length if desc else ())
            if length > 0
        }) if metadata else []
        options.append({
            "country": region,
            "calling_code": f"+{calling_code}",
            "national_prefix": metadata.national_prefix if metadata and metadata.national_prefix and metadata.national_prefix.isdigit() else "",
            "possible_lengths": possible_lengths,
        })
    return tuple(options)
