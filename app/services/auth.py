"""Authentication service: password hashing (bcrypt), email validation, and JWT session handling."""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import bcrypt
import jwt

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
MIN_PASSWORD_LENGTH = 8

# Common trivially compromised passwords from public breaches
COMMON_BREACHED_PASSWORDS = {
    "password", "password1", "12345678", "123456789", "1234567890",
    "admin123", "admin1234", "welcome1", "welcome123", "letmein123",
    "qwerty1234", "iloveyou123"
}


def hash_password(password: str) -> str:
    """Securely hash a password using bcrypt with 12 salt rounds."""
    if not password:
        raise ValueError("Password cannot be empty")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def is_valid_email(email: str) -> bool:
    """Validate email format."""
    if not email or len(email) > 200:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_password_strength(password: str) -> Optional[str]:
    """Validate password strength rules: length, character variety, and common breached passwords."""
    if not password:
        return "Password is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    if password.lower() in COMMON_BREACHED_PASSWORDS:
        return "This password is too common or known to be compromised in public data breaches. Please choose a stronger, unique password."
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_letter and has_digit):
        return "Password must contain both letters and numbers for enhanced security."
    return None


def create_access_token(
    user_id: int,
    email: str,
    role: str,
    name: str,
    secret_key: str,
    expires_hours: int = 24,
    algorithm: str = "HS256",
) -> Tuple[str, str, datetime]:
    """Create a signed JWT access token. Returns (encoded_jwt, session_id, expires_at)."""
    session_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=expires_hours)

    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "email": email.strip().lower(),
        "role": role,
        "name": name,
        "jti": session_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded = jwt.encode(payload, secret_key, algorithm=algorithm)
    return encoded, session_id, expires_at.replace(tzinfo=None)


def decode_access_token(token: str, secret_key: str, algorithm: str = "HS256") -> dict:
    """Decode and verify a signed JWT token. Raises jwt.PyJWTError on invalid/expired token."""
    return jwt.decode(token, secret_key, algorithms=[algorithm])
