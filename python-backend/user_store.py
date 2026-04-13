import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
import re


DB_FILENAME = "users.db"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
_DB_LOCK = threading.Lock()


def _db_path(app_root):
    return Path(app_root) / DB_FILENAME


def _connect(app_root):
    path = _db_path(app_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_store(app_root):
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    max_parallel_runs INTEGER NOT NULL DEFAULT 1,
                    max_prompt_chars INTEGER NOT NULL DEFAULT 20000,
                    max_upload_bytes INTEGER NOT NULL DEFAULT 10485760,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_username TEXT,
                    detail TEXT,
                    created_at INTEGER NOT NULL
                );
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "email" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
            if "max_parallel_runs" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN max_parallel_runs INTEGER NOT NULL DEFAULT 1")
            if "max_prompt_chars" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN max_prompt_chars INTEGER NOT NULL DEFAULT 20000")
            if "max_upload_bytes" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN max_upload_bytes INTEGER NOT NULL DEFAULT 10485760")
            conn.commit()
        finally:
            conn.close()


def _hash_password(password, salt=None, rounds=200000):
    if not isinstance(password, str) or not password:
        raise ValueError("password required")
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, rounds)
    return "pbkdf2_sha256${}${}${}".format(
        rounds,
        base64.b64encode(salt_bytes).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password, encoded):
    try:
        algorithm, rounds, salt_b64, hash_b64 = str(encoded).split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(hash_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _row_to_user(row):
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "email": row["email"] if "email" in row.keys() else None,
        "is_admin": bool(row["is_admin"]),
        "is_active": bool(row["is_active"]),
        "max_parallel_runs": int(row["max_parallel_runs"]) if row["max_parallel_runs"] is not None else 1,
        "max_prompt_chars": int(row["max_prompt_chars"]) if row["max_prompt_chars"] is not None else 20000,
        "max_upload_bytes": int(row["max_upload_bytes"]) if row["max_upload_bytes"] is not None else 10485760,
        "created_at": int(row["created_at"]),
        "updated_at": int(row["updated_at"]),
    }


def normalize_email(email):
    value = str(email or "").strip().lower()
    if not value:
        raise ValueError("email required")
    if len(value) > 254:
        raise ValueError("email too long")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("invalid email")
    return value


def get_user_by_username(app_root, username):
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            row = conn.execute(
                "SELECT id, username, email, is_admin, is_active, max_parallel_runs, max_prompt_chars, max_upload_bytes, created_at, updated_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            return _row_to_user(row)
        finally:
            conn.close()


def list_users(app_root):
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            rows = conn.execute(
                "SELECT id, username, email, is_admin, is_active, max_parallel_runs, max_prompt_chars, max_upload_bytes, created_at, updated_at FROM users ORDER BY username"
            ).fetchall()
            return [_row_to_user(row) for row in rows]
        finally:
            conn.close()


def create_user(app_root, username, password, is_admin=False, email=None):
    username = str(username or "").strip()
    if not username:
        raise ValueError("username required")
    if not password:
        raise ValueError("password required")
    normalized_email = normalize_email(email) if email is not None else None
    now = int(time.time())
    password_hash = _hash_password(password)
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            conn.execute(
                """
                INSERT INTO users (username, email, password_hash, is_admin, is_active, max_parallel_runs, max_prompt_chars, max_upload_bytes, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 1, 20000, 10485760, ?, ?)
                """,
                (username, normalized_email, password_hash, 1 if is_admin else 0, now, now),
            )
            conn.commit()
        finally:
            conn.close()
    return get_user_by_username(app_root, username)


def ensure_bootstrap_admin(app_root, username=None, password=None):
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count:
                return False
            admin_username = str(username or os.environ.get("GA_ADMIN_USERNAME") or "admin").strip()
            admin_password = str(password or os.environ.get("GA_ADMIN_PASSWORD") or "admin123456").strip()
            now = int(time.time())
            conn.execute(
                """
                INSERT INTO users (username, email, password_hash, is_admin, is_active, max_parallel_runs, max_prompt_chars, max_upload_bytes, created_at, updated_at)
                VALUES (?, NULL, ?, 1, 1, 1, 20000, 10485760, ?, ?)
                """,
                (admin_username, _hash_password(admin_password), now, now),
            )
            conn.commit()
            print(
                f"[Auth] Bootstrapped admin account username={admin_username}. "
                "Please change the default password immediately."
            )
            return True
        finally:
            conn.close()


def authenticate_user(app_root, username, password):
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            row = conn.execute(
                "SELECT id, username, email, password_hash, is_admin, is_active, max_parallel_runs, max_prompt_chars, max_upload_bytes, created_at, updated_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if not row or not bool(row["is_active"]):
                return None
            if not verify_password(password, row["password_hash"]):
                return None
            return _row_to_user(row)
        finally:
            conn.close()


def delete_sessions_by_user_id(app_root, user_id):
    if not user_id:
        return
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (int(user_id),))
            conn.commit()
        finally:
            conn.close()


def update_password(app_root, username, new_password):
    username = str(username or "").strip()
    if not username:
        raise ValueError("username required")
    if not isinstance(new_password, str) or len(new_password) < 6:
        raise ValueError("password must be at least 6 characters")
    now = int(time.time())
    password_hash = _hash_password(new_password)
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                raise ValueError("user not found")
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, now, int(row["id"])),
            )
            conn.commit()
            user_id = int(row["id"])
        finally:
            conn.close()
    delete_sessions_by_user_id(app_root, user_id)
    return get_user_by_username(app_root, username)


