"""
reader.py — Renze backend reader (v2): bundles rows by data timestamp, stub processor.

Folders (under demo_root/):
    to_be_processed/   the writer drops one CSV per 5-s row (contract in packet_io.py)
    processed/         minutes.db  — 1-min sensor means (+ n_rows per minute)
                       inference.db — processor output per minute
    bad/               files that failed to parse; their rows count as missing
    control/EOS        written by the replay agent when it has finished

Rules
- A bundle is every row with ts in [cut, cut + 900). It is processed once a row with
  ts >= cut + 900 exists, i.e. the bundle is complete. Otherwise the reader waits (writer
  stopped or slow). A backlog is processed bundle after bundle until the reader catches up.
- After EOS, the remaining rows are flushed (including a final partial bundle) and the
  reader exits.
- Next cut at start-up: the bundle after the last one committed in BOTH databases (the
  earlier of the two). With nothing committed, the bundle containing the oldest file.
- Per bundle: commit minutes.db, commit inference.db, then delete the bundle's files.
  Inserts are keyed by ts (INSERT OR IGNORE), so a crash at any point redoes that bundle.
- A SQLite error waits RETRY_S and retries the same bundle instead of stopping the reader.
- Minutes with no rows are skipped; partial minutes are averaged; n_rows says how many rows.

Usage:
    python reader.py [--demo-root PATH] [--poll SECS]
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import numpy as np

from packet_io import (
    BUNDLE_S,
    CANON_SENSOR_COLS,
    N_COLS,
    VCB2_IDX,
    floor_bundle,
    name_to_ts,
    one_min_means,
    read_row,
    ts_to_name,
)

DEFAULT_DEMO_ROOT = Path(__file__).parent.parent / 'demo_root'
POLL_S  = 0.1        # wall seconds between folder scans
RETRY_S = 1.0        # wall seconds before retrying a failed database commit
STUB_VERSION = 'stub-2xVCB2'

# ── SQLite ────────────────────────────────────────────────────────────────────

_PRAGMAS = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
"""

_SENSOR_DDL = ',\n'.join(f'    "{c}" REAL' for c in CANON_SENSOR_COLS)

_MINUTES_DDL = f"""
CREATE TABLE IF NOT EXISTS minutes (
    ts     INTEGER PRIMARY KEY,
    n_rows INTEGER NOT NULL,
{_SENSOR_DDL}
);
"""

_INFERENCE_DDL = """
CREATE TABLE IF NOT EXISTS inference (
    ts            INTEGER PRIMARY KEY,
    vcb2_x2       REAL,
    model_version TEXT NOT NULL
);
"""

_MIN_COLS = ['ts', 'n_rows'] + [f'"{c}"' for c in CANON_SENSOR_COLS]
_INSERT_MINUTE = (f"INSERT OR IGNORE INTO minutes ({', '.join(_MIN_COLS)}) "
                  f"VALUES ({', '.join('?' * len(_MIN_COLS))})")
_INSERT_INFERENCE = ("INSERT OR IGNORE INTO inference (ts, vcb2_x2, model_version) "
                     "VALUES (?, ?, ?)")


