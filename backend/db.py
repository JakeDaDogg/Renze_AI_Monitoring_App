"""
db.py — shared SQLite schema for the Renze backend (v3).

One minutes.db for all cycles (backfilled history + live/demo data) and one inference.db.
Both tables are keyed by the minute's epoch seconds (UTC); ts_utc is a generated,
human-readable copy (YYYYMMDDHHMM) and is never written.

Needs SQLite >= 3.31 (generated columns); Python 3.10+ ships a newer one.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from packet_io import CANON_SENSOR_COLS

PRAGMAS = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
"""

_TS_UTC = "ts_utc TEXT GENERATED ALWAYS AS (strftime('%Y%m%d%H%M', ts, 'unixepoch')) VIRTUAL"
_SENSOR_DDL = ',\n'.join(f'    "{c}" REAL' for c in CANON_SENSOR_COLS)

MINUTES_DDL = f"""
CREATE TABLE IF NOT EXISTS minutes (
    ts       INTEGER PRIMARY KEY,
    {_TS_UTC},
    n_rows   INTEGER NOT NULL,
    n_filled INTEGER NOT NULL DEFAULT 0,
{_SENSOR_DDL}
);
"""

INFERENCE_DDL = f"""
CREATE TABLE IF NOT EXISTS inference (
    ts            INTEGER PRIMARY KEY,
    {_TS_UTC},
    vcb2_x2       REAL,
    saved_power   REAL,
    model_version TEXT NOT NULL
);
"""

MINUTE_COLS = ['ts', 'n_rows', 'n_filled'] + list(CANON_SENSOR_COLS)
_QUOTED = ', '.join('"' + c + '"' for c in MINUTE_COLS)
INSERT_MINUTE = (
    f"INSERT OR IGNORE INTO minutes ({_QUOTED}) "
    f"VALUES ({', '.join('?' * len(MINUTE_COLS))})"
)
INFERENCE_COLS = ['ts', 'vcb2_x2', 'saved_power', 'model_version']
INSERT_INFERENCE = (
    f"INSERT OR IGNORE INTO inference ({', '.join(INFERENCE_COLS)}) "
    f"VALUES ({', '.join('?' * len(INFERENCE_COLS))})"
)

_EXPECTED = {
    'minutes': ['ts', 'ts_utc', 'n_rows', 'n_filled'] + list(CANON_SENSOR_COLS),
    'inference': ['ts', 'ts_utc', 'vcb2_x2', 'saved_power', 'model_version'],
}


SCHEMA_VERSION = '3'

_INFO_DDL = """
CREATE TABLE IF NOT EXISTS db_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def open_db(path: Path, table: str, mode: str) -> sqlite3.Connection:
    """
    Open (and create if needed) minutes.db or inference.db for `mode` ('demo' or 'prod').
    A new file is labelled with its mode in db_info; an existing file whose label differs,
    or whose schema is older, is refused, so a demo can never write into production.
    """
    if sqlite3.sqlite_version_info < (3, 31, 0):
        raise SystemExit(f'SQLite {sqlite3.sqlite_version} is too old: generated columns need 3.31+')
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(PRAGMAS + _INFO_DDL + (MINUTES_DDL if table == 'minutes' else INFERENCE_DDL))
    cols = [r[1] for r in conn.execute(f'PRAGMA table_xinfo({table})')]
    if cols != _EXPECTED[table]:
        conn.close()
        raise SystemExit(
            f'{path} has an older {table} schema ({len(cols)} columns). '
            f'Move it aside (e.g. rename to {path.name}.v2) and start again.')
    with conn:
        conn.execute("INSERT OR IGNORE INTO db_info VALUES ('mode', ?)", (mode,))
        conn.execute("INSERT OR IGNORE INTO db_info VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
        conn.execute("INSERT OR IGNORE INTO db_info VALUES ('created_utc', strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    stored = get_info(conn, 'mode')
    if stored != mode:
        conn.close()
        raise SystemExit(f'{path} belongs to mode {stored!r}, not {mode!r}: refusing to open it.')
    return conn


def get_info(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute('SELECT value FROM db_info WHERE key = ?', (key,)).fetchone()
    return row[0] if row else None


def set_info(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute('INSERT OR REPLACE INTO db_info VALUES (?, ?)', (key, value))


def max_ts(conn: sqlite3.Connection, table: str) -> int | None:
    return conn.execute(f'SELECT MAX(ts) FROM {table}').fetchone()[0]
