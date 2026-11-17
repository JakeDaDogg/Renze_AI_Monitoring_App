"""
reader.py — Renze backend reader (v3): two tracks, isolated demo / production roots.

    python reader.py --mode demo            # demo_root next to backend/, scale from speed.json
    python reader.py --mode prod [--root P] # production root (see paths.py), scale 1

Each scan (every 60 s of data time, i.e. 60 / scale wall seconds):
  1. Writer status from control/writer_status.json (running / stopped / finished; none = running).
  2. List to_be_processed/ by name. Files below the minutes cursor were already committed: delete.
  3. Minutes track: every row before the open minute (the minute of the newest row) is read in
     chunks of at most one data day, averaged per minute, and committed to minutes.db (write 1);
     then its CSVs are deleted. A CSV that cannot be parsed goes to bad/ and its row becomes a
     copy of the previous good row (n_filled). More than 120 bad rows in a row (10 min) is a data
     error: everything before the stretch is committed and inferred, then the reader exits (code 2).
     A bad row with no previous good row (start of a run) counts as missing.
  4. Inference track: every real minute (n_rows > 0) in closed bundles is scored from a 15-minute
     window ending at that minute, read back from minutes.db (write 2). Missing minutes in a window
     are filled with the last real minute, up to 10 in a row; a window that would need more is skipped
     (cycle starts, outages, zero placeholder rows).
  5. stopped or stale (no new file and no status change for 1 h of data time) → exit with the open
     minute and open bundle kept; finished → flush everything, then exit.

Restart: the minutes cursor = last minute in minutes.db + 1 min; the inference cursor = bundle after
the last one in inference.db (or db_info 'infer_from', set by the first live minute). Inserts skip
existing timestamps, so a crash anywhere just redoes a chunk. SQLite errors retry after 1 s.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path

import numpy as np

from db import INSERT_INFERENCE, INSERT_MINUTE, get_info, max_ts, open_db, set_info
from packet_io import (BUNDLE_S, CANON_SENSOR_COLS, MIN_S, N_COLS, ROW_S, VCB2_IDX,
                       floor_bundle, floor_minute, name_to_ts, read_row, ts_to_name)
from paths import layout, resolve_root

SCAN_DATA_S   = 60        # scan cadence, data time
STALE_DATA_S  = 3600      # writer stale after this much data time with no sign of life
CHUNK_DATA_S  = 86_400    # at most one data day per read → write
BAD_RUN_MAX   = 120       # consecutive filled rows (10 min) before a data error
FILL_MAX_MIN  = 10        # missing minutes a window may fill from the last real minute
WINDOW_MIN    = 15        # model window, minutes
RETRY_S       = 1.0       # wall seconds before retrying a failed commit
STUB_VERSION  = 'stub-2xVCB2'
N_SENS = len(CANON_SENSOR_COLS)


class DataError(Exception):
    """Too many unparseable rows in a row."""


def tag(ts: int) -> str:
    return ts_to_name(ts)[6:-4]


# ── Processor (stub) ──────────────────────────────────────────────────────────

def process(targets: np.ndarray, windows: np.ndarray) -> list[tuple]:
    """
    targets: (k,) minute timestamps; windows: (k, 15, 48) 1-min means, the last row = the target.
    Stub: vcb2_x2 = 2 × the target minute's VCB2-Power; saved_power = 0.0 placeholder.
    Replace with the RUL models: scale, score the k windows in one call, smooth over 60 raw scores.
    """
    vcb2 = windows[:, -1, VCB2_IDX]
    return [(int(t), 2.0 * float(v), 0.0, STUB_VERSION) for t, v in zip(targets, vcb2)]


# ── Reader ────────────────────────────────────────────────────────────────────

class Reader:
    def __init__(self, mode: str, root: Path, scale: float, resume: bool = False):
        self.d = layout(root)
        self.mode, self.scale, self.resume = mode, scale, resume
        self.m = open_db(self.d['minutes_db'], 'minutes', mode)
        self.i = open_db(self.d['inference_db'], 'inference', mode)
        last_m = max_ts(self.m, 'minutes')
        self.mc = None if last_m is None else last_m + MIN_S           # minutes cursor
        last_i = max_ts(self.i, 'inference')
        start = get_info(self.i, 'infer_from')
        self.ic = (floor_bundle(last_i) + BUNDLE_S if last_i is not None
                   else int(start) if start is not None else None)       # inference cursor
        self.last_good: np.ndarray | None = None
        self.bad_run = 0
        self.run_start: int | None = None
        self.did_work = False
        self.last_key = None
        self.last_change = time.monotonic()

    # ── helpers ──
    def scan(self) -> list[tuple[int, str]]:
        out = []
        with os.scandir(self.d['tbp']) as it:
            for e in it:
                ts = name_to_ts(e.name)
                if ts is not None and e.is_file():
                    out.append((ts, e.name))
        out.sort()
        return out

    def status(self) -> dict | None:
        try:
            return json.loads(self.d['status'].read_text())
        except (OSError, ValueError):
            return None

    @staticmethod
    def commit(conn: sqlite3.Connection, sql: str, rows: list[tuple]) -> None:
        while True:
            try:
                with conn:
                    conn.executemany(sql, rows)
                return
            except sqlite3.Error as exc:
                print(f"[DB RETRY] {exc} — retrying in {RETRY_S:.0f} s")
                time.sleep(RETRY_S)

    def remove(self, name: str) -> None:
        try:
            os.remove(self.d['tbp'] / name)
        except FileNotFoundError:
            pass

    # ── minutes track ──
    def read_chunk(self, files: list[tuple[int, str]]) -> tuple[list, list, int | None]:
        """Rows (filled where bad) and their filled flags; stops early on a data error and then
        returns the ts where the bad stretch began."""
        rows, filled = [], []
        for ts, name in files:
            path = self.d['tbp'] / name
            try:
                row = read_row(path)
            except (ValueError, OSError) as exc:
                try:
                    os.replace(path, self.d['bad'] / name)
                except FileNotFoundError:
                    pass
                if self.last_good is None:
                    continue                                  # nothing to copy: missing
                if self.bad_run == 0:
                    self.run_start = ts
                self.bad_run += 1
                if self.bad_run > BAD_RUN_MAX:
                    keep = [k for k, r in enumerate(rows) if r[0] < self.run_start]
                    return [rows[k] for k in keep], [filled[k] for k in keep], self.run_start
                row = self.last_good.copy()
                row[0] = ts
                rows.append(row)
                filled.append(True)
                continue
            self.last_good = row
            self.bad_run = 0
            rows.append(row)
            filled.append(False)
        return rows, filled, None

    def write_minutes(self, rows: list, filled: list, start: int, end: int) -> int:
        if not rows:
            return 0
        a = np.array(rows, dtype=np.float64).reshape(-1, N_COLS)
        f = np.array(filled, dtype=bool)
        n_min = (end - start) // MIN_S
        idx = ((a[:, 0] - start) // MIN_S).astype(np.int64)
        cnt = np.bincount(idx, minlength=n_min)
        nfl = np.bincount(idx, weights=f.astype(float), minlength=n_min).astype(np.int64)
        sums = np.zeros((n_min, N_SENS))
        np.add.at(sums, idx, a[:, 1:1 + N_SENS])
        keep = np.flatnonzero(cnt)
        means = sums[keep] / cnt[keep, None]
        out = [(int(start + k * MIN_S), int(cnt[k]), int(nfl[k])) + tuple(float(v) for v in mu)
               for k, mu in zip(keep, means)]
        self.commit(self.m, INSERT_MINUTE, out)
        if self.ic is None and out:                    # first live minute: inference starts here
            self.ic = floor_bundle(out[0][0])
            set_info(self.i, 'infer_from', str(self.ic))
        return len(out)

    def minutes_track(self, files: list[tuple[int, str]], limit: int) -> list[tuple[int, str]]:
        while files and files[0][0] < limit:
            start = max(self.mc, floor_minute(files[0][0]))      # jump over gaps with no files
            end = min(limit, start + CHUNK_DATA_S)
            k = 0
            while k < len(files) and files[k][0] < end:
                k += 1
            chunk = files[:k]
            rows, filled, err_at = self.read_chunk(chunk)
            if err_at is not None:
                self.data_error(rows, filled, start, chunk, err_at)
            n = self.write_minutes(rows, filled, start, end)
            for ts, name in chunk:                    # bad ones were already moved to bad/
                self.remove(name)
            self.mc = end
            self.did_work = self.did_work or n > 0
            print(f"[MINUTES ] {tag(start)} → {tag(end)}  files {len(chunk):6d}  minutes {n:5d}")
            files = files[k:]
        return files

    def data_error(self, rows: list, filled: list, start: int, chunk: list, err_at: int) -> None:
        """Keep only what came before the bad stretch. Its first 10 min were already forward-filled
        (and maybe committed in earlier scans): remove those fully filled minutes and their
        inference rows, then raise DataError."""
        cut = floor_minute(err_at)
        if rows and start <= cut:
            self.write_minutes(rows, filled, start, cut + MIN_S)
        for ts, name in chunk:
            if ts < err_at:
                self.remove(name)
        gone = [r[0] for r in self.m.execute(
            'SELECT ts FROM minutes WHERE ts >= ? AND n_rows > 0 AND n_filled = n_rows', (cut,))]
        if gone:
            self.commit(self.m, 'DELETE FROM minutes WHERE ts = ?', [(t,) for t in gone])
            self.commit(self.i, 'DELETE FROM inference WHERE ts = ?', [(t,) for t in gone])
        last = max_ts(self.m, 'minutes')
        self.mc = cut if last is None else last + MIN_S
        print(f"[MINUTES ] data error: kept minutes up to {tag(self.mc)}, removed {len(gone)} filled")
        raise DataError(err_at)

    # ── inference track ──
    def inference_track(self, upto: int) -> None:
        """Score every real minute in [ic, upto)."""
        if self.ic is None:
            return
        while self.ic < upto:
            start, end = self.ic, min(upto, self.ic + CHUNK_DATA_S)
            g0 = start - (WINDOW_MIN - 1 + FILL_MAX_MIN) * MIN_S
            cur = self.m.execute(
                'SELECT * FROM minutes WHERE ts >= ? AND ts < ? ORDER BY ts', (g0, end))
            # columns: ts, ts_utc, n_rows, n_filled, 48 sensors
            data = cur.fetchall()
            n_grid = (end - g0) // MIN_S
            vals = np.full((n_grid, N_SENS), np.nan)
            real = np.zeros(n_grid, dtype=bool)
            for r in data:
                if r[2] > 0:
                    k = (r[0] - g0) // MIN_S
                    vals[k] = r[4:]
                    real[k] = True
            idx = np.arange(n_grid)
            last = np.maximum.accumulate(np.where(real, idx, -1))
            ok = real | ((last >= 0) & (idx - last <= FILL_MAX_MIN))
            filled = vals[np.maximum(last, 0)]
            bad_cum = np.concatenate([[0], np.cumsum(~ok)])
            first = (start - g0) // MIN_S
            targets = [k for k in range(first, n_grid)
                       if real[k] and k >= WINDOW_MIN - 1
                       and bad_cum[k + 1] - bad_cum[k + 1 - WINDOW_MIN] == 0]
            n_real = int(real[first:].sum())
            if targets:
                t = np.array(targets)
                win = np.stack([filled[k + 1 - WINDOW_MIN:k + 1] for k in targets])
                self.commit(self.i, INSERT_INFERENCE, process(g0 + t * MIN_S, win))
            if n_real:
                skipped = n_real - len(targets)
                print(f"[INFER   ] {tag(start)} → {tag(end)}  scored {len(targets):5d}"
                      + (f"  skipped {skipped} (window not fillable)" if skipped else ''))
            self.ic = end

    # ── main loop ──
    def run(self) -> int:
        scan_s = SCAN_DATA_S / self.scale
        stale_s = STALE_DATA_S / self.scale
        print(f"Reader [{self.mode}] {self.d['tbp'].parent}  scale {self.scale:,.0f}×  "
              f"scan {scan_s * 1000:.0f} ms")
        print(f"Minutes cursor: {tag(self.mc) if self.mc else 'from the oldest file'}   "
              f"inference cursor: {tag(self.ic) if self.ic else 'first live minute'}")
        next_tick = time.monotonic()
        while True:
            st = self.status()
            state = (st or {}).get('state', 'running')
            files = self.scan()

            key = (files[-1][0] if files else None, None if st is None else st.get('beat'), state)
            if key != self.last_key:
                self.last_key, self.last_change = key, time.monotonic()

            # a stopped/finished status left by an earlier run, with nothing to do: wait
            if state in ('stopped', 'finished') and not files and not self.did_work and not self.resume:
                state = 'waiting'
            finished = state == 'finished'

            if self.mc is None and files:
                self.mc = floor_minute(files[0][0])
            if self.mc is not None:
                k = 0
                while k < len(files) and files[k][0] < self.mc:     # already committed
                    self.remove(files[k][1])
                    k += 1
                files = files[k:]
                if files:
                    limit = floor_minute(files[-1][0]) + (MIN_S if finished else 0)
                    try:
                        files = self.minutes_track(files, limit)
                    except DataError as exc:
                        self.inference_track(self.mc)
                        print(f"DATA ERROR: more than {BAD_RUN_MAX} unparseable rows in a row from "
                              f"{tag(exc.args[0])}. Everything before it is committed; the files are "
                              f"in bad/. Check the source, then restart the reader.")
                        return 2
                self.inference_track(self.mc if finished else floor_bundle(self.mc))

            if finished and not files:
                print("Writer finished — everything written. Reader done.")
                return 0
            if state == 'stopped':
                print("Writer stopped — closed minutes and bundles written; the rest waits. Reader done.")
                return 0
            if state in ('running',) and time.monotonic() - self.last_change > stale_s:
                print(f"Writer silent for {STALE_DATA_S // 60} min of data time — treated as stopped. Reader done.")
                return 0

            next_tick += scan_s
            now = time.monotonic()
            if next_tick <= now:
                next_tick += (int((now - next_tick) // scan_s) + 1) * scan_s
            time.sleep(next_tick - now)


def read_scale(mode: str, d: dict, override: float | None, resume: bool) -> float:
    """Production: scale 1. Demo: the locked scale from speed.json, written by a writer that is
    running now (the writer resets demo_root on start, so the reader must open it after that).
    --resume accepts the files as they are (reader restarted mid-run or after the writer ended)."""
    if override is not None:
        return float(override)
    if mode == 'prod':
        return 1.0
    print('Waiting for a running writer (start replay_agent.py first) …')
    while True:
        try:
            scale = float(json.loads(d['speed'].read_text())['scale'])
            state = json.loads(d['status'].read_text()).get('state')
            if resume or state == 'running':
                return scale
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.2)


def main() -> None:
    ap = argparse.ArgumentParser(description='Renze backend reader (v3)')
    ap.add_argument('--mode', choices=('demo', 'prod'), required=True)
    ap.add_argument('--root', type=Path, default=None, help='override the data root')
    ap.add_argument('--scale', type=float, default=None,
                    help='data/wall time; default: speed.json (demo) or 1 (prod)')
    ap.add_argument('--resume', action='store_true',
                    help='demo: do not wait for a running writer (restart mid-run or drain a backlog)')
    args = ap.parse_args()
    root = resolve_root(args.mode, args.root)
    d = root / 'control'
    scale = read_scale(args.mode, {'speed': d / 'speed.json', 'status': d / 'writer_status.json'},
                       args.scale, args.resume)
    if scale < 1:
        raise SystemExit('scale must be >= 1')
    raise SystemExit(Reader(args.mode, root, scale, args.resume).run())


if __name__ == '__main__':
    main()
