"""Usernames may be full names; their comparison key is canonical and unique."""
import secrets
import unicodedata


def normalize_username(value: str) -> str:
    clean = " ".join(unicodedata.normalize("NFKC", value or "").split())
    if not 3 <= len(clean) <= 80:
        raise ValueError("Username must contain 3 to 80 characters.")
    if not any(ch.isalpha() for ch in clean):
        raise ValueError("Username must contain at least one letter.")
    if any(not (ch.isalnum() or ch in " ._-'()") for ch in clean):
        raise ValueError("Use letters, numbers, spaces, dots, hyphens or apostrophes in your username.")
    return clean


def username_key(value: str) -> str:
    return normalize_username(value).casefold()


def default_username() -> str:
    # Legacy/internal account creators still get a unique username.
    return "user-" + secrets.token_hex(12)


def default_username_key(context) -> str:
    return username_key(context.get_current_parameters()["username"])

