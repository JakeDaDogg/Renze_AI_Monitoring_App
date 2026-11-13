"""
reader.py — backend reader with stub processor for the Renze C9 demo.

Polls demo_root/inbox/ every 100 ms, processes packets strictly in time order,
appends raw copies, computes 1-min means, and commits packets + minutes to SQLite.
Scoring (Part 2) replaces the stub processor call.

Usage:
    python reader.py [--demo-root PATH] [--gap-wait SECS] [--db PATH]
"""
from __future__ import annotations

import os
import sqlite3
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from packet_io import (
    CANON_SENSOR_COLS,
    ROWS_PER_PACKET,
    VCB2_IDX,
    name_to_quarter,
    one_min_means,
    quarter_to_name,
    read_packet,
    validate_packet,
)

DEFAULT_DEMO_ROOT = Path(__file__).parent.parent / 'demo_root'
DEFAULT_GAP_WAIT  = 2.0   # seconds of wall time before declaring a gap
POLL_INTERVAL     = 0.1   # seconds between inbox scans

# ── SQLite schema (Part 1 tables only) ───────────────────────────────────────

_SENSOR_COLS_DDL = '\n'.join(
    f'    "{col}" REAL,' for col in CANON_SENSOR_COLS
)

_DDL = f"""
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS cycles (
    cycle_id    INTEGER PRIMARY KEY,
    started_ts  INTEGER,
    closed_ts   INTEGER,
    close_reason TEXT,
    export_path TEXT
);

CREATE TABLE IF NOT EXISTS packets (
    quarter_ts     INTEGER PRIMARY KEY,
    cycle_id       INTEGER,
    file_name      TEXT,
    status         TEXT,
    n_rows         INTEGER,
    received_wall  REAL,
    committed_wall REAL,
    FOREIGN KEY (cycle_id) REFERENCES cycles(cycle_id)
);

CREATE TABLE IF NOT EXISTS minutes (
    ts       INTEGER PRIMARY KEY,
    cycle_id INTEGER,
{_SENSOR_COLS_DDL}
    vcb2_roll15 REAL,
    FOREIGN KEY (cycle_id) REFERENCES cycles(cycle_id)
);

CREATE TABLE IF NOT EXISTS messages (
    msg_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_data  INTEGER,
    ts_wall  REAL,
    level    TEXT,
    type     TEXT,
    text     TEXT,
    payload  TEXT,
    acked    INTEGER DEFAULT 0
);
"""

_INSERT_PACKET = """
INSERT OR IGNORE INTO packets
    (quarter_ts, cycle_id, file_name, status, n_rows, received_wall, committed_wall)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""

_MINUTE_COLS = ['ts', 'cycle_id'] + [f'"{c}"' for c in CANON_SENSOR_COLS] + ['vcb2_roll15']
_INSERT_MINUTE = (
    f"INSERT OR REPLACE INTO minutes ({', '.join(_MINUTE_COLS)}) "
    f"VALUES ({', '.join(['?'] * len(_MINUTE_COLS))})"
)

_INSERT_MESSAGE = """
INSERT INTO messages (ts_data, ts_wall, level, type, text, payload)
VALUES (?, ?, ?, ?, ?, ?)
"""


# ── Stub processor state ──────────────────────────────────────────────────────

class _StubState:
    """Minimal state for the Part 1 stub processor (VCB2 rolling mean only)."""
    def __init__(self, cycle_id: int) -> None:
        self.cycle_id = cycle_id
        self._vcb2_trail: deque[float] = deque(maxlen=15)

    def vcb2_roll15(self, vcb2_val: float) -> float | None:
        self._vcb2_trail.append(vcb2_val)
        if len(self._vcb2_trail) < 15:
            return None
        return float(np.mean(self._vcb2_trail))


# ── Database helpers ──────────────────────────────────────────────────────────

def _init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(_DDL)
    return conn


def _ensure_cycle(conn: sqlite3.Connection, started_ts: int) -> int:
    """Return cycle_id=1, inserting the cycle row if it doesn't exist."""
    conn.execute(
        "INSERT OR IGNORE INTO cycles (cycle_id, started_ts) VALUES (1, ?)",
        (started_ts,),
    )
    return 1


