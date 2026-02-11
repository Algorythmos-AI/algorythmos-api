from __future__ import annotations

import hashlib
import hmac
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class SignatureInfo:
    scheme: str
    signature: str
    timestamp: Optional[int]


LEGACY_PREFIX = "sha256="
V1_PREFIX = "v1"


def parse_signature_header(header: Optional[str]) -> Optional[SignatureInfo]:
    """Parse vendor signature header supporting v1 and legacy formats."""
    if not header:
        return None

    value = header.strip()
    if not value:
        return None

    if value.startswith(LEGACY_PREFIX):
        sig = value[len(LEGACY_PREFIX) :].strip()
        if sig:
            return SignatureInfo(scheme="legacy", signature=sig, timestamp=None)
        return None

    if value.startswith(V1_PREFIX + ","):
        parts = value.split(",")
        parsed: Dict[str, str] = {}
        for part in parts:
            if "=" not in part:
                continue
            key, val = part.split("=", 1)
            key = key.strip()
            val = val.strip()
            if key:
                parsed[key] = val
        sig = parsed.get("sig")
        ts_raw = parsed.get("t")
        if not sig:
            return None
        timestamp: Optional[int] = None
        if ts_raw is not None:
            try:
                timestamp = int(ts_raw)
            except ValueError:
                return None
        return SignatureInfo(scheme="v1", signature=sig, timestamp=timestamp)

    return None


def verify_hmac_sha256(
    raw: bytes,
    sig_info: SignatureInfo,
    secret: Optional[str],
    *,
    now: Optional[int] = None,
    replay_window_s: int = 300,
) -> bool:
    """Validate HMAC signatures against the raw payload."""
    if not secret:
        return False

    if now is None:
        now = int(time.time())

    if sig_info.scheme == "v1":
        if sig_info.timestamp is None:
            return False
        if abs(now - sig_info.timestamp) > replay_window_s:
            return False
    elif sig_info.scheme == "legacy":
        # Legacy callers must supply timestamp separately; this is enforced by the caller.
        pass
    else:
        return False

    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_info.signature)


class ReplaySet:
    """Thread-safe TTL set for replay protection."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
        self._store: Dict[str, float] = {}

    def seen_once(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._prune(now)
            if key in self._store:
                return False
            self._store[key] = now
            return True

    def _prune(self, now: float) -> None:
        if not self._store:
            return
        expired = [k for k, ts in self._store.items() if now - ts > self.ttl]
        for key in expired:
            self._store.pop(key, None)


replay_set = ReplaySet()
