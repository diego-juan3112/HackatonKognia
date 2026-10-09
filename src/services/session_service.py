"""Anonymous signed session (R-28, docs/08 section 3). No database, no personal data.

Token = base64url(claims) "." base64url(HMAC-SHA256(claims)). Claims: a random
session id, the locale and the expiry. Verification is constant-time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime


class InvalidSession(Exception):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class SessionClaims:
    sid: str
    locale: str
    exp: int


class SessionService:
    def __init__(self, signing_key: str, ttl_hours: int = 2) -> None:
        if len(signing_key) < 16:
            raise ValueError("SESSION_SIGNING_KEY is missing or too short (use 32 random bytes)")
        self._key = signing_key.encode()
        self._ttl = ttl_hours * 3600

    def issue(self, locale: str = "es-CO") -> tuple[str, str]:
        exp = int(time.time()) + self._ttl
        claims = _b64(json.dumps({"sid": secrets.token_urlsafe(12), "loc": locale, "exp": exp},
                                 separators=(",", ":")).encode())
        sig = _b64(hmac.new(self._key, claims.encode(), hashlib.sha256).digest())
        return f"{claims}.{sig}", datetime.fromtimestamp(exp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def verify(self, token: str | None) -> SessionClaims:
        if not token or token.count(".") != 1:
            raise InvalidSession("missing or malformed token")
        claims_b64, sig_b64 = token.split(".")
        expected = hmac.new(self._key, claims_b64.encode(), hashlib.sha256).digest()
        try:
            if not hmac.compare_digest(expected, _unb64(sig_b64)):
                raise InvalidSession("bad signature")
            data = json.loads(_unb64(claims_b64))
        except (ValueError, json.JSONDecodeError) as exc:
            raise InvalidSession("malformed token") from exc
        if int(data.get("exp", 0)) < time.time():
            raise InvalidSession("expired")
        return SessionClaims(sid=str(data["sid"]), locale=str(data.get("loc", "es-CO")), exp=int(data["exp"]))


class RateLimiter:
    """Sliding one-minute window per key (session id and client IP), in memory (R-28)."""

    def __init__(self, per_minute: int) -> None:
        self._limit = per_minute
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> float | None:
        """Return None if allowed, or the seconds to wait (for ``Retry-After``)."""
        now = time.monotonic()
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self._limit:
            return max(1.0, 60 - (now - q[0]))
        q.append(now)
        if len(self._hits) > 10_000:  # bound memory on a long-lived instance
            for k in [k for k, v in self._hits.items() if not v][:5000]:
                self._hits.pop(k, None)
        return None