def _post_message(
    conn: sqlite3.Connection,
    ts_data: int | None,
    level: str,
    msg_type: str,
    text: str,
    payload: str | None = None,
) -> None:
    conn.execute(
        _INSERT_MESSAGE,
        (ts_data, time.time(), level, msg_type, text, payload),
    )
    print(f"[{level.upper():8s}] {msg_type}: {text}")


# ── Raw-copy append ───────────────────────────────────────────────────────────

def _append_raw(raw_dir: Path, quarter_ts: int, data: np.ndarray) -> None:
    """Append 180 rows to raw/YYYYMMDD.csv (UTC date of the quarter)."""
    from packet_io import RAW_SENSOR_COLS
    dt = datetime.fromtimestamp(quarter_ts, tz=timezone.utc)
    day_file = raw_dir / f"{dt.strftime('%Y%m%d')}.csv"
    full_header = 'ts,' + ','.join(RAW_SENSOR_COLS)
    write_header = not day_file.exists()
    with open(day_file, 'a') as fh:
        if write_header:
            fh.write(full_header + '\n')
        fmt = ['%d'] + ['%.9g'] * 49
        np.savetxt(fh, data, delimiter=',', comments='', fmt=fmt)


# ── Packet processing ─────────────────────────────────────────────────────────

def _process_ok(
    path: Path,
    received_wall: float,
    conn: sqlite3.Connection,
    raw_dir: Path,
    state: _StubState,
) -> None:
    """Parse, validate, store raw copy, compute 1-min means, commit to SQLite."""
    quarter_ts, data = read_packet(path)
    validate_packet(quarter_ts, data)

    _append_raw(raw_dir, quarter_ts, data)
    min_ts, means = one_min_means(data)

    with conn:
        # Ensure cycle exists (first packet sets cycle start)
        _ensure_cycle(conn, int(min_ts[0]))

        conn.execute(
            _INSERT_PACKET,
            (quarter_ts, state.cycle_id, path.name, 'ok',
             ROWS_PER_PACKET, received_wall, time.time()),
        )
        for i in range(len(min_ts)):
            vcb2_val = float(means[i, VCB2_IDX])
            roll15   = state.vcb2_roll15(vcb2_val)
            row = (int(min_ts[i]), state.cycle_id) + tuple(means[i]) + (roll15,)
            conn.execute(_INSERT_MINUTE, row)


def _record_missing(
    quarter_ts: int,
    conn: sqlite3.Connection,
    state: _StubState,
) -> None:
    with conn:
        conn.execute(
            _INSERT_PACKET,
            (quarter_ts, state.cycle_id, quarter_to_name(quarter_ts),
             'missing', 0, None, time.time()),
        )
        _post_message(conn, quarter_ts, 'warning', 'data_gap',
                      f"quarter {quarter_to_name(quarter_ts)} not received within gap_wait")


def _record_late(
    path: Path,
    raw_dir: Path,
    conn: sqlite3.Connection,
    state: _StubState,
) -> None:
    quarter_ts, data = read_packet(path)
    _append_raw(raw_dir, quarter_ts, data)
    with conn:
        conn.execute(
            _INSERT_PACKET,
            (quarter_ts, state.cycle_id, path.name, 'late',
             ROWS_PER_PACKET, time.time(), time.time()),
        )
        _post_message(conn, quarter_ts, 'warning', 'late_packet',
                      f"{path.name} arrived after its quarter was already passed")


