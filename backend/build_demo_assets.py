"""
build_demo_assets.py — cut the cycle 9 demo window into demo_assets/c9_window.npz.

The packaged app ships this file instead of the full converted cycle 9 .npy, and the replay
agent reads it by default. Values are kept as float64 (the CSV contract prints 9 significant
digits, which float32 cannot hold); the npz is compressed.

    RENZE_SCHEMA=full49 python build_demo_assets.py [--source PATH] [--start T] [--end T]

The C9 window is full49 data. Under the demo default schema synth15 there is nothing to build:
replay_agent.py reads demo_assets/synthetic/renze_synth_c456_v1.npz directly, so this script only
checks that file and exits.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from paths import preselect_schema

preselect_schema('demo')        # synth15 unless RENZE_SCHEMA is set; before packet_io is imported

from packet_io import N_COLS, SCHEMA_NAME  # noqa: E402
from replay_agent import (DEMO_ASSET, FALLBACK_SOURCE, SEE_MANIFEST, SYNTH_SOURCE,  # noqa: E402
                          WINDOW_END, WINDOW_START, load_source, parse_utc)


def main() -> None:
    ap = argparse.ArgumentParser(description='Build demo_assets/c9_window.npz')
    ap.add_argument('--source', type=Path, default=FALLBACK_SOURCE,
                    help='default: demo_assets/data/series6_cycle_9_converted.npy')
    ap.add_argument('--start', type=parse_utc, default=parse_utc(WINDOW_START))
    ap.add_argument('--end', type=parse_utc, default=parse_utc(WINDOW_END))
    args = ap.parse_args()
    if SCHEMA_NAME == 'synth15':
        arr, _ = load_source(None)
        print(f"synth15: replay_agent.py reads {SYNTH_SOURCE.name} directly ({arr.shape[0]:,} rows); "
              f"nothing to build. The C9 window: RENZE_SCHEMA=full49 python build_demo_assets.py")
        return
    if not args.source.exists():
        raise SystemExit(f'source not found: {args.source} ({SEE_MANIFEST})')
    arr = np.load(args.source, mmap_mode='r')
    r0 = int(np.searchsorted(arr[:, 0], args.start, side='left'))
    r1 = int(np.searchsorted(arr[:, 0], args.end, side='left'))
    win = np.ascontiguousarray(arr[r0:r1], dtype=np.float64)
    if win.shape[1] != N_COLS or not np.all(np.isfinite(win)):
        raise SystemExit(f'unexpected source: shape {win.shape} or non-finite values')
    DEMO_ASSET.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(DEMO_ASSET, data=win)
    print(f"{DEMO_ASSET}: {win.shape[0]:,} rows, {DEMO_ASSET.stat().st_size / 1e6:.0f} MB")


if __name__ == '__main__':
    main()
