"""Project allocation primitives: exact-cent conservation and no implicit FX."""
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP


def to_minor(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError
        cents = amount * 100
        if cents != cents.to_integral_value():
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Enter a valid amount with at most two decimal places.')
    if cents > 100000000000: raise ValueError('Amount exceeds project limit.')
    return int(cents)


def allocate_minor(total, mode, entries):
    """Entries [{user_id, value}]. Equal/percent/share/amount; deterministic largest remainders."""
    if type(total) is not int or total <= 0:raise ValueError('Amount must be positive.')
    if not isinstance(entries,list) or not 1 <= len(entries) <= 100:raise ValueError('Select 1–100 participants.')
    ids=[];weights=[]
    for entry in entries:
        if not isinstance(entry,dict) or type(entry.get('user_id')) is not int or entry['user_id'] < 1:
            raise ValueError('Invalid project participant.')
        if entry['user_id'] in ids:raise ValueError('Participant appears more than once.')
        ids.append(entry['user_id'])
        if mode == 'equal':weight=Decimal(1)
        else:
            try:weight=Decimal(str(entry.get('value')))
            except (InvalidOperation,TypeError):raise ValueError('Invalid allocation value.')
            if not weight.is_finite() or weight < 0:raise ValueError('Allocation cannot be negative.')
        weights.append(weight)
    if mode == 'amount':
        cents=[to_minor(str(w)) for w in weights]
        if sum(cents) != total:raise ValueError('Allocated amounts must equal the full bill.')
        return dict(zip(ids,cents))
    if mode not in ('equal','percent','share'):raise ValueError('Choose Equal, Percent, Amount or Share.')
    total_weight=sum(weights)
    if not total_weight:raise ValueError('Select a positive allocation.')
    if mode == 'percent' and abs(total_weight - Decimal(100)) > Decimal('0.00001'):
        raise ValueError('Percent allocations must sum to 100%.')
    exact=[Decimal(total)*w/total_weight for w in weights]
    floors=[int(x.to_integral_value(rounding=ROUND_FLOOR)) for x in exact]
    missing=total-sum(floors)
    remainder=sorted(range(len(ids)),key=lambda i:(-(exact[i]-floors[i]),ids[i]))
    for i in remainder[:missing]:floors[i]+=1
    assert sum(floors)==total
    return dict(zip(ids,floors))
