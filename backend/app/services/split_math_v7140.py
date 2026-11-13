"""Pure money allocation primitives for a proposed Core v7.1.40 integration.

NOT wired to Pruvs Core sessions, database, API, or React. All values are
integer minor units. Callers must validate ownership and persist atomically.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Mapping, Sequence


def to_minor(value: str, *, exponent: int = 2) -> int:
    """Convert a decimal currency value to integer minor units, without rounding."""
    if not 0 <= exponent <= 3:
        raise ValueError('Unsupported currency exponent')
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Invalid amount') from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError('Amount must be finite and nonnegative')
    minor = amount * (Decimal(10) ** exponent)
    if minor != minor.to_integral_value():
        raise ValueError('Amount contains more decimal places than the currency supports')
    return int(minor)


def equal_minor(total: int, participant_ids: Sequence[str]) -> dict[str, int]:
    """Deterministically allocate exact minor units to distinct participant IDs."""
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise ValueError('total must be nonnegative integer minor units')
    if not participant_ids or len(set(participant_ids)) != len(participant_ids) or any(not x for x in participant_ids):
        raise ValueError('Distinct, non-empty participants required')
    # Stable tie-break prevents different participant ordering from changing shares.
    ordered = sorted(participant_ids)
    base, remainder = divmod(total, len(ordered))
    result = {pid: base + (1 if n < remainder else 0) for n, pid in enumerate(ordered)}
    assert sum(result.values()) == total
    return result


def proportional_minor(total: int, weights: Mapping[str, str]) -> dict[str, int]:
    """Largest-remainder apportionment, exact cents and no floating point drift.

    Weights are decimal strings, not floats. Ties break by participant ID.
    """
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise ValueError('total must be nonnegative integer minor units')
    if not weights or any(not pid for pid in weights):
        raise ValueError('At least one non-empty participant required')
    fractions = {}
    for pid, value in weights.items():
        try:
            frac = Fraction(Decimal(value))
        except (InvalidOperation, ValueError, OverflowError) as exc:
            raise ValueError('Invalid participant weight') from exc
        if frac <= 0:
            raise ValueError('All included participants must have positive weights')
        fractions[pid] = frac
    denominator = sum(fractions.values())
    floor = {pid: (total * weight // denominator) for pid, weight in fractions.items()}
    leftover = total - sum(floor.values())
    ranking = sorted(fractions, key=lambda pid: (-(total * fractions[pid] / denominator - floor[pid]), pid))
    for pid in ranking[:leftover]:
        floor[pid] += 1
    assert sum(floor.values()) == total
    return dict(sorted(floor.items()))


def shared_item_minor(quantity: str, unit_amount_minor: int, participant_ids: Sequence[str]) -> dict[str, int]:
    """Physical quantity determines total price, not max sharing participants."""
    try:
        count = Decimal(quantity)
    except InvalidOperation as exc:
        raise ValueError('Invalid quantity') from exc
    if not count.is_finite() or count < 0 or unit_amount_minor < 0:
        raise ValueError('Invalid quantity or item price')
    total = count * unit_amount_minor
    if total != total.to_integral_value():
        raise ValueError('Fractional quantity requires explicit rounded line total from receipt')
    return equal_minor(int(total), participant_ids)
