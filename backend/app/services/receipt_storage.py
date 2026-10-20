"""Private storage for paid plans, and transient OCR-only files for Free."""
import os
from pathlib import Path
from urllib.parse import urlparse
from fastapi import HTTPException

REQUIRED = ('PRUVS_S3_ENDPOINT','PRUVS_S3_BUCKET','PRUVS_S3_ACCESS_KEY_ID','PRUVS_S3_SECRET_ACCESS_KEY')

def ready():
    return all(os.getenv(key,'').strip() for key in REQUIRED)

def _client():
    if not ready():
        raise HTTPException(503, 'Secure cloud receipt storage is not configured. Contact Pruvs support before uploading on a paid plan.')
    try:
        import boto3
    except ImportError as exc:
        raise HTTPException(503,'Cloud storage dependency is missing.') from exc
    endpoint=os.environ['PRUVS_S3_ENDPOINT']
    if urlparse(endpoint).scheme!='https':
        raise HTTPException(503,'Cloud storage endpoint must use HTTPS.')
    return boto3.client('s3', endpoint_url=endpoint, region_name=os.getenv('PRUVS_S3_REGION','auto'),
        aws_access_key_id=os.environ['PRUVS_S3_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['PRUVS_S3_SECRET_ACCESS_KEY'])

def is_cloud(doc):
    return bool(doc and str(doc.path or '').startswith('s3://'))

def store_paid(doc, case, user_id, data):
    bucket=os.environ['PRUVS_S3_BUCKET']
    key=f'users/{int(user_id)}/receipts/{int(case.id)}/{doc.stored_filename}'
    # Encryption at rest is enforced by the private bucket provider (R2/S3);
    # don't force an optional SSE request header unsupported by some endpoints.
    _client().put_object(Bucket=bucket,Key=key,Body=data,ContentType=doc.mime_type or 'application/octet-stream')
    return f's3://{bucket}/{key}'

def read_paid(doc):
    if not is_cloud(doc):return None
    bucket,key=str(doc.path)[5:].split('/',1)
    try:
        return _client().get_object(Bucket=bucket,Key=key)['Body'].read()
    except Exception as exc:
        raise HTTPException(503,'The secure receipt copy could not be retrieved.') from exc

def delete_paid(doc):
    if is_cloud(doc):
        bucket,key=str(doc.path)[5:].split('/',1)
        _client().delete_object(Bucket=bucket,Key=key)

def erase_temporary(doc):
    if not doc or not doc.path or str(doc.path).startswith(('s3://','local://')):return
    path=Path(doc.path)
    from app.services.document_service import upload_root, LEGACY_UPLOAD_ROOT
    if any(path.resolve().is_relative_to(root.resolve()) for root in (upload_root(),LEGACY_UPLOAD_ROOT)):
        path.unlink(missing_ok=True)

def finalize_original(db,case,doc,user_id,plan):
    path=Path(doc.path)
    if plan=='free':
        doc.path=f'local://users/{user_id}/receipts/{case.id}'
        db.commit()
        erase_temporary_path(path)
        return 'local'
    data=path.read_bytes()
    new_path=store_paid(doc,case,user_id,data)
    doc.path=new_path
    db.commit()
    erase_temporary_path(path)
    return 'cloud'

def erase_temporary_path(path):
    from app.services.document_service import upload_root, LEGACY_UPLOAD_ROOT
    if any(path.resolve().is_relative_to(root.resolve()) for root in (upload_root(),LEGACY_UPLOAD_ROOT)):
        path.unlink(missing_ok=True)
