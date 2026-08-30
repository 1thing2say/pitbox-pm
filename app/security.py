"""Passwords, sessions, and the dependency that guards every API route.

PASSWORD HASHING
----------------
Uses scrypt from Python's own hashlib -- no new dependency. scrypt is a
memory-hard KDF, so it resists GPU cracking in a way a plain SHA never can.
The cost parameters are stored alongside each hash, so they can be raised in a
few years without invalidating anyone's existing password.

Deliberately NOT bcrypt/passlib: that is two more packages to keep alive for a
team that hands this over every year, and passlib in particular has a history
of breaking against new bcrypt releases.

SESSIONS
--------
Server-side, in the sessions table. A signed stateless cookie would avoid the
lookup, but could not be revoked -- and "this person graduated, cut their
access now" is a thing that actually happens here. Only the hash of the token
is stored; the token itself lives solely in the user's cookie.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .config import settings
from .database import get_db
from .models import Member, Session, utcnow

COOKIE_NAME = "pitbox_session"

# scrypt cost. n=2**14 with r=8 needs 128*n*r = 16 MB and takes ~100 ms, which
# is the usual interactive-login target: unnoticeable to a person, punishing to
# anyone working through a leaked password list.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_MAXMEM = 64 * 1024 * 1024


# --- password hashing --------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN, maxmem=_SCRYPT_MAXMEM,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check. Returns False for members who have no password set."""
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_hex, key_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(key_hex) // 2, maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        # A malformed hash must fail closed, never raise into the request.
        return False
    return hmac.compare_digest(candidate, bytes.fromhex(key_hex))


# --- brute-force throttle ----------------------------------------------------
# Deliberately simple: an in-process counter, so it resets on restart and does
# not span multiple workers. scrypt already makes guessing expensive; this just
# stops someone hammering one account from a script. If you ever run more than
# one worker, move this to the database or put a rate limit at the proxy.

_FAILS: dict[str, tuple[int, float]] = {}
_MAX_FAILS = 8
_LOCKOUT_SECONDS = 300


def throttle_check(key: str) -> int:
    """Seconds the caller must wait, or 0 if they may try now."""
    count, until = _FAILS.get(key, (0, 0.0))
    if count >= _MAX_FAILS and time.monotonic() < until:
        return int(until - time.monotonic()) + 1
    return 0


def throttle_fail(key: str) -> None:
    count, _ = _FAILS.get(key, (0, 0.0))
    count += 1
    _FAILS[key] = (count, time.monotonic() + _LOCKOUT_SECONDS)


def throttle_reset(key: str) -> None:
    _FAILS.pop(key, None)


# --- sessions ----------------------------------------------------------------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: DbSession, member: Member, user_agent: str | None = None) -> str:
    """Start a session and return the raw token to put in the cookie."""
    token = secrets.token_urlsafe(32)
    db.add(Session(
        token_hash=_hash_token(token),
        member_id=member.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_days),
        user_agent=(user_agent or "")[:300] or None,
    ))
    member.last_login_at = utcnow()
    db.commit()
    return token


def destroy_session(db: DbSession, token: str) -> None:
    row = db.scalar(select(Session).where(Session.token_hash == _hash_token(token)))
    if row is not None:
        db.delete(row)
        db.commit()


def purge_expired_sessions(db: DbSession) -> int:
    now = datetime.now(timezone.utc)
    stale = list(db.scalars(select(Session).where(Session.expires_at < now)))
    for row in stale:
        db.delete(row)
    if stale:
        db.commit()
    return len(stale)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,          # JavaScript cannot read it, so XSS cannot steal it
        samesite="lax",         # blocks cross-site POST/PATCH/DELETE, i.e. CSRF
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


# --- request dependencies ----------------------------------------------------

def current_member_optional(request: Request, db: DbSession = Depends(get_db)) -> Member | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    row = db.scalar(select(Session).where(Session.token_hash == _hash_token(token)))
    if row is None:
        return None

    # SQLite hands back naive datetimes even for timezone=True columns, so
    # compare in UTC explicitly rather than trusting tzinfo to be present.
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        return None

    member = db.get(Member, row.member_id)
    # Deactivating someone cuts their access on their very next request.
    if member is None or not member.is_active:
        return None
    return member


def require_member(member: Member | None = Depends(current_member_optional)) -> Member:
    if member is None:
        raise HTTPException(401, "Not signed in.")
    return member


def require_admin(member: Member = Depends(require_member)) -> Member:
    if not member.is_admin:
        raise HTTPException(403, "That action needs an admin account.")
    return member
