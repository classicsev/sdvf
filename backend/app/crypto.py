from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_fernet = Fernet(settings.field_encryption_key.encode())


def encrypt_field(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_field(token: str) -> Optional[str]:
    try:
        return _fernet.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
