import hashlib
import hmac
import secrets

ITERATIONS = 310_000
MIN_PASSWORD_LENGTH = 8


def validate_password(password: str) -> None:
    value = password or ""
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must contain at least {MIN_PASSWORD_LENGTH} characters.")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations_text, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)
