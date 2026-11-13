"""
replay_agent.py — demo replay agent for the Renze C9 demo.

Reads series6_cycle_9_converted.npy and drops one quarter-hour packet per wall-clock
interval into demo_root/inbox/ at the configured rate.

Usage:
    python replay_agent.py [options]

    --dry-run           print schedule and estimated time, write nothing
    --op-rate N         packets/s for operating data (default 5)
    --offline-rate N    packets/s for offline/downtime data (default 100)
    --duration SECS     target run duration; overrides --op-rate
    --demo-root PATH    root folder (default: ../demo_root relative to this file)
    --source PATH       source .npy file (default: AI_for_Renze/08-Data/…)
    --drop-quarters YYYYMMDDTHHMMZ [...]
    --late-quarters YYYYMMDDTHHMMZ:N [...]
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from packet_io import (
    ROWS_PER_PACKET,
    VCB2_IDX,
    name_to_quarter,
    quarter_to_name,
    write_packet,
)

# Demo window (UTC epoch seconds)
WINDOW_START = int(datetime(2026, 4, 27, 0, 0, 0, tzinfo=timezone.utc).timestamp())
WINDOW_END   = int(datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc).timestamp())

# VCB2-Power column index in the full 50-column npy array (col 0 = ts, so +1)
_VCB2_NPY_COL = VCB2_IDX + 1  # 5

OFFLINE_KW = 10.0  # mean VCB2-Power below this → offline (agent pacing only)

_HERE = Path(__file__).parent
DEFAULT_DEMO_ROOT = _HERE.parent / 'demo_root'
DEFAULT_SOURCE = (
    _HERE.parent.parent / 'AI_for_Renze' / '08-Data'
    / 'series6_cycle_9_converted.npy'
)


# ── Schedule helpers ──────────────────────────────────────────────────────────

def _build_schedule(
    arr: np.ndarray,
    start_row: int,
    end_row: int,
    op_rate: float,
    offline_rate: float,
) -> list[dict]:
    """Return one descriptor per packet in time order (no drop/late applied yet)."""
    schedule = []
    quarter = WINDOW_START
    row = start_row
    while row < end_row:
        rows = arr[row: row + ROWS_PER_PACKET]
        mean_vcb2 = float(rows[:, _VCB2_NPY_COL].mean())
        is_offline = mean_vcb2 < OFFLINE_KW
        schedule.append({
            'quarter': quarter,
            'name': quarter_to_name(quarter),
            'row': row,
            'state': 'offline' if is_offline else 'operating',
            'mean_vcb2': mean_vcb2,
            'rate': offline_rate if is_offline else op_rate,
        })
        quarter += 900
        row += ROWS_PER_PACKET
    return schedule


def _build_write_map(
    schedule: list[dict],
    drop_quarters: set[int],
    late_quarters: dict[int, int],
) -> dict[int, tuple[dict, bool]]:
    """
    Map slot_index → (packet_info, is_late).
    Dropped packets are absent; late packets shift to natural_index + N.
    """
    result: dict[int, tuple[dict, bool]] = {}
    for i, p in enumerate(schedule):
        q = p['quarter']
        if q in drop_quarters:
            pass
        elif q in late_quarters:
            result[i + late_quarters[q]] = (p, True)
        else:
            result[i] = (p, False)
    return result


# ── Packet write ──────────────────────────────────────────────────────────────

def _write_one(
    arr: np.ndarray,
    p: dict,
    inbox: Path,
    tmp: Path,
    control: Path,
    seq: int,
    is_late: bool,
) -> None:
    rows = arr[p['row']: p['row'] + ROWS_PER_PACKET].copy()
    name = p['name']
    part = tmp / (name + '.part')
    dest = inbox / name
    write_packet(part, rows)
    os.replace(part, dest)
    status = {
        'seq': seq,
        'quarter': name,
        'state': p['state'],
        'wall_time': datetime.now(tz=timezone.utc).isoformat(),
        'late': is_late,
    }
    with open(control / 'agent_status.json', 'w') as fh:
        json.dump(status, fh)


# ── Main run ──────────────────────────────────────────────────────────────────

def run(
    source: Path,
    demo_root: Path,
    op_rate: float,
    offline_rate: float,
    duration: float | None,
    drop_quarters: set[int],
    late_quarters: dict[int, int],
    dry_run: bool,
) -> None:
    inbox   = demo_root / 'inbox'
    tmp     = inbox / '.tmp'
    control = demo_root / 'control'

    if not dry_run:
        for d in [inbox, tmp, inbox / 'processed', inbox / 'rejected', control]:
            d.mkdir(parents=True, exist_ok=True)

    print(f"Loading {source} …")
    arr = np.load(source, mmap_mode='r')
    ts_col = arr[:, 0]

    start_row = int(np.searchsorted(ts_col, WINDOW_START, side='left'))
    end_row   = int(np.searchsorted(ts_col, WINDOW_END,   side='left'))
    n_packets = (end_row - start_row) // ROWS_PER_PACKET
    print(f"Window rows {start_row}–{end_row}  ({n_packets} packets)")

    schedule = _build_schedule(arr, start_row, end_row, op_rate, offline_rate)

    # Adjust op_rate if duration target is set
    op_count = sum(1 for p in schedule if p['state'] == 'operating')
    if duration is not None and op_count > 0:
        op_rate = op_count / duration
        for p in schedule:
            if p['state'] == 'operating':
                p['rate'] = op_rate

    off_count = sum(1 for p in schedule if p['state'] == 'offline')
    est_op  = op_count  / op_rate      if op_rate      > 0 else 0.0
    est_off = off_count / offline_rate if offline_rate > 0 else 0.0
    print(
        f"Est. run: {est_op:.0f}s operating + {est_off:.0f}s offline"
        f"  ≈ {(est_op + est_off) / 60:.1f} min"
        f"  |  drop={len(drop_quarters)}  late={len(late_quarters)}"
    )

    if dry_run:
        print('\n[dry-run] First 8 packets:')
        for p in schedule[:8]:
            print(
                f"  {p['name']}  {p['state']:9s}  "
                f"vcb2={p['mean_vcb2']:7.1f} kW  rate={p['rate']}/s"
            )
        print('  …')
        return

    write_map = _build_write_map(schedule, drop_quarters, late_quarters)
    max_slot  = max(write_map, default=len(schedule) - 1)

    next_due = time.monotonic()
    seq = 0

    for slot in range(max_slot + 1):
        # Rate for this slot: use natural schedule position if available
        rate = schedule[slot]['rate'] if slot < len(schedule) else op_rate
        next_due += 1.0 / rate
        slack = next_due - time.monotonic()
        if slack > 0:
            time.sleep(slack)

        if slot in write_map:
            p, is_late = write_map[slot]
            seq += 1
            _write_one(arr, p, inbox, tmp, control, seq, is_late)

    (control / 'EOS').touch()
    print('EOS written — replay agent done.')


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_drop(spec: str) -> int:
    q = name_to_quarter(f'renze_{spec}.csv')
    if q is None:
        raise argparse.ArgumentTypeError(f'invalid quarter {spec!r}')
    return q


def _parse_late(spec: str) -> tuple[int, int]:
    parts = spec.split(':')
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f'expected YYYYMMDDTHHMMZ:N, got {spec!r}')
    q = name_to_quarter(f'renze_{parts[0]}.csv')
    if q is None:
        raise argparse.ArgumentTypeError(f'invalid quarter {parts[0]!r}')
    return q, int(parts[1])


def main() -> None:
    ap = argparse.ArgumentParser(description='Renze C9 demo replay agent')
    ap.add_argument('--demo-root',     type=Path,  default=DEFAULT_DEMO_ROOT)
    ap.add_argument('--source',        type=Path,  default=DEFAULT_SOURCE)
    ap.add_argument('--dry-run',       action='store_true')
    ap.add_argument('--op-rate',       type=float, default=5.0,   metavar='N')
    ap.add_argument('--offline-rate',  type=float, default=100.0, metavar='N')
    ap.add_argument('--duration',      type=float, default=None,  metavar='SECS')
    ap.add_argument('--drop-quarters', nargs='*',  type=_parse_drop, default=[],
                    metavar='YYYYMMDDTHHMMZ')
    ap.add_argument('--late-quarters', nargs='*',  type=_parse_late, default=[],
                    metavar='YYYYMMDDTHHMMZ:N')
    args = ap.parse_args()

    run(
        source=args.source,
        demo_root=args.demo_root,
        op_rate=args.op_rate,
        offline_rate=args.offline_rate,
        duration=args.duration,
        drop_quarters=set(args.drop_quarters),
        late_quarters=dict(args.late_quarters),
        dry_run=args.dry_run,
    )


if __name__ == '__main__':
    main()
