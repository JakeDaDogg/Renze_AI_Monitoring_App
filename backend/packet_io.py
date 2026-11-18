"""
packet_io.py — shared file contract for the Renze replay agent and reader (v2).

v2 contract: one CSV per 5-s row
- Folder: demo_root/to_be_processed/
- Name:   renze_YYYYMMDDTHHMMSSZ.csv, the row's UTC timestamp. Alphabetical order = time order.
- Body:   header line `ts,<RAW_SENSOR_COLS>`, then one data line: integer epoch seconds and
          one value per sensor with 9 significant digits, '.' decimal point, '\\n' line ends.
          The sensor list is the active schema: full49 (production) or synth15 (demo), see below.
- Publish: the writer writes .tmp/<name>.part, then os.replace()s it into the folder, so the
          reader never sees a half-written file.

The reader bundles rows by data timestamp into [cut, cut + BUNDLE_S) windows, independent of
how many files there are.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ── Column definitions: two named schemas, chosen once per process ─────────────
#
# full49  — the production plant feed: 49 sensors, PT104S last. Default for --mode prod.
# synth15 — the shareable demo: 11 model sensors + 4 extra sensors of the daily decision,
#           no PT104S. Default for --mode demo. Demo only; production never uses it.
#
# Selection: environment variable RENZE_SCHEMA (full49 | synth15), read once when this module is
# first imported. Entry scripts set the mode default with paths.preselect_schema(mode) before they
# import packet_io or db; an explicit RENZE_SCHEMA always wins. Unset everywhere → full49.
# Everything below is derived by name from the active list.

FULL49_COLS: list[str] = [
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

SYNTH15_COLS: list[str] = [
    'VCB1-Power', 'VCB2-Power', 'PT100', 'PT101', 'PV101', 'TT203', 'LIT101', 'LV101',
    'TT101', 'FT102', 'LV102', 'FT103', 'PT106', 'PT105', 'ENV-0',
]  # canonical order; model 11 + decision extras TT203, PT105, PT106, LV102

SCHEMAS: dict[str, list[str]] = {'full49': FULL49_COLS, 'synth15': SYNTH15_COLS}
MODE_SCHEMA: dict[str, str] = {'prod': 'full49', 'demo': 'synth15'}
SCHEMA_ENV = 'RENZE_SCHEMA'

SCHEMA_NAME: str = os.environ.get(SCHEMA_ENV) or 'full49'
if SCHEMA_NAME not in SCHEMAS:
    raise SystemExit(f'{SCHEMA_ENV}={SCHEMA_NAME!r}: must be one of {sorted(SCHEMAS)}')

# The 11 model features, in the order the models were trained (same list for pipe and HXG).
# Notebook 09-B has 16 names but the indices match the pipe list — model stays as trained.
MODEL_FEAT_COLS: list[str] = [
    'VCB1-Power', 'VCB2-Power', 'PT100', 'PT101', 'PV101', 'LIT101', 'LV101', 'TT101',
    'FT102', 'FT103', 'ENV-0',
]

# Sensors in a packet file, in file order
RAW_SENSOR_COLS: list[str] = list(SCHEMAS[SCHEMA_NAME])
if 'PT104S' in RAW_SENSOR_COLS and RAW_SENSOR_COLS[-1] != 'PT104S':
    raise SystemExit('PT104S must be the last raw column')  # one_min_means drops it by position

# Canonical sensor names (PT104S dropped if present); used by reader, scoring, and SQLite
CANON_SENSOR_COLS: list[str] = [c for c in RAW_SENSOR_COLS if c != 'PT104S']

# Index of VCB2-Power within CANON_SENSOR_COLS
VCB2_IDX: int = CANON_SENSOR_COLS.index('VCB2-Power')

# Model feature indices into CANON_SENSOR_COLS, in MODEL_FEAT_COLS order
MODEL_FEAT_INDICES: list[int] = [CANON_SENSOR_COLS.index(c) for c in MODEL_FEAT_COLS]

ROW_S: int = 5          # one data row every 5 s
MIN_S: int = 60         # 1-min samples
BUNDLE_S: int = 900     # reader bundle = 15 min of data (one model window)

N_COLS: int = 1 + len(RAW_SENSOR_COLS)   # ts + sensors: 50 (full49) or 16 (synth15)
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


def floor_minute(ts: int) -> int:
    """Start of the minute that contains ts."""
    return int(ts) - int(ts) % MIN_S


# ── Write ─────────────────────────────────────────────────────────────────────

def write_row(path: Path, row: np.ndarray) -> None:
    """Write one N_COLS-value row (col 0 = epoch ts, then RAW_SENSOR_COLS) to a CSV."""
    line = f"{int(row[0])}," + ','.join(f'{float(v):.9g}' for v in row[1:])
    with open(path, 'w', newline='\n') as fh:
        fh.write(HEADER + '\n' + line + '\n')


# ── Read and validate ─────────────────────────────────────────────────────────

def read_row(path: Path) -> np.ndarray:
    """
    Read and validate one packet file. Returns an (N_COLS,) float64 array.
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

def one_min_means(rows: np.ndarray, start: int, end: int | None = None
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    1-min means of rows (n × N_COLS) with ts in [start, end); end defaults to start + BUNDLE_S.
    Works for one bundle or a batch of many; start must sit on a minute boundary.

    Returns, for minutes that have at least one row (empty minutes are skipped):
        min_ts : (k,) int64   — minute start
        means  : (k, len(CANON_SENSOR_COLS)) — mean over the rows present, PT104S dropped
        n_rows : (k,) int64   — rows behind each mean (12 = complete minute)
    """
    end = start + BUNDLE_S if end is None else end
    n_min = (end - start) // MIN_S
    n_sens = len(CANON_SENSOR_COLS)
    idx = ((rows[:, 0] - start) // MIN_S).astype(np.int64)
    counts = np.bincount(idx, minlength=n_min)
    sums = np.zeros((n_min, n_sens), dtype=np.float64)
    np.add.at(sums, idx, rows[:, 1:1 + n_sens])
    keep = np.flatnonzero(counts)
    return (start + keep.astype(np.int64) * MIN_S,
            sums[keep] / counts[keep, None],
            counts[keep].astype(np.int64))
