"""Exact-cent, per-currency group netting of existing split obligations.

Read-only *suggestions*, not payments. Nonmember and guest debts remain visible
on their original bills and are never silently included in the group settlement plan.
"""
from collections import defaultdict


def settlement_plan(obligations, accepted_user_ids, names):
    """obligations = [{payer_id, payee_id, currency, cents}]. No FX or rounding."""
    accepted = set(accepted_user_ids)
    ledgers = defaultdict(lambda: defaultdict(int))
    excluded = defaultdict(int)
    for item in obligations:
        payer, payee = item['payer_id'], item['payee_id']
        curr, cents = item['currency'], item['cents']
        if type(cents) is not int or cents < 0 or not isinstance(curr, str) or not curr:
            raise ValueError('Invalid group obligation')
        if payer == payee or cents == 0: continue
        if payer not in accepted or payee not in accepted:
            excluded[curr] += cents
            continue
        ledgers[curr][payer] -= cents
        ledgers[curr][payee] += cents
    result = []
    balances = []
    for currency in sorted(ledgers):
        positions = ledgers[currency]
        # Stable ordering ensures repeatable summaries across sessions.
        debtors = [[uid, -v] for uid,v in sorted(positions.items()) if v < 0]
        creditors = [[uid, v] for uid,v in sorted(positions.items()) if v > 0]
        assert sum(x[1] for x in debtors) == sum(x[1] for x in creditors)
        for uid, cents in sorted(positions.items()):
            balances.append({'user_id':uid,'name':names.get(uid,'Member'),
                             'currency':currency,'net_minor':cents,'net':cents/100})
        i = j = 0
        while i < len(debtors) and j < len(creditors):
            cents=min(debtors[i][1],creditors[j][1])
            result.append({'from_user_id':debtors[i][0],'from_name':names.get(debtors[i][0],'Member'),
                           'to_user_id':creditors[j][0],'to_name':names.get(creditors[j][0],'Member'),
                           'currency':currency,'amount_minor':cents,'amount':cents/100})
            debtors[i][1]-=cents;creditors[j][1]-=cents
            if debtors[i][1]==0:i+=1
            if creditors[j][1]==0:j+=1
    return {'suggested_settlements':result,'net_balances':balances,
            'excluded_nonmember_minor':dict(excluded),
            'settlements_are_advisory':True}
