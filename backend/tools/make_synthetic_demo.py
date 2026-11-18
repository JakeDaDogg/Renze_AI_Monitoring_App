"""
make_synthetic_demo.py — build the shareable synthetic demo data from cleaned series6 cycles 4–6.

Runs once, on a machine that has the (internal, read-only) series6 files; the output is committed,
the inputs are not. Demo only: production reads real 5-s plant data with all 49 sensors.

    python tools/make_synthetic_demo.py [--series6-dir DIR] [--seed 0] [--out PATH] [--plots DIR]

Input: <series6-dir>/series6_cycle_{4,5,6}_raw.npy + series6_column_labels.npy
       (default ~/Desktop/BALA/AI_for_Renze/08-Data/series6, or RENZE_SERIES6_DIR).
       Sampled every 60 s; downtime and rows < 300 kW were already removed (gaps).

Method:
  1. Cleaning dates C4–C6 from the training config of AI_for_Renze/09-RUL Model/
     05-RUL_Pipe_Model_TrainDev.ipynb (CYCLES; pipe and HXG share them). Printed next to each file's
     last timestamp; if they differ by more than 1 h the notebook date is used (later rows dropped).
  2. Per cycle, an operating-time axis counted backwards from the cleaning date: each interval
     between consecutive samples (and from the last sample to the cleaning date) adds its length,
     intervals > 5 min add 0. The 15 synth15 sensors are put on a 1-min grid of operating minutes
     (mean of the samples in each minute, empty minutes linearly interpolated); the last 10
     operating days (14,400 minutes) are kept.
  3. The three cycles are aligned on operating minutes-before-cleaning: C4[m], C5[m], C6[m].
  4. Each 5-s row of minute m is a random weighted average w4·C4[m] + w5·C5[m] + w6·C6[m],
     w ~ Dirichlet(1, 1, 1) drawn fresh per row, the same w for all 15 sensors of the row.
     No other noise, no clipping (every value stays inside the three cycles' range).
  5. Shutdown tail, 60 min = 720 rows: VCB1-Power and VCB2-Power of each cycle replaced by a
     few kW (uniform 0–5 kW per cycle and minute), other sensors = each cycle's last-minute
     values; then the same random weighting.
  6. Timestamps: 2000-01-01T00:00:00Z every 5 s, no gaps: 14,400 × 12 + 720 = 173,520 rows.

Output: demo_assets/synthetic/renze_synth_c456_v1.npz with ts (int64), X (float32, 173,520 × 15),
columns, seed, weights, source_cycles, cleaning_dates, build_date. Quick-look PNGs (synthetic 1-min
means vs the three cycles) go to demo_assets/synthetic_plots/ (ignored by git).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # backend/
from paths import ASSETS  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────────────

SYNTH15_COLS = [
    'VCB1-Power', 'VCB2-Power', 'PT100', 'PT101', 'PV101', 'TT203', 'LIT101', 'LV101',
    'TT101', 'FT102', 'LV102', 'FT103', 'PT106', 'PT105', 'ENV-0',
]  # = packet_io.SYNTH15_COLS (not imported, so the schema choice of this process does not matter)

CYCLES = (4, 5, 6)
# 05-RUL_Pipe_Model_TrainDev.ipynb, cell 4, CYCLES[c][1] (cycle end = pipe cleaning date).
# Naive datetimes, same clock as the series6 files (Taiwan local time).
CLEANING = {
    4: datetime(2025, 4, 21, 0, 0),
    5: datetime(2025, 5, 20, 0, 0),
    6: datetime(2025, 6, 17, 0, 0),
}
DATE_TOL_S = 3600            # notebook date vs last timestamp: report if further apart
GAP_S = 300                  # intervals longer than this are not operating time
KEEP_MIN = 10 * 1440         # last 10 operating days
ROWS_PER_MIN = 12            # 5-s rows
TAIL_MIN = 60                # shutdown tail
TAIL_POWER_KW = (0.0, 5.0)   # VCB1/VCB2 per cycle during the tail
POWER_COLS = ('VCB1-Power', 'VCB2-Power')
START_TS = 946_684_800       # 2000-01-01T00:00:00Z
ROW_S = 5
DIRICHLET = (1.0, 1.0, 1.0)

DEFAULT_SERIES6 = Path.home() / 'Desktop' / 'BALA' / 'AI_for_Renze' / '08-Data' / 'series6'
OUT = ASSETS / 'synthetic' / 'renze_synth_c456_v1.npz'
PLOTS = ASSETS / 'synthetic_plots'

GROUPS = {
    'power': ['VCB1-Power', 'VCB2-Power'],
    'pressure': ['PT100', 'PT101', 'PT105', 'PT106'],
    'temperature': ['TT101', 'TT203'],
    'level_valve': ['LIT101', 'LV101', 'LV102', 'PV101'],
    'flow_env': ['FT102', 'FT103', 'ENV-0'],
}


# ── Steps ─────────────────────────────────────────────────────────────────────

def load_cycle(d: Path, c: int) -> tuple[np.ndarray, np.ndarray]:
    """Epoch-like seconds of the naive timestamps (no zone shift) and the 15 sensors."""
    import pandas as pd
    labels = [str(x) for x in np.load(d / 'series6_column_labels.npy', allow_pickle=True)]
    raw = np.load(d / f'series6_cycle_{c}_raw.npy', allow_pickle=True)
    t = pd.to_datetime(raw[:, 0])
    ts = t.values.astype('datetime64[s]').astype(np.int64)
    X = raw[:, [labels.index(k) for k in SYNTH15_COLS]].astype(np.float64)
    if not np.all(np.isfinite(X)) or np.any(np.diff(ts) <= 0):
        raise SystemExit(f'cycle {c}: non-finite values or unsorted timestamps')
    return ts, X


def operating_grid(ts: np.ndarray, X: np.ndarray, clean_s: int) -> tuple[np.ndarray, int]:
    """(KEEP_MIN, 15) 1-min grid in forward time (row -1 = the minute just before cleaning) and
    the number of empty minutes that were interpolated."""
    keep = ts <= clean_s
    ts, X = ts[keep], X[keep]
    step = np.diff(np.append(ts, clean_s)).astype(np.float64)       # interval after each sample
    step[step > GAP_S] = 0.0
    before = np.cumsum(step[::-1])[::-1]                            # operating s before cleaning
    k = np.floor(before / 60.0).astype(np.int64)                    # 0 = last operating minute
    if k.max() < KEEP_MIN - 1:
        raise SystemExit(f'only {k.max() + 1} operating minutes, need {KEEP_MIN}')
    sel = k < KEEP_MIN
    k, X = k[sel], X[sel]
    cnt = np.bincount(k, minlength=KEEP_MIN)
    sums = np.zeros((KEEP_MIN, X.shape[1]))
    np.add.at(sums, k, X)
    have = cnt > 0
    grid = np.empty_like(sums)
    grid[have] = sums[have] / cnt[have, None]
    idx = np.arange(KEEP_MIN)
    for j in range(X.shape[1]):
        grid[~have, j] = np.interp(idx[~have], idx[have], grid[have, j])
    return grid[::-1], int((~have).sum())                           # forward time


def build(cyc: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """cyc: (3, n_min, 15) aligned cycles → (n_min × 12, 15) Dirichlet-weighted rows."""
    n_min = cyc.shape[1]
    w = rng.dirichlet(DIRICHLET, size=(n_min, ROWS_PER_MIN))       # (n_min, 12, 3)
    rows = np.einsum('mrc,cms->mrs', w, cyc)                        # (n_min, 12, 15)
    return rows.reshape(n_min * ROWS_PER_MIN, cyc.shape[2])


def tail_cycles(cyc: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """(3, TAIL_MIN, 15): each cycle's last-minute values, powers replaced by a few kW."""
    t = np.repeat(cyc[:, -1:, :], TAIL_MIN, axis=1).copy()
    for name in POWER_COLS:
        j = SYNTH15_COLS.index(name)
        t[:, :, j] = rng.uniform(*TAIL_POWER_KW, size=(cyc.shape[0], TAIL_MIN))
    return t


