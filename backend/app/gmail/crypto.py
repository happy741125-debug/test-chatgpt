from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class CredentialEncryptionError(RuntimeError):
    pass


class CredentialCipher:
    def __init__(self, secret: str) -> None:
        if not secret:
            raise CredentialEncryptionError("Credential encryption secret is not configured")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise CredentialEncryptionError("Stored credential cannot be decrypted") from exc
