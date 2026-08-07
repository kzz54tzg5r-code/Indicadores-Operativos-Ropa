from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from core.settings import DB_FILE
@contextmanager
def connect():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(DB_FILE, timeout=3); con.row_factory=sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=3000")
    try: yield con; con.commit()
    finally: con.close()
def initialize_database():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL, scope TEXT NOT NULL DEFAULT 'COMPANY', region TEXT, store TEXT, team TEXT, active INTEGER NOT NULL DEFAULT 1, blocked_until TEXT, failed_attempts INTEGER NOT NULL DEFAULT 0, last_access TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, event TEXT NOT NULL, username TEXT, details TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY, name TEXT NOT NULL, value REAL NOT NULL, previous_value REAL, effective_from TEXT, changed_by TEXT, justification TEXT, changed_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS downloads(id INTEGER PRIMARY KEY, username TEXT, role TEXT, scope TEXT, report TEXT, period TEXT, filters TEXT, format TEXT, records INTEGER, bytes INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS system_state(id INTEGER PRIMARY KEY CHECK(id=1), state TEXT NOT NULL DEFAULT 'ACTIVE', message TEXT, changed_by TEXT, changed_at TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT OR IGNORE INTO system_state(id,state,message) VALUES(1,'ACTIVE','');
        """)
