"""
packet_io.py — shared file contract for the Renze replay agent and reader (v2).

v2 contract: one CSV per 5-s row
- Folder: demo_root/to_be_processed/
- Name:   renze_YYYYMMDDTHHMMSSZ.csv, the row's UTC timestamp. Alphabetical order = time order.
- Body:   header line `ts,<49 RAW_SENSOR_COLS>`, then one data line: integer epoch seconds and
          49 values with 9 significant digits, '.' decimal point, '\\n' line ends.
- Publish: the writer writes .tmp/<name>.part, then os.replace()s it into the folder, so the
          reader never sees a half-written file.

The reader bundles rows by data timestamp into [cut, cut + BUNDLE_S) windows, independent of
how many files there are.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ── Column definitions ────────────────────────────────────────────────────────

RAW_SENSOR_COLS: list[str] = [
    'VCB1-Power', 'VCB1-Voltage-LL-AVG', 'VCB1-Current-AVG', 'VCB1-PF',
    'VCB2-Power', 'VCB2-Voltage-LL-AVG', 'VCB2-Current-AVG', 'VCB2-PF',
    'VCB3-Power', 'VCB3-Voltage-LL-AVG', 'VCB3-Current-AVG', 'VCB3-PF',
    'PT100', 'PT101', 'PV101', 'PT203', 'TT203', 'LIT202', 'TT202A',
    'LIT101', 'LV101', 'TT101', 'TT202B', 'TT202C', 'PT102', 'PV102',
    'LIT102', 'FT102', 'LV102', 'FT103', 'TV103', 'TT103', 'LIT103',
    'PT106', 'PT104', 'TT104', 'VFDB-Power', 'VFDC-Frequency', 'VFDC-Power',
    'PT105', 'FT105', 'PT204', 'TT204', 'ENV-0', 'PT205', 'PT201',
    'TT205', 'TT201', 'PT104S',
]  # 49 names; PT104S is last (npy column 49)

# 48 canonical sensor names (PT104S dropped); used by reader, scoring, and SQLite
CANON_SENSOR_COLS: list[str] = RAW_SENSOR_COLS[:-1]

# Index of VCB2-Power within CANON_SENSOR_COLS
VCB2_IDX: int = CANON_SENSOR_COLS.index('VCB2-Power')  # 4

# 11 model feature indices into CANON_SENSOR_COLS (same list for pipe and HXG).
# Notebook 09-B has 16 names but the indices match the pipe list — model stays as trained.
MODEL_FEAT_INDICES: list[int] = [0, 4, 12, 13, 14, 19, 20, 21, 27, 29, 43]
MODEL_FEAT_COLS: list[str] = [CANON_SENSOR_COLS[i] for i in MODEL_FEAT_INDICES]

ROW_S: int = 5          # one data row every 5 s
MIN_S: int = 60         # 1-min samples
BUNDLE_S: int = 900     # reader bundle = 15 min of data (one model window)

N_COLS: int = 1 + len(RAW_SENSOR_COLS)   # 50: ts + 49 sensors
HEADER: str = 'ts,' + ','.join(RAW_SENSOR_COLS)

_NAME_RE = re.compile(r'^renze_(\d{8}T\d{6}Z)\.csv$')
_NAME_FMT = '%Y%m%dT%H%M%SZ'


# ── File name ↔ timestamp ─────────────────────────────────────────────────────

def ts_to_name(ts: int) -> str:
    """Canonical file name for a row's epoch timestamp (UTC)."""
    return f"renze_{datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(_NAME_FMT)}.csv"


def name_to_ts(name: str) -> int | None:
    """Epoch timestamp from a file name, or None if the name is not a packet file."""
    m = _NAME_RE.match(name)
    if not m:
        return None
    return int(datetime.strptime(m.group(1), _NAME_FMT).replace(tzinfo=timezone.utc).timestamp())


def floor_bundle(ts: int) -> int:
    """Start of the bundle that contains ts."""
    return int(ts) - int(ts) % BUNDLE_S


# ── Write ─────────────────────────────────────────────────────────────────────

def write_row(path: Path, row: np.ndarray) -> None:
    """Write one 50-value row (col 0 = epoch ts, cols 1–49 = RAW_SENSOR_COLS) to a CSV."""
    line = f"{int(row[0])}," + ','.join(f'{float(v):.9g}' for v in row[1:])
    with open(path, 'w', newline='\n') as fh:
        fh.write(HEADER + '\n' + line + '\n')


# ── Read and validate ─────────────────────────────────────────────────────────

def read_row(path: Path) -> np.ndarray:
    """
    Read and validate one packet file. Returns a (50,) float64 array.
    Raises ValueError if the file breaks the contract.
    """
    ts = name_to_ts(path.name)
    if ts is None:
        raise ValueError('name does not match the packet pattern')
    with open(path) as fh:
        lines = fh.read().splitlines()
    if len(lines) != 2 or lines[0] != HEADER:
        raise ValueError('expected the header line plus one data line')
    parts = lines[1].split(',')
    if len(parts) != N_COLS:
        raise ValueError(f'expected {N_COLS} values, got {len(parts)}')
    row = np.array([float(p) for p in parts], dtype=np.float64)  # float() raises ValueError
    if row[0] != ts or ts % ROW_S:
        raise ValueError('ts does not match the file name or the 5-s grid')
    if not np.all(np.isfinite(row[1:])):
        raise ValueError('non-finite sensor value')
    return row


# ── 1-minute means ────────────────────────────────────────────────────────────

def one_min_means(rows: np.ndarray, bundle_start: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    1-min means of one bundle's rows (n × 50, any n ≥ 1, all ts in [bundle_start, +BUNDLE_S)).

    Returns, for minutes that have at least one row (empty minutes are skipped):
        min_ts : (k,) int64   — minute start
        means  : (k, 48)      — mean over the rows present, PT104S dropped
        n_rows : (k,) int64   — rows behind each mean (12 = complete minute)
    """
    idx = ((rows[:, 0] - bundle_start) // MIN_S).astype(np.int64)
    min_ts, means, n_rows = [], [], []
    for m in range(BUNDLE_S // MIN_S):
        sel = idx == m
        n = int(sel.sum())
        if n:
            min_ts.append(bundle_start + m * MIN_S)
            means.append(rows[sel, 1:1 + len(CANON_SENSOR_COLS)].mean(axis=0))
            n_rows.append(n)
    return (np.array(min_ts, dtype=np.int64),
            np.array(means, dtype=np.float64).reshape(-1, len(CANON_SENSOR_COLS)),
            np.array(n_rows, dtype=np.int64))
