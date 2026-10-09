"""Generate secrets locally; refuses to overwrite. Never add this output to git."""
import argparse
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

p = argparse.ArgumentParser()
p.add_argument('--subject', required=True, help='mailto:your-real-email@example.com')
p.add_argument('--out', default='pruvs-push.private.env')
a = p.parse_args()
if not (a.subject.startswith('mailto:') and '@' in a.subject) or '\n' in a.subject or '\r' in a.subject:
    p.error('Provide a real contact address as mailto:you@example.com')
private = ec.generate_private_key(ec.SECP256R1())
public = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
secret = private.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
def b64(value): return base64.urlsafe_b64encode(value).decode().rstrip('=')
path = Path(a.out).expanduser().resolve()
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(f'PRUVS_PUSH_ENABLED=true\nPRUVS_PUSH_WORKER_ENABLED=true\nPRUVS_VAPID_PUBLIC_KEY={b64(public)}\nPRUVS_VAPID_PRIVATE_KEY={b64(secret)}\nPRUVS_VAPID_SUBJECT={a.subject}\n')
print(f'Private settings saved to {path}. Add them to Render Environment. Do not commit this file.')
