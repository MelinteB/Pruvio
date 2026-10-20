"""Strong semantic duplicate key; never match on merchant/total alone.

If a date AND receipt-specific document number are not confirmed, use the
preexisting exact-file/perceptual image duplicate checks only. This avoids
blocking someone who buys the same food at the same merchant every day.
"""
import hashlib,re,unicodedata

def normalize(value):
    text=unicodedata.normalize('NFKD',str(value or '').lower())
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in text if not unicodedata.combining(c))).strip()

def extract_from_text(text):
    text=str(text or '')
    date=re.search(r'\b(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.](?:20)?\d{2})\b',text)
    number=re.search(r'(?im)^\s*(?:bon(?:\s+fiscal)?|receipt|ticket|chitanta|factura)(?:\s+(?:nr|no|number|#))?\s*[:.#-]?\s*([a-z]?\d{3,12}(?:[-/]\d{1,6})?)\b',text)
    return {'date':date.group(0) if date else None,'number':number.group(1) if number else None}

def identity_hash(merchant,total,currency,date,number):
    from decimal import Decimal,InvalidOperation
    if not (normalize(merchant) and date and number and currency):return None
    try:money=str(Decimal(str(total)).quantize(Decimal('0.01')))
    except (InvalidOperation,TypeError):return None
    parts=[normalize(merchant),money,str(currency).upper().strip(),re.sub(r'[^0-9]','',str(date)),normalize(number)]
    if not parts[-1] or len(parts[-2])<6:return None
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()
