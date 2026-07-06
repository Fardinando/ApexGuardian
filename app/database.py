import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from app.config import settings


def get_db_path() -> Path:
    return settings.database_full_path


def get_connection():
    if settings.use_turso:
        import libsql
        conn = libsql.connect(settings.turso_db_url, auth_token=settings.turso_auth_token)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        try:
            conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass
        return _TursoConnection(conn)
    import sqlite3
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class _TursoRow:
    __slots__ = ("_cols", "_vals", "_map")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals
        self._map = dict(zip(cols, vals))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._map[key]

    def __iter__(self):
        return iter(self._vals)

    def keys(self):
        return self._cols

    def values(self):
        return self._vals

    def items(self):
        return self._map.items()

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def __repr__(self):
        return f"<Row {dict(self._map)}>"


class _TursoCursor:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self.lastrowid = getattr(raw_cursor, "lastrowid", None)

    @property
    def description(self):
        return self._cur.description

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None or not self.description:
            return None
        cols = [d[0] for d in self.description]
        return _TursoRow(cols, row)

    def fetchall(self):
        if not self.description:
            return []
        cols = [d[0] for d in self.description]
        return [_TursoRow(cols, r) for r in self._cur.fetchall()]


class _TursoConnection:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        raw = self._conn.execute(sql, params or ())
        return _TursoCursor(raw)

    def executescript(self, script):
        for stmt in (s.strip() for s in script.split(";") if s.strip()):
            self._conn.execute(stmt)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS error_signatures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT UNIQUE NOT NULL,
                stack_trace TEXT,
                description TEXT,
                origin TEXT NOT NULL DEFAULT 'user_report',
                status TEXT NOT NULL DEFAULT 'new',
                total_reports INTEGER DEFAULT 1,
                unique_users INTEGER DEFAULT 1,
                fix_attempts INTEGER DEFAULT 0,
                design_guard_rejections INTEGER DEFAULT 0,
                cooldown_until TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_sig_id INTEGER REFERENCES error_signatures(id) ON DELETE CASCADE,
                user_id_anon TEXT NOT NULL,
                description TEXT,
                screenshot_base64 TEXT,
                timestamp_frontend REAL,
                matched_log INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fix_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_sig_id INTEGER REFERENCES error_signatures(id) ON DELETE CASCADE,
                attempt INTEGER NOT NULL,
                plan_md TEXT,
                feedback_round INTEGER DEFAULT 0,
                user_feedback TEXT,
                branch_name TEXT,
                preview_url TEXT,
                status TEXT DEFAULT 'pending_approval',
                design_guard_blocked INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS log_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_sig_id INTEGER REFERENCES error_signatures(id) ON DELETE CASCADE,
                deployment_id TEXT,
                timestamp TEXT,
                raw_log TEXT,
                matched_report_id INTEGER REFERENCES user_reports(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'basic',
                is_active INTEGER DEFAULT 1,
                created_by INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL,
                last_login TEXT
            );

            CREATE TABLE IF NOT EXISTS admin_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER REFERENCES admin_users(id) ON DELETE CASCADE,
                token TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details TEXT,
                ip_address TEXT,
                timestamp TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_error_hash ON error_signatures(hash);
            CREATE INDEX IF NOT EXISTS idx_error_status ON error_signatures(status);
            CREATE INDEX IF NOT EXISTS idx_reports_error ON user_reports(error_sig_id);
            CREATE INDEX IF NOT EXISTS idx_fix_error ON fix_attempts(error_sig_id);
            CREATE INDEX IF NOT EXISTS idx_activity_admin ON admin_activity_log(admin_id);
            CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON admin_activity_log(timestamp);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance_mode', '0');
        """)


def hash_error(stack_trace: str = "", description: str = "") -> str:
    raw = (stack_trace or description or "").strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def upsert_error_signature(hash_val: str, stack_trace: str, description: str,
                           origin: str, user_id_anon: Optional[str] = None) -> int:
    with db() as conn:
        existing = conn.execute(
            "SELECT id, total_reports, unique_users FROM error_signatures WHERE hash = ?",
            (hash_val,)
        ).fetchone()

        if existing:
            new_total = existing["total_reports"] + 1
            user_count = conn.execute(
                "SELECT COUNT(DISTINCT user_id_anon) FROM user_reports WHERE error_sig_id = ?",
                (existing["id"],)
            ).fetchone()[0]
            conn.execute(
                """UPDATE error_signatures SET total_reports = ?, unique_users = ?,
                   last_seen = ?, updated_at = ? WHERE id = ?""",
                (new_total, user_count, now_iso(), now_iso(), existing["id"])
            )
            return existing["id"]
        else:
            cur = conn.execute(
                """INSERT INTO error_signatures (hash, stack_trace, description, origin,
                   total_reports, unique_users, first_seen, last_seen, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 1, 1, ?, ?, ?, ?)""",
                (hash_val, stack_trace, description, origin, now_iso(), now_iso(), now_iso(), now_iso())
            )
            return cur.lastrowid


def seed_admin():
    with db() as conn:
        existing = conn.execute("SELECT id FROM admin_users WHERE role = 'supreme'").fetchone()
        if not existing:
            import bcrypt
            pw_hash = bcrypt.hashpw(settings.admin_pass.encode(), bcrypt.gensalt()).decode()
            conn.execute(
                """INSERT INTO admin_users (username, password_hash, role, is_active, created_at)
                   VALUES (?, ?, 'supreme', 1, ?)""",
                (settings.admin_user, pw_hash, now_iso())
            )


def verify_admin_login(username: str, password: str) -> Optional[dict]:
    import bcrypt
    with db() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role, is_active FROM admin_users WHERE username = ?",
            (username,)
        ).fetchone()
        if row:
            if not row["is_active"]:
                return {"banned": True}
            if bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
                conn.execute("UPDATE admin_users SET last_login = ? WHERE id = ?",
                             (now_iso(), row["id"]))
                return {
                    "id": row["id"],
                    "username": row["username"],
                    "role": row["role"],
                    "is_active": bool(row["is_active"]),
                }
    return None


def create_session(admin_id: int) -> str:
    import secrets
    token = secrets.token_hex(32)
    expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    with db() as conn:
        conn.execute(
            "INSERT INTO admin_sessions (admin_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (admin_id, token, now_iso(), expires)
        )
    return token


def validate_session(token: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            """SELECT u.id, u.username, u.role, u.is_active
               FROM admin_sessions s JOIN admin_users u ON s.admin_id = u.id
               WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1""",
            (token, now_iso())
        ).fetchone()
        if row:
            return {"id": row["id"], "username": row["username"],
                    "role": row["role"], "is_active": bool(row["is_active"])}
    return None


def delete_session(token: str):
    with db() as conn:
        conn.execute("DELETE FROM admin_sessions WHERE token = ?", (token,))


def log_admin_activity(admin_id: int, action: str, target_type: str = None,
                       target_id: str = None, details: dict = None, ip: str = None):
    with db() as conn:
        conn.execute(
            """INSERT INTO admin_activity_log (admin_id, action, target_type, target_id,
               details, ip_address, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (admin_id, action, target_type, target_id,
             json.dumps(details) if details else None, ip, now_iso())
        )


