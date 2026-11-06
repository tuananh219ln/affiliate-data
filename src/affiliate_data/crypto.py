"""Encrypts saved login sessions (browser cookies) at rest. They are never sent back by the API."""

from cryptography.fernet import Fernet

from . import config


class MissingKey(RuntimeError):
    pass


def _fernet() -> Fernet:
    if not config.SECRET_KEY:
        raise MissingKey("SECRET_KEY is not set; see .env.example")
    return Fernet(config.SECRET_KEY.encode())


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode()).decode()
