"""
build_demo_assets.py — cut the cycle 9 demo window into demo_assets/c9_window.npz.

The packaged app ships this file instead of the full converted cycle 9 .npy, and the replay
agent reads it by default. Values are kept as float64 (the CSV contract prints 9 significant
digits, which float32 cannot hold); the npz is compressed.

    python build_demo_assets.py [--source PATH] [--start T] [--end T]
"""
from __future__ import annotations

import argparse

import numpy as np

from replay_agent import DEMO_ASSET, FALLBACK_SOURCE, WINDOW_END, WINDOW_START, parse_utc


def main() -> None:
    ap = argparse.ArgumentParser(description='Build demo_assets/c9_window.npz')
    ap.add_argument('--source', default=str(FALLBACK_SOURCE))
    ap.add_argument('--start', type=parse_utc, default=parse_utc(WINDOW_START))
    ap.add_argument('--end', type=parse_utc, default=parse_utc(WINDOW_END))
    args = ap.parse_args()
    arr = np.load(args.source, mmap_mode='r')
    r0 = int(np.searchsorted(arr[:, 0], args.start, side='left'))
    r1 = int(np.searchsorted(arr[:, 0], args.end, side='left'))
    win = np.ascontiguousarray(arr[r0:r1], dtype=np.float64)
    if win.shape[1] != 50 or not np.all(np.isfinite(win)):
        raise SystemExit(f'unexpected source: shape {win.shape} or non-finite values')
    DEMO_ASSET.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(DEMO_ASSET, data=win)
    print(f"{DEMO_ASSET}: {win.shape[0]:,} rows, {DEMO_ASSET.stat().st_size / 1e6:.0f} MB")


if __name__ == '__main__':
    main()
