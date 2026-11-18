"""
backfill.py — build the production minutes.db history from cleaned series6 cycles 1–8.

PARKED (2026-11-17): not part of the C9 demo. Kept here, tracked, until the production backfill
decision is made. It imports paths, db and packet_io from backend/ (one level up).

Production only (the demo database never holds history). Run once on the production machine,
from backend/:

    pip install pandas                      # the series6 files store pandas Timestamps
    python _parked/backfill.py --root /path/to/prod_root   # or RENZE_PROD_ROOT / renze_paths.json
    python _parked/backfill.py --root ... --dry-run        # counts only, writes nothing

- Source: <data-dir>/series6_cycle_{1..8}_raw.npy (col 0 = datetime, then the canonical 48 sensors),
  sampled every 30–60 s, downtime and rows below 300 kW already removed.
- Each minute = the mean of the samples in it; n_rows = number of samples (1–2 here, not 12).
- Every minute from the first to the last sample with no data becomes a zero placeholder row:
  all sensors 0.0, n_rows = 0 (so it can never be mistaken for real data).
- Timestamps are read as UTC unless --tz says otherwise (e.g. --tz Asia/Taipei).
- Inserts skip existing minutes, so running it twice changes nothing. The live reader never
  scores this history: inference starts at the first live minute.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # backend/: paths, db, packet_io

from db import INSERT_MINUTE, MINUTE_COLS, open_db
from packet_io import CANON_SENSOR_COLS, MIN_S, ts_to_name
from paths import HERE, layout, resolve_root

DEFAULT_DATA_DIR = HERE.parent.parent / 'AI_for_Renze' / '08-Data' / 'series6'
DEFAULT_CYCLES = '1-8'
BATCH = 50_000


def parse_cycles(spec: str) -> list[int]:
    out = []
    for part in spec.split(','):
        a, _, b = part.partition('-')
        out += list(range(int(a), int(b or a) + 1))
    return out


def load_cycle(data_dir: Path, c: int, tz: str) -> tuple[np.ndarray, np.ndarray]:
    import pandas as pd
    labels = [str(x) for x in np.load(data_dir / 'series6_column_labels.npy', allow_pickle=True)]
    if labels[0] != 'datetime' or labels[1:] != list(CANON_SENSOR_COLS):
        raise SystemExit('series6_column_labels.npy does not match the canonical 48 sensors')
    raw = np.load(data_dir / f'series6_cycle_{c}_raw.npy', allow_pickle=True)
    t = pd.to_datetime(raw[:, 0])
    t = t.tz_localize(tz).tz_convert('UTC') if t.tz is None else t.tz_convert('UTC')
    ts = t.tz_localize(None).values.astype('datetime64[s]').astype(np.int64)  # any pandas unit
    vals = raw[:, 1:].astype(np.float64)
    if not np.all(np.isfinite(vals)):
        raise SystemExit(f'cycle {c}: non-finite sensor values')
    return ts, vals


def main() -> None:
    ap = argparse.ArgumentParser(description='Backfill production minutes.db from series6 cycles')
    ap.add_argument('--root', type=Path, default=None, help='production root (see paths.py)')
    ap.add_argument('--data-dir', type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument('--cycles', default=DEFAULT_CYCLES, help='e.g. 1-8 or 1,2,5-8')
    ap.add_argument('--tz', default='UTC', help='time zone of the stored datetimes (default UTC)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    try:
        import pandas  # noqa: F401
    except ImportError:
        raise SystemExit('pandas is needed to read the series6 files: pip install pandas')

    ts_all, val_all = [], []
    for c in parse_cycles(args.cycles):
        ts, vals = load_cycle(args.data_dir, c, args.tz)
        print(f"cycle {c}: {len(ts):7,d} samples  {ts_to_name(ts[0])[6:-4]} → {ts_to_name(ts[-1])[6:-4]}")
        ts_all.append(ts)
        val_all.append(vals)
    ts = np.concatenate(ts_all)
    vals = np.concatenate(val_all)
    order = np.argsort(ts, kind='stable')
    ts, vals = ts[order], vals[order]

    minute = ts - ts % MIN_S
    m0, m1 = int(minute[0]), int(minute[-1])
    n_grid = (m1 - m0) // MIN_S + 1
    idx = (minute - m0) // MIN_S
    cnt = np.bincount(idx, minlength=n_grid)
    sums = np.zeros((n_grid, vals.shape[1]))
    np.add.at(sums, idx, vals)
    means = np.divide(sums, cnt[:, None], out=np.zeros_like(sums), where=cnt[:, None] > 0)
    n_real = int((cnt > 0).sum())
    print(f"minutes {ts_to_name(m0)[6:-4]} → {ts_to_name(m1)[6:-4]}: {n_grid:,} total, "
          f"{n_real:,} with data, {n_grid - n_real:,} zero placeholders "
          f"(≈ {n_grid * 0.4 / 1024:.0f} MB)")
    if args.dry_run:
        return

    root = resolve_root('prod', args.root)
    conn = open_db(layout(root)['minutes_db'], 'minutes', 'prod')
    assert MINUTE_COLS[:3] == ['ts', 'n_rows', 'n_filled']
    before = conn.execute('SELECT COUNT(*) FROM minutes').fetchone()[0]
    for b in range(0, n_grid, BATCH):
        rows = [(int(m0 + k * MIN_S), int(cnt[k]), 0) + tuple(float(v) for v in means[k])
                for k in range(b, min(n_grid, b + BATCH))]
        with conn:
            conn.executemany(INSERT_MINUTE, rows)
    after = conn.execute('SELECT COUNT(*) FROM minutes').fetchone()[0]
    conn.close()
    print(f"{root / 'processed' / 'minutes.db'}: {after - before:,} rows added ({after:,} in total)")


if __name__ == '__main__':
    main()