def get_errors_paginated(page: int = 1, per_page: int = 20, status: str = None,
                         origin: str = None, search: str = None) -> tuple[list, int]:
    with db() as conn:
        conditions = []
        params = []
        if status:
            if "," in status:
                statuses = [s.strip() for s in status.split(",")]
                placeholders = ",".join("?" for _ in statuses)
                conditions.append(f"e.status IN ({placeholders})")
                params.extend(statuses)
            else:
                conditions.append("e.status = ?")
                params.append(status)
        if origin:
            conditions.append("e.origin = ?")
            params.append(origin)
        if search:
            conditions.append("(e.description LIKE ? OR e.stack_trace LIKE ? OR e.hash LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        where = " AND ".join(conditions) if conditions else "1=1"
        total = conn.execute(
            f"SELECT COUNT(*) FROM error_signatures e WHERE {where}", params
        ).fetchone()[0]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""SELECT e.*, (SELECT COUNT(*) FROM user_reports r WHERE r.error_sig_id = e.id) as report_count
                FROM error_signatures e WHERE {where}
                ORDER BY e.last_seen DESC LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ).fetchall()
        return [dict(r) for r in rows], total


def get_error_by_id(error_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            """SELECT e.*,
               (SELECT COUNT(*) FROM user_reports r WHERE r.error_sig_id = e.id) as report_count
               FROM error_signatures e WHERE e.id = ?""",
            (error_id,)
        ).fetchone()
        if row:
            return dict(row)
    return None


