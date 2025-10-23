# storage.py
import sqlite3
from datetime import datetime
from typing import Optional, List, Tuple

DB_FILE = "reminders.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alisa_user_id TEXT,
    telegram_chat_id TEXT,
    telegram_thread_id TEXT,
    text TEXT NOT NULL,
    remind_ts TEXT NOT NULL, -- ISO8601 UTC
    job_id TEXT,
    created_at TEXT NOT NULL
);
"""

def _connect():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(CREATE_SQL)
    conn.commit()
    return conn

_conn = _connect()

def add_reminder(alisa_user_id: Optional[str], telegram_chat_id: str, telegram_thread_id: Optional[str],
                 text: str, remind_dt_iso: str) -> int:
    """Добавить напоминание. remind_dt_iso — ISO timestamp в UTC"""
    cur = _conn.cursor()
    created_at = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO reminders (alisa_user_id, telegram_chat_id, telegram_thread_id, text, remind_ts, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (alisa_user_id, telegram_chat_id, telegram_thread_id, text, remind_dt_iso, created_at)
    )
    _conn.commit()
    return cur.lastrowid

def update_job_id(reminder_id: int, job_id: str):
    cur = _conn.cursor()
    cur.execute("UPDATE reminders SET job_id=? WHERE id=?", (job_id, reminder_id))
    _conn.commit()

def delete_reminder(reminder_id: int):
    cur = _conn.cursor()
    cur.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
    _conn.commit()
    return cur.rowcount

def get_by_id(reminder_id: int):
    cur = _conn.cursor()
    cur.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,))
    row = cur.fetchone()
    return dict(row) if row else None

def get_pending(now_iso: str = None) -> List[dict]:
    """Вернуть все напоминания где remind_ts > now_iso (UTC). Если now_iso None — берем сейчас."""
    if now_iso is None:
        now_iso = datetime.utcnow().isoformat()
    cur = _conn.cursor()
    cur.execute("SELECT * FROM reminders WHERE remind_ts > ? ORDER BY remind_ts ASC", (now_iso,))
    rows = cur.fetchall()
    return [dict(r) for r in rows]

def get_all():
    cur = _conn.cursor()
    cur.execute("SELECT * FROM reminders ORDER BY remind_ts ASC")
    return [dict(r) for r in cur.fetchall()]