def _record_rejected(
    path: Path,
    reason: str,
    conn: sqlite3.Connection,
    state: _StubState,
) -> None:
    quarter_ts = name_to_quarter(path.name) or 0
    with conn:
        conn.execute(
            _INSERT_PACKET,
            (quarter_ts, state.cycle_id, path.name, 'rejected',
             0, None, time.time()),
        )
        _post_message(conn, quarter_ts, 'warning', 'rejected_packet',
                      f"{path.name} rejected: {reason}")


# ── Inbox scan ────────────────────────────────────────────────────────────────

def _sorted_inbox(inbox: Path) -> list[str]:
    """Return sorted list of packet file names in inbox/ (ignoring .tmp/)."""
    names = []
    for entry in os.scandir(inbox):
        if entry.is_file() and name_to_quarter(entry.name) is not None:
            names.append(entry.name)
    return sorted(names)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(demo_root: Path, gap_wait_s: float, db_path: Path) -> None:
    inbox     = demo_root / 'inbox'
    processed = inbox / 'processed'
    rejected  = inbox / 'rejected'
    raw_dir   = demo_root / 'raw'
    control   = demo_root / 'control'
    eos_path  = control / 'EOS'

    for d in [inbox, processed, rejected, raw_dir, control]:
        d.mkdir(parents=True, exist_ok=True)

    conn  = _init_db(db_path)
    state = _StubState(cycle_id=1)

    next_expected: int | None = None   # epoch-second quarter ts
    gap_since: float | None   = None   # wall time when gap first detected

    print(f"Reader started — polling {inbox}")
    print(f"Database: {db_path}")

    while True:
        files = _sorted_inbox(inbox)

        while True:
            if not files:
                break

            first_q = name_to_quarter(files[0])

            # Initialise expected from first file seen
            if next_expected is None:
                next_expected = first_q

            if first_q == next_expected:
                # Normal: expected packet arrived
                gap_since = None
                path = inbox / files[0]
                received_wall = time.time()
                try:
                    _process_ok(path, received_wall, conn, raw_dir, state)
                    os.replace(path, processed / files[0])
                    print(f"[OK      ] {files[0]}")
                except (ValueError, OSError) as exc:
                    os.replace(path, rejected / files[0])
                    _record_rejected(
                        rejected / files[0], str(exc), conn, state
                    )
                next_expected += 900
                files = _sorted_inbox(inbox)

            elif first_q < next_expected:
                # Late packet: arrived after its quarter was already processed
                path = inbox / files[0]
                try:
                    _record_late(path, raw_dir, conn, state)
                    os.replace(path, processed / files[0])
                except (ValueError, OSError) as exc:
                    os.replace(path, rejected / files[0])
                    _record_rejected(rejected / files[0], str(exc), conn, state)
                files = _sorted_inbox(inbox)

            else:
                # first_q > next_expected → gap; a later file is waiting
                if gap_since is None:
                    gap_since = time.time()
                if time.time() - gap_since >= gap_wait_s:
                    _record_missing(next_expected, conn, state)
                    next_expected += 900
                    gap_since = None
                    # re-check without rescanning — same files list is fine
                else:
                    break  # keep waiting

        # Check for EOS exit condition
        if eos_path.exists() and not files:
            with conn:
                _post_message(conn, None, 'info', 'replay_finished',
                               'EOS received and inbox empty — replay finished')
            print("Reader done.")
            break

        time.sleep(POLL_INTERVAL)

    conn.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description='Renze backend reader (Part 1 stub)')
    ap.add_argument('--demo-root', type=Path, default=DEFAULT_DEMO_ROOT)
    ap.add_argument('--gap-wait',  type=float, default=DEFAULT_GAP_WAIT, metavar='SECS')
    ap.add_argument('--db',        type=Path, default=None)
    args = ap.parse_args()

    db_path = args.db or (args.demo_root / 'renze.db')
    run(args.demo_root, args.gap_wait, db_path)


if __name__ == '__main__':
    main()
