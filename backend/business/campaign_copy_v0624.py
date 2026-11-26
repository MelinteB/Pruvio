"""Keep numerical loyalty conditions out of editable advertising copy."""
import re

# Explicit currency/percentage amounts and qualifying counts. This is a
# deterministic guard, not semantic proof of all possible marketing claims.
RULES = (
    re.compile(r'(?i)(?:\b\d+(?:[.,]\d+)?\s*(?:RON|LEI|EUR|EURO|USD)\b|[€$£]\s*\d|\d+(?:[.,]\d+)?\s*[%€$£])'),
    re.compile(r'(?i)\b\d+\s+(?:(?:qualifying|eligible|verified|confirmed|eligibile|confirmate|verificate)\s+)?(?:purchases?|receipts?|visits?|stamps?|cump[ăa]r[ăa]turi|bonuri|vizite|[șs]tampile)\b'),
)

def validate_campaign_copy(headline, message):
    if any(rule.search((headline or '')+' '+(message or '')) for rule in RULES):
        raise ValueError('Keep numerical reward conditions in the loyalty program, not the campaign headline or message.')