def change_password(app_root, username, old_password, new_password):
    username = str(username or "").strip()
    if not username:
        raise ValueError("username required")
    if not isinstance(old_password, str) or not old_password:
        raise ValueError("old password required")
    if not isinstance(new_password, str) or len(new_password) < 6:
        raise ValueError("new password must be at least 6 characters")
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            row = conn.execute(
                "SELECT id, password_hash FROM users WHERE username = ? AND is_active = 1",
                (username,),
            ).fetchone()
            if not row:
                raise ValueError("user not found")
            if not verify_password(old_password, row["password_hash"]):
                raise ValueError("old password is incorrect")
        finally:
            conn.close()
    return update_password(app_root, username, new_password)


def set_user_active(app_root, username, is_active):
    username = str(username or "").strip()
    if not username:
        raise ValueError("username required")
    now = int(time.time())
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                raise ValueError("user not found")
            user_id = int(row["id"])
            conn.execute(
                "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
                (1 if is_active else 0, now, user_id),
            )
            conn.commit()
        finally:
            conn.close()
    if not is_active:
        delete_sessions_by_user_id(app_root, user_id)
    return get_user_by_username(app_root, username)


def create_session(app_root, user_id, ttl_seconds=SESSION_TTL_SECONDS):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + int(ttl_seconds)
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (token, int(user_id), expires_at, now),
            )
            conn.commit()
            return {"token": token, "expires_at": expires_at}
        finally:
            conn.close()


def get_user_by_session(app_root, token):
    if not token:
        return None
    now = int(time.time())
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            row = conn.execute(
                """
                SELECT u.id, u.username, u.email, u.is_admin, u.is_active, u.max_parallel_runs, u.max_prompt_chars, u.max_upload_bytes, u.created_at, u.updated_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1
                """,
                (token, now),
            ).fetchone()
            return _row_to_user(row)
        finally:
            conn.close()


def delete_session(app_root, token):
    if not token:
        return
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()


def cleanup_expired_sessions(app_root):
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            conn.commit()
        finally:
            conn.close()


def set_user_limits(app_root, username, max_parallel_runs=None, max_prompt_chars=None, max_upload_bytes=None):
    username = str(username or "").strip()
    if not username:
        raise ValueError("username required")
    updates = []
    params = []
    if max_parallel_runs is not None:
        value = max(1, int(max_parallel_runs))
        updates.append("max_parallel_runs = ?")
        params.append(value)
    if max_prompt_chars is not None:
        value = max(100, int(max_prompt_chars))
        updates.append("max_prompt_chars = ?")
        params.append(value)
    if max_upload_bytes is not None:
        value = max(1024, int(max_upload_bytes))
        updates.append("max_upload_bytes = ?")
        params.append(value)
    if not updates:
        raise ValueError("no limits provided")
    updates.append("updated_at = ?")
    params.append(int(time.time()))
    params.append(username)
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            cur = conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE username = ?",
                tuple(params),
            )
            if cur.rowcount <= 0:
                raise ValueError("user not found")
            conn.commit()
        finally:
            conn.close()
    return get_user_by_username(app_root, username)


def add_audit_log(app_root, actor_username, action, target_username=None, detail=None):
    actor_username = str(actor_username or "").strip()
    action = str(action or "").strip()
    if not actor_username or not action:
        return
    detail_text = None if detail is None else str(detail)
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            conn.execute(
                """
                INSERT INTO audit_logs (actor_username, action, target_username, detail, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (actor_username, action, target_username, detail_text, int(time.time())),
            )
            conn.commit()
        finally:
            conn.close()


def list_audit_logs(app_root, actor_username=None, target_username=None, action=None, limit=100):
    clauses = []
    params = []
    if actor_username:
        clauses.append("actor_username = ?")
        params.append(str(actor_username).strip())
    if target_username:
        clauses.append("target_username = ?")
        params.append(str(target_username).strip())
    if action:
        clauses.append("action = ?")
        params.append(str(action).strip())
    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)
    limit = min(500, max(1, int(limit or 100)))
    with _DB_LOCK:
        conn = _connect(app_root)
        try:
            rows = conn.execute(
                f"""
                SELECT id, actor_username, action, target_username, detail, created_at
                FROM audit_logs
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            return [
                {
                    "id": int(row["id"]),
                    "actor_username": row["actor_username"],
                    "action": row["action"],
                    "target_username": row["target_username"],
                    "detail": row["detail"],
                    "created_at": int(row["created_at"]),
                }
                for row in rows
            ]
        finally:
            conn.close()
