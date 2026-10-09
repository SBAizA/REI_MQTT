"""SQLite persistence for machines, status history and logbook notes."""

import json
import sqlite3
import time
from contextlib import closing

SCHEMA = """
CREATE TABLE IF NOT EXISTS machines (
    id          TEXT PRIMARY KEY,
    info        TEXT NOT NULL DEFAULT '{}',  -- JSON documentation from <prefix>/<id>/info
    state       TEXT,
    detail      TEXT,
    last_seen   INTEGER
);
CREATE TABLE IF NOT EXISTS status_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id  TEXT NOT NULL REFERENCES machines(id),
    ts          INTEGER NOT NULL,
    state       TEXT NOT NULL,
    detail      TEXT,
    payload     TEXT NOT NULL,
    is_will     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_status_machine_ts ON status_log(machine_id, ts DESC);
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id  TEXT NOT NULL REFERENCES machines(id),
    ts          INTEGER NOT NULL,
    author      TEXT,
    text        TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # WAL lets the web app read while the collector writes (SD card friendly too).
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _ensure_machine(conn: sqlite3.Connection, machine_id: str) -> None:
    conn.execute("INSERT OR IGNORE INTO machines(id) VALUES (?)", (machine_id,))


def save_status(conn, machine_id: str, state: str, detail: str | None, payload: dict, is_will: bool) -> None:
    ts = int(time.time())
    with conn:
        _ensure_machine(conn, machine_id)
        conn.execute(
            "INSERT INTO status_log(machine_id, ts, state, detail, payload, is_will) VALUES (?,?,?,?,?,?)",
            (machine_id, ts, state, detail, json.dumps(payload), int(is_will)),
        )
        conn.execute(
            "UPDATE machines SET state=?, detail=?, last_seen=? WHERE id=?",
            (state, detail, ts, machine_id),
        )


def save_info(conn, machine_id: str, info: dict) -> None:
    with conn:
        _ensure_machine(conn, machine_id)
        conn.execute("UPDATE machines SET info=? WHERE id=?", (json.dumps(info), machine_id))


def add_note(conn, machine_id: str, author: str | None, text: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO notes(machine_id, ts, author, text) VALUES (?,?,?,?)",
            (machine_id, int(time.time()), author, text),
        )


def list_machines(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM machines ORDER BY id").fetchall()
    return [{**dict(r), "info": json.loads(r["info"])} for r in rows]


def get_machine(conn, machine_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM machines WHERE id=?", (machine_id,)).fetchone()
    return {**dict(row), "info": json.loads(row["info"])} if row else None


def status_history(conn, machine_id: str, limit: int = 100) -> list[dict]:
    with closing(conn.execute(
        "SELECT ts, state, detail, is_will FROM status_log WHERE machine_id=? ORDER BY id DESC LIMIT ?",
        (machine_id, limit),
    )) as cur:
        return [dict(r) for r in cur]


def notes(conn, machine_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT ts, author, text FROM notes WHERE machine_id=? ORDER BY id DESC", (machine_id,)
    ).fetchall()
    return [dict(r) for r in rows]
