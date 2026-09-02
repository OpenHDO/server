"""Persistent users, password hashes, and revocable browser sessions."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3
from threading import RLock
import time
from uuid import uuid4


USER_ROLES = {"admin", "operator", "viewer"}
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32
_SCRYPT_MAXMEM = 64 * 1024 * 1024


class AuthError(Exception):
    """Base class for authentication store errors."""


class AuthConflict(AuthError):
    """The requested user operation conflicts with current auth state."""


@dataclass(frozen=True)
class UserRecord:
    id: str
    username: str
    role: str
    active: bool
    created_at: str


class AuthStore:
    """Small SQLite-backed auth repository owned by the server runtime."""

    def __init__(self, database_path: str) -> None:
        if database_path == ":memory:":
            connection_target = database_path
            uri = False
        else:
            path = Path(database_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            connection_target = str(path)
            uri = False
        self._connection = sqlite3.connect(connection_target, check_same_thread=False, uri=uri)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'operator', 'viewer')),
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf_hash TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                """
            )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def has_users(self) -> bool:
        with self._lock:
            row = self._connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            return row is not None

    def ensure_bootstrap_admin(self, username: str | None, password: str | None) -> None:
        if not username or not password:
            return
        with self._lock:
            if self._connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None:
                return
            self._insert_user(username, password, "admin")
            self._connection.commit()

    def authenticate(self, username: str, password: str) -> UserRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT id, username, password_hash, role, active, created_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            _verify_password(password, _DUMMY_PASSWORD_HASH)
            return None
        if not _verify_password(password, row["password_hash"]) or not row["active"]:
            return None
        return _user_from_row(row)

    def create_session(self, user: UserRecord, *, ttl_seconds: int) -> tuple[str, str]:
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        now = int(time.time())
        with self._lock:
            self._purge_expired(now)
            self._connection.execute(
                "INSERT INTO sessions(token_hash, user_id, csrf_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
                (_token_hash(session_token), user.id, _token_hash(csrf_token), now + ttl_seconds, now),
            )
            self._connection.commit()
        return session_token, csrf_token

    def session(self, session_token: str | None) -> UserRecord | None:
        if not session_token:
            return None
        now = int(time.time())
        with self._lock:
            self._purge_expired(now)
            row = self._connection.execute(
                """
                SELECT u.id, u.username, u.role, u.active, u.created_at
                FROM sessions AS s JOIN users AS u ON u.id = s.user_id
                WHERE s.token_hash = ?
                """,
                (_token_hash(session_token),),
            ).fetchone()
            if row is None or not row["active"]:
                return None
        return _user_from_row(row)

    def csrf_matches(self, session_token: str | None, csrf_token: str | None) -> bool:
        if not session_token or not csrf_token:
            return False
        with self._lock:
            row = self._connection.execute(
                "SELECT csrf_hash, expires_at FROM sessions WHERE token_hash = ?",
                (_token_hash(session_token),),
            ).fetchone()
        return row is not None and row["expires_at"] > int(time.time()) and hmac.compare_digest(
            row["csrf_hash"], _token_hash(csrf_token)
        )

    def revoke_session(self, session_token: str | None) -> None:
        if not session_token:
            return
        with self._lock:
            self._connection.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(session_token),))
            self._connection.commit()

    def list_users(self) -> list[UserRecord]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, username, role, active, created_at FROM users ORDER BY username COLLATE NOCASE"
            ).fetchall()
        return [_user_from_row(row) for row in rows]

    def create_user(self, username: str, password: str, role: str) -> UserRecord:
        if role not in USER_ROLES:
            raise AuthConflict("unsupported user role")
        with self._lock:
            try:
                user_id = self._insert_user(username, password, role)
                self._connection.commit()
            except sqlite3.IntegrityError as error:
                raise AuthConflict("username is already registered") from error
            row = self._connection.execute(
                "SELECT id, username, role, active, created_at FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return _user_from_row(row)

    def update_user(
        self,
        user_id: str,
        *,
        role: str | None = None,
        active: bool | None = None,
        password: str | None = None,
    ) -> UserRecord:
        if role is not None and role not in USER_ROLES:
            raise AuthConflict("unsupported user role")
        with self._lock:
            current = self._connection.execute(
                "SELECT id, username, role, active, created_at FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if current is None:
                raise AuthConflict("user does not exist")
            next_role = role or current["role"]
            next_active = current["active"] if active is None else int(active)
            if current["role"] == "admin" and current["active"] and (next_role != "admin" or not next_active):
                admins = self._connection.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
                ).fetchone()[0]
                if admins <= 1:
                    raise AuthConflict("the last active admin cannot be disabled or demoted")
            updates = ["role = ?", "active = ?"]
            values: list[object] = [next_role, next_active]
            if password is not None:
                updates.append("password_hash = ?")
                values.append(_hash_password(password))
            values.append(user_id)
            self._connection.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
            self._connection.commit()
            row = self._connection.execute(
                "SELECT id, username, role, active, created_at FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return _user_from_row(row)

    def _insert_user(self, username: str, password: str, role: str) -> str:
        user_id = str(uuid4())
        self._connection.execute(
            "INSERT INTO users(id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (user_id, username, _hash_password(password), role, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )
        return user_id

    def _purge_expired(self, now: int) -> None:
        self._connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        self._connection.commit()


def _user_from_row(row: sqlite3.Row) -> UserRecord:
    return UserRecord(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        active=bool(row["active"]),
        created_at=row["created_at"],
    )


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _derive_password(password: str, salt: bytes, *, n: int = _SCRYPT_N, r: int = _SCRYPT_R, p: int = _SCRYPT_P) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=_KEY_BYTES,
        maxmem=_SCRYPT_MAXMEM,
    )


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive_password(password, salt)
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii")
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${encode(salt)}${encode(digest)}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_value, digest_value = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
        actual = _derive_password(password, salt, n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


_DUMMY_PASSWORD_HASH = _hash_password("openhdo-invalid-password")