def plots(out_dir: Path, cyc: np.ndarray, X: np.ndarray) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out_dir.mkdir(parents=True, exist_ok=True)
    n_min = X.shape[0] // ROWS_PER_MIN
    means = X.reshape(n_min, ROWS_PER_MIN, -1).mean(1)
    days = (np.arange(n_min) - KEEP_MIN) / 1440.0                    # 0 = cleaning, tail > 0
    full = np.concatenate([cyc, np.full((3, TAIL_MIN, cyc.shape[2]), np.nan)], axis=1)
    for g, names in GROUPS.items():
        fig, axes = plt.subplots(len(names), 1, figsize=(12, 2.6 * len(names)), sharex=True)
        for ax, name in zip(np.atleast_1d(axes), names):
            j = SYNTH15_COLS.index(name)
            for c, col in zip(range(3), ('tab:blue', 'tab:orange', 'tab:green')):
                ax.plot(days, full[c, :, j], lw=0.5, alpha=0.6, color=col, label=f'C{CYCLES[c]}')
            ax.plot(days, means[:, j], lw=0.7, color='black', label='synthetic 1-min mean')
            ax.set_ylabel(name)
        np.atleast_1d(axes)[0].legend(loc='upper left', ncol=4, fontsize=8)
        np.atleast_1d(axes)[-1].set_xlabel('operating days relative to cleaning (tail after 0)')
        fig.tight_layout()
        fig.savefig(out_dir / f'synth_{g}.png', dpi=110)
        plt.close(fig)
    print(f'plots: {out_dir}/synth_*.png')


