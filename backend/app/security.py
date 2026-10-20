

"""Device tokens: how they are made, and how they are stored safely."""

import hashlib
import secrets


def new_token() -> str:
    """A long random token for one device, e.g. "kX9_vQ2m..." (43 characters)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """The SHA-256 hash of a token: what the database stores instead of the token itself."""
    return hashlib.sha256(token.encode()).hexdigest()
