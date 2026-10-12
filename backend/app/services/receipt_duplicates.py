"""Avoid reprocessing the same user's exact or nearly identical image upload."""
import base64
import hashlib
import io
from pathlib import Path

from PIL import Image, ImageOps, ImageStat

from app.models.case import Case
from app.models.document import Document
from app.models.receipt_fingerprint import ReceiptFingerprint


def fingerprint(data):
    sha = hashlib.sha256(data).hexdigest()
    try:
        with Image.open(io.BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened).convert('L')
            if ImageStat.Stat(image).stddev[0] < 8:
                return sha, None
            ratio = image.width / image.height
            pixels = image.resize((32, 32), Image.Resampling.LANCZOS).tobytes()
            signature = f'{ratio:.5f}:' + base64.b64encode(pixels).decode('ascii')
            return sha, signature
    except (OSError, ValueError, Image.DecompressionBombError):
        # Exact-file detection still applies to PDFs and non-decodable images.
        return sha, None


def same_image(first, second):
    if not first or not second:
        return False
    try:
        ratio_a, encoded_a = first.split(':', 1)
        ratio_b, encoded_b = second.split(':', 1)
        if abs(float(ratio_a) / float(ratio_b) - 1) > .015:
            return False
        a, b = base64.b64decode(encoded_a), base64.b64decode(encoded_b)
        return len(a) == len(b) == 1024 and sum(abs(x - y) for x, y in zip(a, b)) / 1024 <= 3
    except (ValueError, ZeroDivisionError):
        return False


def find_duplicate(db, user_id, sha, image_signature):
    stored = (db.query(ReceiptFingerprint, Case)
              .join(Case, Case.id == ReceiptFingerprint.case_id)
              .filter(ReceiptFingerprint.user_id == user_id, Case.status != 'processing_failed').all())
    for record, case in stored:
        if record.sha256 == sha or same_image(record.image_signature, image_signature):
            return case.id
    # Older receipts predate persistent fingerprints. Check their surviving files.
    legacy = (db.query(Document, Case)
              .join(Case, Case.id == Document.case_id)
              .filter(Case.user_id == user_id, Case.status != 'processing_failed',
                      Document.document_type == 'receipt').all())
    known = {case.id for _, case in stored}
    for document, case in legacy:
        if case.id in known:
            continue
        path = Path(document.path)
        if not path.is_file():
            continue
        try:
            old_sha, old_image = fingerprint(path.read_bytes())
        except OSError:
            continue
        if old_sha == sha or same_image(old_image, image_signature):
            return case.id
    return None