def main() -> None:
    ap = argparse.ArgumentParser(description='Build demo_assets/synthetic/renze_synth_c456_v1.npz')
    ap.add_argument('--series6-dir', type=Path,
                    default=Path(os.environ.get('RENZE_SERIES6_DIR', DEFAULT_SERIES6)))
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', type=Path, default=OUT)
    ap.add_argument('--plots', type=Path, default=PLOTS, help='quick-look PNGs (not committed)')
    ap.add_argument('--no-plots', action='store_true')
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    grids, used = [], {}
    for c in CYCLES:
        ts, X = load_cycle(args.series6_dir, c)
        nb = CLEANING[c]
        nb_s = int(np.datetime64(nb, 's').astype(np.int64))
        last = np.datetime64(int(ts[-1]), 's').astype(datetime)
        diff_h = (ts[-1] - nb_s) / 3600
        note = ''
        if abs(ts[-1] - nb_s) > DATE_TOL_S:
            note = f'  → differ by {diff_h:+.2f} h: notebook date used, {int((ts > nb_s).sum())} later samples dropped'
        print(f'C{c}: notebook cleaning {nb:%Y-%m-%d %H:%M}  file last {last:%Y-%m-%d %H:%M:%S}{note}')
        grid, n_interp = operating_grid(ts, X, nb_s)
        print(f'     10 operating days: {KEEP_MIN} minutes, {n_interp} interpolated')
        grids.append(grid)
        used[c] = nb.isoformat(timespec='minutes')
    cyc = np.stack(grids)                                           # (3, 14400, 15)

    X = np.concatenate([build(cyc, rng), build(tail_cycles(cyc, rng), rng)]).astype(np.float32)
    n = X.shape[0]
    ts = START_TS + ROW_S * np.arange(n, dtype=np.int64)
    assert n == (KEEP_MIN + TAIL_MIN) * ROWS_PER_MIN == 173_520 and np.all(np.isfinite(X))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out, ts=ts, X=X, columns=np.array(SYNTH15_COLS), seed=np.int64(args.seed),
        weights=np.array('Dirichlet(1,1,1) per 5-s row'),
        source_cycles=np.array(CYCLES, dtype=np.int64),
        cleaning_dates=np.array([f'C{c} {used[c]}' for c in CYCLES]),
        build_date=np.array(date.today().isoformat()))
    print(f'{args.out}: {n:,} rows × {X.shape[1]} sensors, {args.out.stat().st_size / 1e6:.1f} MB')
    if not args.no_plots:
        plots(args.plots, cyc, X)


if __name__ == '__main__':
    main()
