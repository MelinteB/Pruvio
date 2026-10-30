"""Private receipt storage with bounded downloads and guarded cloud transitions.

Cloud/SQL commits cannot be atomic: failure handling compensates a successful
upload when SQL persistence fails. Provider deletion failure is explicitly
reported, rather than suggesting recovery was completed.
"""
import logging
import os
from pathlib import Path
from urllib.parse import urlparse
from fastapi import HTTPException

REQUIRED = ('PRUVS_S3_ENDPOINT','PRUVS_S3_BUCKET','PRUVS_S3_ACCESS_KEY_ID','PRUVS_S3_SECRET_ACCESS_KEY')
MAX_ORIGINAL_BYTES = 10 * 1024 * 1024
logger = logging.getLogger(__name__)


def ready():
    if not all(os.getenv(key, '').strip() for key in REQUIRED):
        return False
    parsed = urlparse(os.environ['PRUVS_S3_ENDPOINT'].strip())
    return parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password


def _client():
    if not ready():
        raise HTTPException(503, 'Secure cloud receipt storage is not configured correctly. Contact Pruvs support.')
    try:
        import boto3
    except ImportError as exc:
        raise HTTPException(503, 'Cloud storage dependency is missing.') from exc
    return boto3.client('s3', endpoint_url=os.environ['PRUVS_S3_ENDPOINT'].strip(),
        region_name=os.getenv('PRUVS_S3_REGION', 'auto'),
        aws_access_key_id=os.environ['PRUVS_S3_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['PRUVS_S3_SECRET_ACCESS_KEY'])


def is_cloud(doc):
    return bool(doc and str(doc.path or '').startswith('s3://'))


def _cloud_location(doc, user_id, case_id):
    # Must match the issuer of the object key; never trust an arbitrary URL from SQL.
    from app.services.account_deletion import validate_cloud_document
    if not validate_cloud_document(doc, user_id, case_id):
        raise HTTPException(409, 'Receipt storage requires support review.')
    return str(doc.path)[5:].split('/', 1)


def store_paid(doc, case, user_id, data):
    if not ready():
        raise HTTPException(503, 'Secure cloud receipt storage is not configured correctly.')
    filename = str(doc.stored_filename or '')
    if (not filename or filename in ('.', '..') or '/' in filename or '\\' in filename
            or any(ord(char) < 32 for char in filename)):
        raise HTTPException(409, 'Invalid receipt storage filename.')
    if not data or len(data) > MAX_ORIGINAL_BYTES:
        raise HTTPException(413, 'Receipt original exceeds the maximum upload size.')
    key = f'users/{int(user_id)}/receipts/{int(case.id)}/{filename}'
    bucket = os.environ['PRUVS_S3_BUCKET'].strip()
    _client().put_object(Bucket=bucket, Key=key, Body=data,
                         ContentType=doc.mime_type or 'application/octet-stream')
    return f's3://{bucket}/{key}'


def read_paid(doc, *, user_id, case_id):
    """Bound memory and validate ownership even if a database path was corrupted."""
    bucket, key = _cloud_location(doc, user_id, case_id)
    body = None
    try:
        result = _client().get_object(Bucket=bucket, Key=key)
        body = result['Body']
        length = result.get('ContentLength')
        if length is not None and int(length) > MAX_ORIGINAL_BYTES:
            raise HTTPException(413, 'Stored receipt exceeds the maximum download size.')
        data = body.read(MAX_ORIGINAL_BYTES + 1)
        if len(data) > MAX_ORIGINAL_BYTES:
            raise HTTPException(413, 'Stored receipt exceeds the maximum download size.')
        return data
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, 'The secure receipt copy could not be retrieved.') from exc
    finally:
        if body is not None:
            try:
                body.close()
            except Exception:
                logger.warning('Cloud receipt stream cleanup failed (no receipt metadata logged)')


def delete_paid(doc):
    if is_cloud(doc):
        bucket, key = str(doc.path)[5:].split('/', 1)
        _client().delete_object(Bucket=bucket, Key=key)


def erase_temporary(doc):
    if not doc or not doc.path or str(doc.path).startswith(('s3://', 'local://')):
        return
    erase_temporary_path(Path(doc.path))


def _cleanup_after_commit(path):
    try:
        erase_temporary_path(path)
    except OSError:
        # SQL has committed. Do not claim the paid upload failed or refund OCR
        # simply because unlink failed; operators can sweep managed temp files.
        logger.warning('Managed receipt temporary file could not be removed after commit')


def finalize_original(db, case, doc, user_id, plan):
    path = Path(doc.path)
    if plan == 'free':
        old_path = doc.path
        doc.path = f'local://users/{int(user_id)}/receipts/{int(case.id)}'
        try:
            db.commit()
        except Exception:
            db.rollback()
            doc.path = old_path
            raise
        _cleanup_after_commit(path)
        return 'local'

    data = path.read_bytes()
    new_path = store_paid(doc, case, user_id, data)
    old_path = doc.path
    doc.path = new_path
    try:
        db.commit()
    except Exception as commit_error:
        db.rollback()
        doc.path = old_path
        # Compensate the successful upload, without hiding provider failures.
        try:
            delete_paid(type('CloudRef', (), {'path': new_path})())
        except Exception as delete_error:
            logger.error('Cloud original requires orphan cleanup after SQL commit failure')
            raise HTTPException(503, 'Receipt persistence failed; storage requires support review.') from delete_error
        raise commit_error
    _cleanup_after_commit(path)
    return 'cloud'


def erase_temporary_path(path):
    from app.services.document_service import upload_root, LEGACY_UPLOAD_ROOT
    resolved = path.resolve()
    for root in (upload_root(), LEGACY_UPLOAD_ROOT):
        if resolved.is_relative_to(root.resolve()):
            path.unlink(missing_ok=True)
            return
