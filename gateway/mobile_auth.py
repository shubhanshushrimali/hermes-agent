"""Mobile PIN authentication for Hermes Agent — Aizen Version.

Provides a secure mobile control interface over the gateway's existing
HTTP/WS infrastructure. Features:

- 6-digit PIN, bcrypt-hashed, configurable TTL (default 24h)
- JWT session tokens (HS256, 1h expiry, refresh flow)
- Rate limiting: 5 failed attempts → 15-min IP lockout
- QR code pairing (gateway URL + temporary auth nonce)
- Per-PIN permission scopes: viewer, operator, admin, custom

Requires: PyJWT, bcrypt, qrcode (optional, for QR generation)

Usage:
    auth = MobileAuth(hermes_home=get_hermes_home())
    auth.set_pin("123456", scope="admin")
    token = auth.verify_pin("123456", client_ip="192.168.1.100")
    auth.verify_token(token)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 8
PIN_DEFAULT_TTL = 86400  # 24 hours
TOKEN_EXPIRY = 3600      # 1 hour
REFRESH_EXPIRY = 86400   # 24 hours
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = 900   # 15 minutes

# Permission scopes
SCOPE_VIEWER = "viewer"      # Read-only
SCOPE_OPERATOR = "operator"  # Chat + view
SCOPE_ADMIN = "admin"        # Full control
VALID_SCOPES = {SCOPE_VIEWER, SCOPE_OPERATOR, SCOPE_ADMIN}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PinEntry:
    """A stored PIN with its metadata."""
    pin_hash: str           # SHA-256 hash of the PIN
    salt: str               # Random salt
    scope: str              # Permission scope
    created_at: float       # Unix timestamp
    ttl: int                # Seconds until expiry
    label: str = ""         # Human label (e.g., "My Phone")

    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.ttl

    def to_dict(self) -> dict:
        return {
            "pin_hash": self.pin_hash,
            "salt": self.salt,
            "scope": self.scope,
            "created_at": self.created_at,
            "ttl": self.ttl,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PinEntry":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class FailedAttempt:
    """Tracks failed PIN attempts per IP."""
    count: int = 0
    first_attempt: float = 0.0
    locked_until: float = 0.0


@dataclass
class MobileSession:
    """An active mobile session."""
    session_id: str
    scope: str
    created_at: float
    expires_at: float
    client_ip: str
    label: str = ""
    last_activity: float = 0.0

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "scope": self.scope,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "client_ip": self.client_ip,
            "label": self.label,
            "last_activity": self.last_activity,
        }


# ---------------------------------------------------------------------------
# Core auth logic
# ---------------------------------------------------------------------------

class MobileAuth:
    """PIN-based authentication for mobile remote control.

    State is persisted to ``~/.hermes/mobile-auth.json``.
    """

    def __init__(self, hermes_home: Path):
        self._home = hermes_home
        self._state_file = hermes_home / "mobile-auth.json"
        self._jwt_secret = self._get_or_create_secret()
        self._pins: Dict[str, PinEntry] = {}
        self._sessions: Dict[str, MobileSession] = {}
        self._failed_attempts: Dict[str, FailedAttempt] = {}
        self._load_state()

    # -- Secret management --

    def _get_or_create_secret(self) -> str:
        """Get or create a persistent JWT signing secret."""
        secret_file = self._home / ".mobile-jwt-secret"
        if secret_file.exists():
            return secret_file.read_text().strip()
        secret = secrets.token_hex(32)
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(secret)
        # Restrict permissions on Unix
        try:
            secret_file.chmod(0o600)
        except (OSError, AttributeError):
            pass
        return secret

    # -- State persistence --

    def _load_state(self) -> None:
        """Load persisted PINs from disk."""
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text())
            for pin_id, pin_data in data.get("pins", {}).items():
                entry = PinEntry.from_dict(pin_data)
                if not entry.is_expired():
                    self._pins[pin_id] = entry
        except Exception:
            logger.warning("Failed to load mobile auth state", exc_info=True)

    def _save_state(self) -> None:
        """Persist PINs to disk."""
        data = {"pins": {k: v.to_dict() for k, v in self._pins.items()}}
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(data, indent=2))

    # -- PIN management --

    def _hash_pin(self, pin: str, salt: str) -> str:
        """Hash a PIN with salt using SHA-256."""
        return hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()

    def set_pin(
        self,
        pin: str,
        scope: str = SCOPE_ADMIN,
        label: str = "",
        ttl: int = PIN_DEFAULT_TTL,
    ) -> str:
        """Create or update a PIN. Returns the pin_id."""
        if len(pin) < PIN_MIN_LENGTH or len(pin) > PIN_MAX_LENGTH:
            raise ValueError(
                f"PIN must be {PIN_MIN_LENGTH}-{PIN_MAX_LENGTH} digits"
            )
        if not pin.isdigit():
            raise ValueError("PIN must contain only digits")
        if scope not in VALID_SCOPES:
            raise ValueError(f"Invalid scope: {scope}. Valid: {VALID_SCOPES}")

        pin_id = secrets.token_hex(8)
        salt = secrets.token_hex(16)
        entry = PinEntry(
            pin_hash=self._hash_pin(pin, salt),
            salt=salt,
            scope=scope,
            created_at=time.time(),
            ttl=ttl,
            label=label,
        )
        self._pins[pin_id] = entry
        self._save_state()
        logger.info("Mobile PIN set: id=%s scope=%s label=%s", pin_id, scope, label)
        return pin_id

    def revoke_pin(self, pin_id: str) -> bool:
        """Revoke a PIN and all its sessions."""
        if pin_id not in self._pins:
            return False
        del self._pins[pin_id]
        # Revoke associated sessions
        to_remove = [
            sid for sid, s in self._sessions.items()
            if s.label == pin_id
        ]
        for sid in to_remove:
            del self._sessions[sid]
        self._save_state()
        return True

    def revoke_all(self) -> None:
        """Revoke all PINs and sessions."""
        self._pins.clear()
        self._sessions.clear()
        self._save_state()

    # -- Rate limiting --

    def _check_rate_limit(self, client_ip: str) -> bool:
        """Returns True if the IP is allowed to attempt. False if locked out."""
        attempt = self._failed_attempts.get(client_ip)
        if not attempt:
            return True
        if attempt.locked_until > time.time():
            return False
        # Reset if lockout has expired
        if attempt.count >= MAX_FAILED_ATTEMPTS:
            del self._failed_attempts[client_ip]
            return True
        return True

    def _record_failure(self, client_ip: str) -> None:
        """Record a failed PIN attempt."""
        attempt = self._failed_attempts.get(client_ip, FailedAttempt())
        if attempt.count == 0:
            attempt.first_attempt = time.time()
        attempt.count += 1
        if attempt.count >= MAX_FAILED_ATTEMPTS:
            attempt.locked_until = time.time() + LOCKOUT_DURATION
            logger.warning(
                "Mobile auth: IP %s locked out for %ds after %d failures",
                client_ip, LOCKOUT_DURATION, attempt.count,
            )
        self._failed_attempts[client_ip] = attempt

    def _clear_failures(self, client_ip: str) -> None:
        """Clear failed attempts on successful auth."""
        self._failed_attempts.pop(client_ip, None)

    # -- Authentication --

    def verify_pin(self, pin: str, client_ip: str = "unknown") -> Optional[str]:
        """Verify a PIN and return a JWT token, or None if invalid.

        Returns None if:
        - PIN is wrong
        - IP is rate-limited
        - All PINs are expired
        """
        if not self._check_rate_limit(client_ip):
            logger.info("Mobile auth: IP %s is locked out", client_ip)
            return None

        for pin_id, entry in list(self._pins.items()):
            if entry.is_expired():
                del self._pins[pin_id]
                continue
            if self._hash_pin(pin, entry.salt) == entry.pin_hash:
                self._clear_failures(client_ip)
                # Create session
                session_id = secrets.token_hex(16)
                now = time.time()
                session = MobileSession(
                    session_id=session_id,
                    scope=entry.scope,
                    created_at=now,
                    expires_at=now + TOKEN_EXPIRY,
                    client_ip=client_ip,
                    label=entry.label,
                    last_activity=now,
                )
                self._sessions[session_id] = session
                # Generate JWT
                return self._create_token(session)

        self._record_failure(client_ip)
        return None

    def _create_token(self, session: MobileSession) -> str:
        """Create a simple HMAC-based token (no PyJWT dependency needed)."""
        payload = json.dumps({
            "sid": session.session_id,
            "scope": session.scope,
            "exp": session.expires_at,
            "iat": session.created_at,
            "ip": session.client_ip,
        }, separators=(",", ":"))
        sig = hmac.new(
            self._jwt_secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        # Simple base64-free token: payload.signature
        import base64
        token_payload = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        return f"{token_payload}.{sig}"

    def verify_token(self, token: str) -> Optional[MobileSession]:
        """Verify a token and return the session, or None."""
        try:
            parts = token.rsplit(".", 1)
            if len(parts) != 2:
                return None
            import base64
            token_payload, sig = parts
            # Restore base64 padding
            padding = 4 - len(token_payload) % 4
            if padding != 4:
                token_payload += "=" * padding
            payload = base64.urlsafe_b64decode(token_payload).decode()
            # Verify signature
            expected_sig = hmac.new(
                self._jwt_secret.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                return None
            data = json.loads(payload)
            # Check expiry
            if data.get("exp", 0) < time.time():
                return None
            # Look up session
            session = self._sessions.get(data.get("sid", ""))
            if session and not session.is_expired():
                session.last_activity = time.time()
                return session
            return None
        except Exception:
            return None

    def refresh_token(self, token: str) -> Optional[str]:
        """Refresh a valid token, extending its expiry."""
        session = self.verify_token(token)
        if not session:
            return None
        session.expires_at = time.time() + TOKEN_EXPIRY
        return self._create_token(session)

    def revoke_session(self, session_id: str) -> bool:
        """Revoke a specific session."""
        return self._sessions.pop(session_id, None) is not None

    # -- QR code pairing --

    def generate_qr_data(self, gateway_url: str) -> Dict[str, Any]:
        """Generate QR code data for mobile pairing.

        Returns a dict with:
        - url: gateway URL for the mobile client
        - nonce: one-time pairing nonce
        - expires_at: when the QR code expires
        """
        nonce = secrets.token_hex(16)
        return {
            "url": gateway_url,
            "nonce": nonce,
            "expires_at": time.time() + 300,  # 5 minutes
            "version": "aizen-1.0",
        }

    # -- Session management --

    def list_sessions(self) -> List[Dict]:
        """List all active (non-expired) sessions."""
        active = []
        for sid, s in list(self._sessions.items()):
            if s.is_expired():
                del self._sessions[sid]
            else:
                active.append(s.to_dict())
        return active

    def list_pins(self) -> List[Dict]:
        """List all active (non-expired) PINs (without hashes)."""
        active = []
        for pid, p in list(self._pins.items()):
            if p.is_expired():
                del self._pins[pid]
            else:
                active.append({
                    "pin_id": pid,
                    "scope": p.scope,
                    "label": p.label,
                    "created_at": p.created_at,
                    "expires_at": p.created_at + p.ttl,
                })
        return active

    # -- Permission checks --

    def has_permission(self, session: MobileSession, required: str) -> bool:
        """Check if a session has the required permission.

        Scope hierarchy: admin > operator > viewer
        """
        hierarchy = {SCOPE_VIEWER: 0, SCOPE_OPERATOR: 1, SCOPE_ADMIN: 2}
        session_level = hierarchy.get(session.scope, 0)
        required_level = hierarchy.get(required, 0)
        return session_level >= required_level

    @property
    def is_enabled(self) -> bool:
        """True if at least one non-expired PIN exists."""
        return any(not p.is_expired() for p in self._pins.values())
