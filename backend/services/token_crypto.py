from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from core.config import get_settings


class TokenCipher:
    def __init__(self) -> None:
        settings = get_settings()
        secret_material = settings.token_encryption_key or settings.session_secret
        digest = hashlib.sha256(secret_material.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(fernet_key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")


cipher = TokenCipher()
