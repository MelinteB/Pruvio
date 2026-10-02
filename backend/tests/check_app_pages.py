"""Check full app startup and public pages without external OCR/email services."""
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

# OCR packages are unrelated to page rendering; fail if a smoke check calls one.
def no_external_call(*args, **kwargs):
    raise AssertionError("No external OCR/PDF calls are allowed in this smoke check")

azure_stub = types.ModuleType('app.services.ocr_providers.azure_receipt_provider')
azure_stub.AzureReceiptOCRProvider = type('AzureReceiptOCRProvider', (), {'process_document': no_external_call})
sys.modules[azure_stub.__name__] = azure_stub
pdf_stub = types.ModuleType('pypdf')
pdf_stub.PdfReader = no_external_call
sys.modules['pypdf'] = pdf_stub

with tempfile.TemporaryDirectory(prefix='pruvs-page-check-') as temporary:
    os.environ.update(DATABASE_URL='sqlite:///' + str(Path(temporary) / 'test.db'),
                      PRUVIO_STORAGE_SECRET='local-page-test-only-' + 'x' * 32,
                      OTP_SECRET='local-page-test-only-' + 'y' * 32,
                      PUBLIC_BASE_URL='https://pruvs.io', CANONICAL_REDIRECT_ENABLED='false',
                      DEV_TOTP_ENABLED='false', LOCAL_OCR_ENABLED='false')
    from app.main import app

    with TestClient(app, base_url='https://pruvs.io') as client:
        health = client.get('/health').json()
        assert health['app'] == 'Pruvs Core' and health['version'] == '6.6.0'
        assert health['otp_channels'] == ['email']
        for path in ('/', '/register', '/reset-password', '/terms', '/privacy', '/support'):
            response = client.get(path)
            assert response.status_code == 200, (path, response.status_code)
            assert '/static/pruvs-logo.png' in response.text, path
            assert 'Pruvio' not in response.text, path
            assert '#0756df' in response.text and 'pruvs-192.svg' in response.text
        manifest = client.get('/static/manifest.webmanifest').json()
        assert manifest['name'] == manifest['short_name'] == 'Pruvs'
        for icon in manifest['icons']:
            response = client.get(icon['src'])
            assert response.status_code == 200
            if icon['type'] == 'image/svg+xml':
                svg = ET.fromstring(response.text)
                assert icon['sizes'] == svg.attrib['width'] + 'x' + svg.attrib['height']
        os.environ['CANONICAL_REDIRECT_ENABLED'] = 'true'
        response = client.get('https://pruvio.onrender.com/s/sample-token?lang=ro', follow_redirects=False)
        assert response.status_code == 307
        assert response.headers['location'] == 'https://pruvs.io/s/sample-token?lang=ro'
        assert client.get('https://pruvio.onrender.com/health', follow_redirects=False).status_code == 200

print('PASS: full ASGI startup, public Pruvs pages, manifest/icons, canonical redirect and health routing (OCR/PDF providers stubbed)')
