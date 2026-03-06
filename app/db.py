import sqlite3
from pathlib import Path

DB_PATH = Path("data/mvp.db")


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                dut_profile TEXT NOT NULL,
                trays INTEGER NOT NULL,
                bports_per_tray INTEGER NOT NULL,
                lanes_per_bport INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                dut_serial TEXT NOT NULL,
                prbs_type TEXT NOT NULL,
                duration_sec INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                pass_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                notes TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lane_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_run_id INTEGER NOT NULL,
                tray INTEGER NOT NULL,
                bport INTEGER NOT NULL,
                lane INTEGER NOT NULL,
                ber REAL NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(test_run_id) REFERENCES test_runs(id)
            )
            """
        )
