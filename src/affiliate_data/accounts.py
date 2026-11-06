"""Team members: password hashing, sign-in, and the signed-in cookie."""

import base64
import hashlib
import hmac
import os

from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crypto
from .models import User

# scrypt cost (OWASP's minimum); stored with each hash, so it can be raised later. Tests lower SCRYPT_N.
SCRYPT_N, _R, _P = 2**17, 8, 1
_MAXMEM = 256 * 1024 * 1024
MIN_PASSWORD = 10
COOKIE = "affiliate_session"
SESSION_DAYS = 14


class AccountError(ValueError):
    """A refusal to show the person as is (Vietnamese)."""


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=_R, p=_P, maxmem=_MAXMEM)
    return f"scrypt${SCRYPT_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def check_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if kind != "scrypt":
        return False
    actual = hashlib.scrypt(
        password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), maxmem=_MAXMEM
    )
    return hmac.compare_digest(actual, base64.b64decode(digest))


_dummy_hash: str | None = None


def _waste_time(password: str) -> None:
    """Hashes once anyway when the email is unknown, so a wrong email takes as long as a wrong password."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(os.urandom(16).hex())
    check_password(password, _dummy_hash)


def find(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email.strip().lower())).first()


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = find(db, email)
    if user is None or not user.active:
        _waste_time(password)
        return None
    return user if check_password(password, user.password_hash) else None


def check_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AccountError(f"Mật khẩu cần ít nhất {MIN_PASSWORD} ký tự.")


def create(db: Session, email: str, name: str, password: str, is_admin: bool = False) -> User:
    email = email.strip().lower()
    if "@" not in email or len(email) > 200:
        raise AccountError("Email không hợp lệ.")
    check_new_password(password)
    if find(db, email) is not None:
        raise AccountError("Email này đã có tài khoản.")
    user = User(
        email=email,
        name=name.strip()[:100] or email,
        password_hash=hash_password(password),
        is_admin=is_admin,
        active=True,
    )
    db.add(user)
    db.commit()
    return user


def _password_mark(user: User) -> str:
    # The hash's last characters: a new password makes every older token invalid.
    return user.password_hash[-12:]


def session_token(user: User) -> str:
    """An encrypted, timestamped token naming the user and their current password."""
    return crypto.encrypt(f"{user.id}:{_password_mark(user)}")


def user_from_token(db: Session, token: str | None) -> User | None:
    """The signed-in member, or None when the token is missing, altered, older than SESSION_DAYS, made before
    their last password change, or their account is off."""
    if not token:
        return None
    try:
        user_id, mark = crypto.decrypt(token, ttl=SESSION_DAYS * 24 * 3600).split(":", 1)
        user = db.get(User, int(user_id))
    except (InvalidToken, ValueError):
        return None
    if user is None or not user.active or not hmac.compare_digest(mark, _password_mark(user)):
        return None
    return user
