"""SQLite persistence: one JSON state document per student + an append-only agent event log."""
import json
import sqlite3
import threading
import time
import uuid

from . import config

_lock = threading.RLock()
_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

with _lock:
    _conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            id TEXT PRIMARY KEY,
            name TEXT,
            created_at REAL,
            state TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            ts REAL,
            agent TEXT,
            kind TEXT,
            message TEXT,
            data TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_events_student ON events(student_id, id);
        """
    )
    _conn.commit()


def empty_state(name: str, target_role: str) -> dict:
    return {
        "name": name,
        "target_role": target_role,
        "status": "idle",  # idle | running | ready | error
        "resume_text": "",
        "profile": None,
        "ats": None,
        "jobs": [],
        "target_job_id": None,
        "gaps": None,
        "roadmap": None,
        "interviews": [],
        "active_interview": None,
        "progress": None,
        "readiness_history": [],
    }


def create_student(name: str, target_role: str) -> str:
    sid = uuid.uuid4().hex[:10]
    with _lock:
        _conn.execute(
            "INSERT INTO students (id, name, created_at, state) VALUES (?, ?, ?, ?)",
            (sid, name, time.time(), json.dumps(empty_state(name, target_role))),
        )
        _conn.commit()
    return sid


def get_state(sid: str):
    with _lock:
        row = _conn.execute("SELECT state FROM students WHERE id = ?", (sid,)).fetchone()
    return json.loads(row["state"]) if row else None


def save_state(sid: str, state: dict):
    with _lock:
        _conn.execute("UPDATE students SET state = ?, name = ? WHERE id = ?", (json.dumps(state), state.get("name"), sid))
        _conn.commit()


def list_students():
    with _lock:
        rows = _conn.execute("SELECT id, name, created_at, state FROM students ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        st = json.loads(r["state"])
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "target_role": st.get("target_role"),
                "readiness": (st.get("progress") or {}).get("readiness"),
                "ats": (st.get("ats") or {}).get("score"),
                "status": st.get("status"),
            }
        )
    return out


def log_event(sid: str, agent: str, kind: str, message: str, data=None):
    with _lock:
        _conn.execute(
            "INSERT INTO events (student_id, ts, agent, kind, message, data) VALUES (?, ?, ?, ?, ?, ?)",
            (sid, time.time(), agent, kind, message, json.dumps(data) if data is not None else None),
        )
        _conn.commit()


def get_events(sid: str, after_id: int = 0, limit: int = 300):
    with _lock:
        rows = _conn.execute(
            "SELECT id, ts, agent, kind, message, data FROM events WHERE student_id = ? AND id > ? ORDER BY id LIMIT ?",
            (sid, after_id, limit),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "ts": r["ts"],
            "agent": r["agent"],
            "kind": r["kind"],
            "message": r["message"],
            "data": json.loads(r["data"]) if r["data"] else None,
        }
        for r in rows
    ]