def get_error_by_hash(hash_val: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM error_signatures WHERE hash = ?", (hash_val,)
        ).fetchone()
        if row:
            return dict(row)
    return None


def get_reports_for_error(error_sig_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM user_reports WHERE error_sig_id = ? ORDER BY created_at DESC",
            (error_sig_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_fix_attempts_for_error(error_sig_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM fix_attempts WHERE error_sig_id = ? ORDER BY attempt ASC",
            (error_sig_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def create_fix_attempt(error_sig_id: int, attempt: int, plan_md: str) -> int:
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO fix_attempts (error_sig_id, attempt, plan_md, status, created_at)
               VALUES (?, ?, ?, 'pending_approval', ?)""",
            (error_sig_id, attempt, plan_md, now_iso())
        )
        return cur.lastrowid


def update_fix_attempt(fix_id: int, **kwargs):
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [fix_id]
    with db() as conn:
        conn.execute(f"UPDATE fix_attempts SET {fields} WHERE id = ?", vals)


def update_error_status(error_id: int, status: str):
    with db() as conn:
        conn.execute(
            "UPDATE error_signatures SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), error_id)
        )


def increment_fix_attempts(error_id: int):
    with db() as conn:
        conn.execute(
            "UPDATE error_signatures SET fix_attempts = fix_attempts + 1, updated_at = ? WHERE id = ?",
            (now_iso(), error_id)
        )


def set_cooldown(error_id: int, hours: int = 24):
    until = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
    with db() as conn:
        conn.execute(
            "UPDATE error_signatures SET status = 'cooldown', cooldown_until = ?, updated_at = ? WHERE id = ?",
            (until, now_iso(), error_id)
        )


def set_error_give_up(error_id: int):
    with db() as conn:
        conn.execute(
            "UPDATE error_signatures SET status = 'give_up', updated_at = ? WHERE id = ?",
            (now_iso(), error_id)
        )


def add_user_report(error_sig_id: int, user_id_anon: str, description: str,
                    screenshot_base64: str, timestamp_frontend: float, matched_log: bool) -> int:
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO user_reports (error_sig_id, user_id_anon, description,
               screenshot_base64, timestamp_frontend, matched_log, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (error_sig_id, user_id_anon, description, screenshot_base64,
             timestamp_frontend, 1 if matched_log else 0, now_iso())
        )
        return cur.lastrowid


def add_log_event(error_sig_id: int, deployment_id: str, raw_log: str, timestamp: str):
    with db() as conn:
        conn.execute(
            "INSERT INTO log_events (error_sig_id, deployment_id, raw_log, timestamp) VALUES (?, ?, ?, ?)",
            (error_sig_id, deployment_id, raw_log, timestamp)
        )


def get_dashboard_stats() -> dict:
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM error_signatures").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM error_signatures WHERE status IN ('new','analyzing','waiting_approval')").fetchone()[0]
        preview = conn.execute("SELECT COUNT(*) FROM error_signatures WHERE status = 'preview'").fetchone()[0]
        resolved = conn.execute("SELECT COUNT(*) FROM error_signatures WHERE status = 'production'").fetchone()[0]
        fully_archived = conn.execute("SELECT COUNT(*) FROM error_signatures WHERE status = 'archived_no_log' AND total_reports = 1").fetchone()[0]
        partially_archived = conn.execute("SELECT COUNT(*) FROM error_signatures WHERE status = 'archived_no_log' AND total_reports > 1").fetchone()[0]
        cooldown = conn.execute("SELECT COUNT(*) FROM error_signatures WHERE status = 'cooldown' AND cooldown_until > ?", (now_iso(),)).fetchone()[0]
        ignored = conn.execute("SELECT COUNT(*) FROM error_signatures WHERE status = 'ignored'").fetchone()[0]
        users = conn.execute("SELECT COUNT(DISTINCT user_id_anon) FROM user_reports").fetchone()[0]
        return {
            "total": total, "active": active, "preview": preview, "resolved": resolved,
            "fully_archived": fully_archived, "partially_archived": partially_archived,
            "cooldown": cooldown, "ignored": ignored, "total_users": users,
        }


def get_errors_by_day(days: int = 30) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT DATE(created_at) as day, COUNT(*) as count
               FROM error_signatures WHERE created_at >= DATE('now', ?)
               GROUP BY day ORDER BY day ASC""",
            (f"-{days} days",)
        ).fetchall()
        return [dict(r) for r in rows]


def get_top_errors(limit: int = 5) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT e.hash, e.description, e.status, e.total_reports,
                      (SELECT COUNT(*) FROM user_reports r WHERE r.error_sig_id = e.id) as report_count
               FROM error_signatures e ORDER BY report_count DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_activity(limit: int = 10) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT 'error' as type, e.hash as id, e.description as title,
                      e.status as detail, e.created_at as timestamp
               FROM error_signatures e
               UNION ALL
               SELECT 'fix' as type, CAST(f.id AS TEXT) as id, f.status as title,
                      'Attempt ' || f.attempt as detail, f.created_at as timestamp
               FROM fix_attempts f
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_admin_by_id(admin_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            "SELECT id, username, role, is_active FROM admin_users WHERE id = ?",
            (admin_id,)
        ).fetchone()
        return dict(row) if row else None


def get_admin_list() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT u.id, u.username, u.role, u.is_active, u.created_at, u.last_login,
                      c.username as created_by_name
               FROM admin_users u LEFT JOIN admin_users c ON u.created_by = c.id
               ORDER BY u.id ASC"""
        ).fetchall()
        return [dict(r) for r in rows]


def create_admin(username: str, password_hash: str, role: str, created_by: int) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO admin_users (username, password_hash, role, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, role, created_by, now_iso())
        )
        return cur.lastrowid


def update_admin_role(admin_id: int, new_role: str):
    with db() as conn:
        conn.execute("UPDATE admin_users SET role = ? WHERE id = ?", (new_role, admin_id))


def rename_admin(admin_id: int, new_username: str):
    with db() as conn:
        conn.execute("UPDATE admin_users SET username = ? WHERE id = ?", (new_username, admin_id))


def update_admin_password(admin_id: int, password_hash: str):
    with db() as conn:
        conn.execute("UPDATE admin_users SET password_hash = ? WHERE id = ?", (password_hash, admin_id))


def toggle_admin_active(admin_id: int, active: bool):
    with db() as conn:
        conn.execute("UPDATE admin_users SET is_active = ? WHERE id = ?", (1 if active else 0, admin_id))


def get_activity_log(page: int = 1, per_page: int = 50, action: str = None) -> tuple[list[dict], int]:
    with db() as conn:
        if action:
            total = conn.execute(
                "SELECT COUNT(*) FROM admin_activity_log WHERE action LIKE ?",
                (f"%{action}%",)
            ).fetchone()[0]
            offset = (page - 1) * per_page
            rows = conn.execute(
                """SELECT a.*, u.username as admin_name
                   FROM admin_activity_log a LEFT JOIN admin_users u ON a.admin_id = u.id
                   WHERE a.action LIKE ?
                   ORDER BY a.timestamp DESC LIMIT ? OFFSET ?""",
                (f"%{action}%", per_page, offset)
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM admin_activity_log").fetchone()[0]
            offset = (page - 1) * per_page
            rows = conn.execute(
                """SELECT a.*, u.username as admin_name
                   FROM admin_activity_log a LEFT JOIN admin_users u ON a.admin_id = u.id
                   ORDER BY a.timestamp DESC LIMIT ? OFFSET ?""",
                (per_page, offset)
            ).fetchall()
        return [dict(r) for r in rows], total


def get_user_stats() -> dict:
    with db() as conn:
        total_users = conn.execute("SELECT COUNT(DISTINCT user_id_anon) FROM user_reports").fetchone()[0]
        top_reporters = conn.execute(
            """SELECT user_id_anon, COUNT(*) as count
               FROM user_reports GROUP BY user_id_anon ORDER BY count DESC LIMIT 10"""
        ).fetchall()
        return {
            "total_users": total_users,
            "top_reporters": [dict(r) for r in top_reporters],
        }


def delete_error_complete(error_id: int):
    with db() as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM user_reports WHERE error_sig_id = ?", (error_id,))
        conn.execute("DELETE FROM log_events WHERE error_sig_id = ?", (error_id,))
        conn.execute("DELETE FROM fix_attempts WHERE error_sig_id = ?", (error_id,))
        conn.execute("DELETE FROM error_signatures WHERE id = ?", (error_id,))


def set_maintenance_mode(active: bool):
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('maintenance_mode', ?)",
            ("1" if active else "0",)
        )


def is_maintenance_mode() -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'maintenance_mode'"
        ).fetchone()
        return row is not None and row[0] == "1"
