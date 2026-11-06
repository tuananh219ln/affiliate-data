"""Encrypts saved login sessions (browser cookies) at rest, and the web sign-in cookie."""

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


def decrypt(encrypted: str, ttl: int | None = None) -> str:
    """Raises InvalidToken when the token was changed, made with another key, or is older than `ttl` s."""
    return _fernet().decrypt(encrypted.encode(), ttl=ttl).decode()
