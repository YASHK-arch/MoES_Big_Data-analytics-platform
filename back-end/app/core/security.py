"""Security, password hashing, and JWT token management utilities."""

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.core.config import settings

# JWT configuration
ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 60 * 24  # 24 hours

# In-memory revocation blocklist and single-use SSE ticket nonce cache
REVOKED_TOKENS: set[str] = set()
SSE_TICKETS: dict[str, dict[str, Any]] = {}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash of a plain text password."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def create_access_token(
    subject: str,
    role: str = "OPERATOR",
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=DEFAULT_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }
    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def revoke_token(token: str) -> None:
    """Add a JWT token to the revocation blocklist."""
    REVOKED_TOKENS.add(token.strip())


def is_token_revoked(token: str) -> bool:
    """Return True if the token has been explicitly invalidated."""
    return token.strip() in REVOKED_TOKENS


def create_sse_ticket(subject: str, role: str = "OPERATOR") -> str:
    """Generate a single-use, short-lived (30-second) ticket nonce for secure SSE handshakes."""
    ticket = uuid.uuid4().hex
    now = time.monotonic()
    SSE_TICKETS[ticket] = {
        "subject": subject,
        "role": role,
        "expires_at": now + 30.0,
    }
    return ticket


def redeem_sse_ticket(ticket: str) -> Optional[dict[str, Any]]:
    """Redeem and atomically invalidate a single-use SSE ticket nonce."""
    if not ticket:
        return None
    ticket_clean = ticket.strip()
    now = time.monotonic()

    # Clean expired tickets
    expired_keys = [k for k, v in SSE_TICKETS.items() if v["expires_at"] < now]
    for k in expired_keys:
        SSE_TICKETS.pop(k, None)

    record = SSE_TICKETS.pop(ticket_clean, None)
    if record and record["expires_at"] >= now:
        return record
    return None


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token against algorithm, expiry, and revocation blocklist."""
    if is_token_revoked(token):
        raise ValueError("Authentication token has been revoked / logged out.")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid authentication token")