def _open_db(path: Path, ddl: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(_PRAGMAS + ddl)
    return conn


def _resume_cut(m_conn: sqlite3.Connection, i_conn: sqlite3.Connection) -> int | None:
    """Bundle after the last one committed in both databases, or None if either is empty."""
    last_m = m_conn.execute('SELECT MAX(ts) FROM minutes').fetchone()[0]
    last_i = i_conn.execute('SELECT MAX(ts) FROM inference').fetchone()[0]
    if last_m is None or last_i is None:
        return None
    return floor_bundle(min(last_m, last_i)) + BUNDLE_S


def _commit(m_conn: sqlite3.Connection, i_conn: sqlite3.Connection,
            minute_rows: list[tuple], inference_rows: list[tuple]) -> None:
    """Commit one bundle to both databases; retry on any SQLite error (inserts are idempotent)."""
    while True:
        try:
            with m_conn:
                m_conn.executemany(_INSERT_MINUTE, minute_rows)
            with i_conn:
                i_conn.executemany(_INSERT_INFERENCE, inference_rows)
            return
        except sqlite3.Error as exc:
            print(f"[DB RETRY] {exc} — retrying in {RETRY_S:.0f} s")
            time.sleep(RETRY_S)


# ── Processor (stub) ──────────────────────────────────────────────────────────

def process(min_ts: np.ndarray, means: np.ndarray) -> list[tuple]:
    """Stub: output = 2 × the minute's VCB2-Power mean. Replace with the RUL models."""
    return [(int(t), 2.0 * float(m[VCB2_IDX]), STUB_VERSION) for t, m in zip(min_ts, means)]


# ── Files ─────────────────────────────────────────────────────────────────────

def _scan(tbp: Path) -> list[tuple[int, str]]:
    """(ts, name) of every packet file in to_be_processed/, sorted by ts (.tmp/ is ignored)."""
    out = []
    with os.scandir(tbp) as it:
        for e in it:
            ts = name_to_ts(e.name)
            if ts is not None and e.is_file():
                out.append((ts, e.name))
    out.sort()
    return out


def _remove(path: Path) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _read_bundle(tbp: Path, bad: Path, files: list[tuple[int, str]]) -> np.ndarray:
    """Read the bundle's files; a file that fails to parse is moved to bad/ and skipped."""
    rows = []
    for _, name in files:
        path = tbp / name
        try:
            rows.append(read_row(path))
        except (ValueError, OSError) as exc:
            print(f"[BAD     ] {name}: {exc} → bad/")
            try:
                os.replace(path, bad / name)
            except FileNotFoundError:
                pass
    return np.array(rows, dtype=np.float64).reshape(-1, N_COLS)


def _process_bundle(cut: int, files: list[tuple[int, str]], tbp: Path, bad: Path,
                    m_conn: sqlite3.Connection, i_conn: sqlite3.Connection) -> None:
    rows = _read_bundle(tbp, bad, files)
    n_min = 0
    if len(rows):
        min_ts, means, n_rows = one_min_means(rows, cut)
        minute_rows = [(int(t), int(n)) + tuple(float(v) for v in m)
                       for t, n, m in zip(min_ts, n_rows, means)]
        _commit(m_conn, i_conn, minute_rows, process(min_ts, means))
        n_min = len(min_ts)
    for _, name in files:            # only after both commits
        _remove(tbp / name)
    print(f"[OK      ] {ts_to_name(cut)[6:-4]}  rows {len(rows):3d}  minutes {n_min:2d}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(demo_root: Path, poll_s: float) -> None:
    tbp       = demo_root / 'to_be_processed'
    processed = demo_root / 'processed'
    bad       = demo_root / 'bad'
    eos       = demo_root / 'control' / 'EOS'
    for d in (tbp, processed, bad, eos.parent):
        d.mkdir(parents=True, exist_ok=True)

    m_conn = _open_db(processed / 'minutes.db', _MINUTES_DDL)
    i_conn = _open_db(processed / 'inference.db', _INFERENCE_DDL)

    # An EOS left by a finished run with nothing to drain would end this run at once.
    if eos.exists() and not _scan(tbp):
        eos.unlink()

    cut = _resume_cut(m_conn, i_conn)
    print(f"Reader started — {tbp}")
    print(f"Next cut: {ts_to_name(cut)[6:-4] if cut is not None else 'from the oldest file'}")

    next_tick = time.monotonic()
    while True:
        finished = eos.exists()          # read before scanning: every file written before EOS is seen
        files = _scan(tbp)

        if cut is None and files:
            cut = floor_bundle(files[0][0])

        if cut is not None:
            # Leftovers of a bundle committed before a crash: already in the databases.
            k = 0
            while k < len(files) and files[k][0] < cut:
                _remove(tbp / files[k][1])
                k += 1
            files = files[k:]

            # Complete bundles (all remaining ones after EOS), back to back.
            while files and (files[-1][0] >= cut + BUNDLE_S or finished):
                end = cut + BUNDLE_S
                k = 0
                while k < len(files) and files[k][0] < end:
                    k += 1
                if k == 0:                       # gap of whole bundles: jump to the next data
                    cut = floor_bundle(files[0][0])
                    continue
                _process_bundle(cut, files[:k], tbp, bad, m_conn, i_conn)
                files = files[k:]
                cut = end

        if finished and not files:
            print("EOS and nothing left — reader done.")
            break

        next_tick += poll_s
        now = time.monotonic()
        if next_tick <= now:                     # overran: skip missed ticks, stay on the grid
            next_tick += (int((now - next_tick) // poll_s) + 1) * poll_s
        time.sleep(next_tick - now)

    m_conn.close()
    i_conn.close()


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description='Renze backend reader (v2, stub processor)')
    ap.add_argument('--demo-root', type=Path, default=DEFAULT_DEMO_ROOT)
    ap.add_argument('--poll', type=float, default=POLL_S, metavar='SECS')
    args = ap.parse_args()
    run(args.demo_root, args.poll)


if __name__ == '__main__':
    main()
