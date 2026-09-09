from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 240_000
_ALGO = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """Return a self-describing hash: pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False
