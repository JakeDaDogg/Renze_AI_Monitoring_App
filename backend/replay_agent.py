"""
replay_agent.py — Renze demo writer (v3). Demo mode only; never touches production.

Replays the cycle 9 window as one CSV per 5-s row into demo_root/to_be_processed/
(contract in packet_io.py), paced by the speed scale (data time / wall time).

On start (unless --keep):
  - demo_root is replaced by a fresh, empty one (the demo database is never reused);
  - control/speed.json is written once: the scale is locked for the whole run.
While running:
  - control/writer_status.json = {"state": "running", "last_ts", "beat", "scale"} every
    60 s of data time (the heartbeat);
  - Ctrl-C or SIGTERM  → state "stopped";  end of the window → state "finished".

Start the writer first, then `python reader.py --mode demo`.

Usage:
    python replay_agent.py [--run-minutes 5 | --scale N] [--source PATH]
                           [--start T] [--end T] [--drop-range A:B] [--bad-range A:B]
                           [--keep] [--dry-run]
    T = YYYYMMDDTHHMMSSZ (UTC).  --drop-range: rows never written (source gap).
    --bad-range: rows written as unparseable files (tests forward fill / data error).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from paths import ASSETS, DEMO_ROOT, layout, preselect_schema, resolve_root

preselect_schema('demo')        # synth15 unless RENZE_SCHEMA is set (e.g. full49 for the C9 replay)

from packet_io import ROW_S, SCHEMA_NAME, ts_to_name, write_row  # noqa: E402

WINDOW_START = '20260427T000000Z'
WINDOW_END   = '20260518T000000Z'
DEFAULT_RUN_MINUTES = 5.0          # whole window in 5 min of wall time (≈ 6,048×)
MIN_RUN_MINUTES = 3.0              # fastest allowed (≈ 10,080×)
HEARTBEAT_DATA_S = 60              # status update every 60 s of data time
PROGRESS_DATA_S = 86_400           # one console line per data day

DEMO_ASSET = ASSETS / 'c9_window.npz'
FALLBACK_SOURCE = ASSETS / 'data' / 'series6_cycle_9_converted.npy'
SEE_MANIFEST = 'see demo_assets/MANIFEST.md'


def parse_utc(spec: str) -> int:
    for fmt in ('%Y%m%dT%H%M%SZ', '%Y%m%dT%H%MZ'):
        try:
            return int(datetime.strptime(spec, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f'invalid UTC time {spec!r} (YYYYMMDDTHHMMSSZ)')


def parse_range(spec: str) -> tuple[int, int]:
    a, sep, b = spec.partition(':')
    if not sep:
        raise argparse.ArgumentTypeError(f'expected START:END, got {spec!r}')
    lo, hi = parse_utc(a), parse_utc(b)
    if hi <= lo:
        raise argparse.ArgumentTypeError(f'empty range {spec!r}')
    return lo, hi


def load_source(path: Path | None) -> tuple[np.ndarray, Path]:
    """The demo asset (npz, key 'data') or a converted .npy; 50 columns, col 0 = epoch s."""
    for p in ([path] if path else [DEMO_ASSET, FALLBACK_SOURCE]):
        if p is not None and p.exists():
            if p.suffix == '.npz':
                with np.load(p) as z:
                    return z['data'], p
            return np.load(p, mmap_mode='r'), p
    if path:
        raise SystemExit(f'source not found: {path} ({SEE_MANIFEST})')
    raise SystemExit(f'no source found: build {DEMO_ASSET.name} with build_demo_assets.py from '
                     f'{FALLBACK_SOURCE} or pass --source ({SEE_MANIFEST})')


def write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix('.json.part')
    tmp.write_text(json.dumps(obj))
    os.replace(tmp, path)


def fresh_demo_root(root: Path) -> None:
    """Replace demo_root with an empty one. Only ever the demo root."""
    if root.resolve() != DEMO_ROOT.resolve():
        raise SystemExit(f'refusing to reset {root}: only {DEMO_ROOT} is a demo root')
    if root.exists():
        shutil.rmtree(root)


def run(args: argparse.Namespace) -> None:
    arr, src = load_source(args.source)
    ts_col = arr[:, 0]
    r0 = int(np.searchsorted(ts_col, args.start, side='left'))
    r1 = int(np.searchsorted(ts_col, args.end, side='left'))
    n = r1 - r0
    if n <= 0:
        raise SystemExit('no rows in the requested window')
    data_s = n * ROW_S
    if args.scale is not None:
        scale = float(args.scale)
    else:
        if args.run_minutes < MIN_RUN_MINUTES:
            raise SystemExit(f'--run-minutes must be >= {MIN_RUN_MINUTES} (the fastest demo)')
        scale = data_s / (args.run_minutes * 60.0)
    if scale < 1:
        raise SystemExit('scale must be >= 1 (1 = real time)')
    rate = scale / ROW_S
    print(f"Source {src.name}: rows {r0}–{r1} ({n:,} files), scale {scale:,.0f}× "
          f"→ {rate:,.0f} files/s, ≈ {data_s / scale / 60:.1f} min")
    if args.dry_run:
        return

    root = resolve_root('demo')
    if not args.keep:
        fresh_demo_root(root)
    d = layout(root)
    write_json(d['speed'], {'scale': scale, 'locked': True, 'schema': SCHEMA_NAME,
                            'written_utc': datetime.now(timezone.utc).isoformat()})

    stop = {'flag': False}

    def on_signal(signum, frame):
        stop['flag'] = True
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    def status(state: str, last_ts: int | None) -> None:
        write_json(d['status'], {'state': state, 'last_ts': last_ts, 'beat': last_ts,
                                 'scale': scale, 'wall_utc': datetime.now(timezone.utc).isoformat()})

    status('running', None)
    beat_every = max(1, HEARTBEAT_DATA_S // ROW_S)
    period = 1.0 / rate
    next_due = time.monotonic()
    t0 = time.monotonic()
    written = dropped = bad = 0
    last_ts = None
    for i in range(r0, r1):
        if stop['flag']:
            status('stopped', last_ts)
            print(f"Stopped at {ts_to_name(last_ts) if last_ts else '-'} — {written:,} files written")
            return
        next_due += period
        slack = next_due - time.monotonic()
        if slack > 0:
            time.sleep(slack)
        row = np.asarray(arr[i], dtype=np.float64)
        ts = int(row[0])
        if any(a <= ts < b for a, b in args.drop_range):
            dropped += 1
        else:
            name = ts_to_name(ts)
            part = d['tmp'] / (name + '.part')
            if any(a <= ts < b for a, b in args.bad_range):
                part.write_text('corrupted\n')
                bad += 1
            else:
                write_row(part, row)
            os.replace(part, d['tbp'] / name)
            written += 1
        last_ts = ts
        if (i - r0 + 1) % beat_every == 0:
            status('running', last_ts)
        if (ts - args.start) % PROGRESS_DATA_S == PROGRESS_DATA_S - ROW_S:
            print(f"  {ts_to_name(ts)[6:-4]}  {written:,} written  {time.monotonic() - t0:.0f} s")
    status('finished', last_ts)
    print(f"Finished — {written:,} files ({bad:,} bad), {dropped:,} dropped, "
          f"{time.monotonic() - t0:.0f} s")


def main() -> None:
    ap = argparse.ArgumentParser(description='Renze demo writer (v3)')
    ap.add_argument('--source', type=Path, default=None,
                    help=f'default: {DEMO_ASSET.name}, else the converted cycle 9 .npy')
    ap.add_argument('--start', type=parse_utc, default=parse_utc(WINDOW_START))
    ap.add_argument('--end', type=parse_utc, default=parse_utc(WINDOW_END))
    ap.add_argument('--run-minutes', type=float, default=DEFAULT_RUN_MINUTES,
                    help='wall minutes for the whole window (default 5, fastest 3)')
    ap.add_argument('--scale', type=float, default=None, help='data/wall time; overrides --run-minutes')
    ap.add_argument('--drop-range', type=parse_range, action='append', default=[], metavar='A:B')
    ap.add_argument('--bad-range', type=parse_range, action='append', default=[], metavar='A:B')
    ap.add_argument('--keep', action='store_true', help='keep the existing demo_root (resume)')
    ap.add_argument('--dry-run', action='store_true')
    run(ap.parse_args())


if __name__ == '__main__':
    main()
