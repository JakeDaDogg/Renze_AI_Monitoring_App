"""
replay_agent.py — Renze C9 replay agent (v2): one CSV per 5-s row, one replay rate.

Reads series6_cycle_9_converted.npy and publishes each 5-s row as its own file in
demo_root/to_be_processed/ (contract in packet_io.py), paced on a monotonic clock.
Writes control/EOS when done, so the reader can flush the last bundle and exit.

Usage:
    python replay_agent.py [options]

    --rate N            rows per second of wall time (default 1350 ≈ 4.5 min for C9)
    --duration SECS     target run time; overrides --rate
    --start / --end     UTC window, YYYYMMDDTHHMMSSZ (or YYYYMMDDTHHMMZ); default = C9 demo window.
                        Use --start to resume a stopped writer where it left off.
    --drop-range A:B    rows with A <= ts < B are never written (tests a source gap); repeatable
    --dry-run           print the plan, write nothing
    --demo-root PATH    root folder (default: ../demo_root relative to this file)
    --source PATH       source .npy file (default: AI_for_Renze/08-Data/…)
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from packet_io import ts_to_name, write_row

# Demo window (UTC)
WINDOW_START = '20260427T000000Z'
WINDOW_END   = '20260518T000000Z'
DEFAULT_RATE = 1350.0          # rows/s: 362,880 rows in ≈ 4.5 min
PROGRESS_EVERY = 17_280        # rows = one data day

_HERE = Path(__file__).parent
DEFAULT_DEMO_ROOT = _HERE.parent / 'demo_root'
DEFAULT_SOURCE = (
    _HERE.parent.parent / 'AI_for_Renze' / '08-Data'
    / 'series6_cycle_9_converted.npy'
)


def parse_utc(spec: str) -> int:
    for fmt in ('%Y%m%dT%H%M%SZ', '%Y%m%dT%H%MZ'):
        try:
            return int(datetime.strptime(spec, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f'invalid UTC time {spec!r} (YYYYMMDDTHHMMSSZ)')


def parse_range(spec: str) -> tuple[int, int]:
    parts = spec.split(':')
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f'expected START:END, got {spec!r}')
    a, b = parse_utc(parts[0]), parse_utc(parts[1])
    if b <= a:
        raise argparse.ArgumentTypeError(f'empty range {spec!r}')
    return a, b


def run(source: Path, demo_root: Path, start: int, end: int, rate: float,
        duration: float | None, drops: list[tuple[int, int]], dry_run: bool) -> None:
    tbp     = demo_root / 'to_be_processed'
    tmp     = tbp / '.tmp'
    control = demo_root / 'control'
    eos     = control / 'EOS'

    print(f"Loading {source} …")
    arr = np.load(source, mmap_mode='r')
    ts_col = arr[:, 0]
    r0 = int(np.searchsorted(ts_col, start, side='left'))
    r1 = int(np.searchsorted(ts_col, end, side='left'))
    n = r1 - r0
    if n <= 0:
        raise SystemExit('no rows in the requested window')
    if duration is not None:
        rate = n / duration
    print(f"Rows {r0}–{r1} ({n:,} files)  rate {rate:.0f}/s  ≈ {n / rate / 60:.1f} min"
          f"  drop ranges: {len(drops)}")
    if dry_run:
        return

    for d in (tbp, tmp, control):
        d.mkdir(parents=True, exist_ok=True)
    if eos.exists():
        eos.unlink()                      # stale marker from a previous run

    period = 1.0 / rate
    next_due = time.monotonic()
    written = skipped = 0
    t0 = time.monotonic()
    for i in range(r0, r1):
        next_due += period
        slack = next_due - time.monotonic()
        if slack > 0:
            time.sleep(slack)
        row = np.asarray(arr[i])
        ts = int(row[0])
        if any(a <= ts < b for a, b in drops):
            skipped += 1
            continue
        name = ts_to_name(ts)
        part = tmp / (name + '.part')
        write_row(part, row)
        os.replace(part, tbp / name)
        written += 1
        if written % PROGRESS_EVERY == 0:
            print(f"  {name}  {written:,} written  {time.monotonic() - t0:.0f} s")

    eos.touch()
    print(f"EOS written — {written:,} files, {skipped:,} dropped, {time.monotonic() - t0:.0f} s")


def main() -> None:
    ap = argparse.ArgumentParser(description='Renze C9 replay agent (v2, one file per 5-s row)')
    ap.add_argument('--demo-root',  type=Path,  default=DEFAULT_DEMO_ROOT)
    ap.add_argument('--source',     type=Path,  default=DEFAULT_SOURCE)
    ap.add_argument('--start',      type=parse_utc, default=parse_utc(WINDOW_START))
    ap.add_argument('--end',        type=parse_utc, default=parse_utc(WINDOW_END))
    ap.add_argument('--rate',       type=float, default=DEFAULT_RATE, metavar='N')
    ap.add_argument('--duration',   type=float, default=None, metavar='SECS')
    ap.add_argument('--drop-range', type=parse_range, action='append', default=[], metavar='A:B')
    ap.add_argument('--dry-run',    action='store_true')
    args = ap.parse_args()
    run(args.source, args.demo_root, args.start, args.end, args.rate,
        args.duration, args.drop_range, args.dry_run)


if __name__ == '__main__':
    main()
