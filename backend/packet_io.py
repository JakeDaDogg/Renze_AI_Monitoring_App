"""
packet_io.py — shared packet format, IO, and 1-min means for the Renze demo pipeline.

Single source of truth for the file contract between replay_agent and reader.
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

ROWS_PER_PACKET: int = 180   # 180 × 5 s = 900 s = 15 min
MINS_PER_PACKET: int = 15
ROWS_PER_MIN: int = 12       # 12 × 5 s = 60 s

_PACKET_RE = re.compile(r'^renze_(\d{8}T\d{4}Z)\.csv$')
_PACKET_FMT = '%Y%m%dT%H%MZ'


# ── File-name ↔ quarter timestamp ─────────────────────────────────────────────

def quarter_to_name(quarter_ts: int) -> str:
    """Return the canonical file name for a quarter epoch timestamp."""
    dt = datetime.fromtimestamp(quarter_ts, tz=timezone.utc)
    return f"renze_{dt.strftime(_PACKET_FMT)}.csv"


def name_to_quarter(name: str) -> int | None:
    """Return the epoch-second quarter timestamp, or None if name doesn't match."""
    m = _PACKET_RE.match(name)
    if not m:
        return None
    dt = datetime.strptime(m.group(1), _PACKET_FMT).replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


# ── CSV write ─────────────────────────────────────────────────────────────────

def write_packet(path: Path, rows: np.ndarray) -> None:
    """Write a 180×50 float64 array (col 0 = epoch ts, cols 1–49 = RAW_SENSOR_COLS) to CSV."""
    header = 'ts,' + ','.join(RAW_SENSOR_COLS)
    fmt = ['%d'] + ['%.9g'] * 49
    np.savetxt(path, rows, delimiter=',', header=header, comments='', fmt=fmt)


# ── CSV read ──────────────────────────────────────────────────────────────────

def read_packet(path: Path) -> tuple[int, np.ndarray]:
    """
    Read a packet CSV.  Returns (quarter_ts, array[180, 50]).
    Raises ValueError for any format error detected before full parsing.
    """
    quarter_ts = name_to_quarter(path.name)
    if quarter_ts is None:
        raise ValueError(f"name does not match packet pattern: {path.name}")

    with open(path) as fh:
        first_line = fh.readline().rstrip('\n')
    expected_header = 'ts,' + ','.join(RAW_SENSOR_COLS)
    if first_line != expected_header:
        raise ValueError(f"unexpected header in {path.name}")

    data = np.loadtxt(path, delimiter=',', skiprows=1, dtype=np.float64)
    if data.ndim != 2 or data.shape != (ROWS_PER_PACKET, 50):
        raise ValueError(
            f"expected {ROWS_PER_PACKET}×50 array, got {data.shape} in {path.name}"
        )
    return quarter_ts, data


# ── Validation ────────────────────────────────────────────────────────────────

def validate_packet(quarter_ts: int, data: np.ndarray) -> None:
    """
    Raise ValueError if the packet fails the contract:
      - ts column == q, q+5, …, q+895
      - all sensor values finite
    """
    expected = np.arange(quarter_ts, quarter_ts + ROWS_PER_PACKET * 5, 5, dtype=np.int64)
    if not np.array_equal(data[:, 0].astype(np.int64), expected):
        raise ValueError("ts column does not match quarter alignment")
    if not np.all(np.isfinite(data[:, 1:])):
        raise ValueError("non-finite values in sensor columns")


# ── 1-minute means ────────────────────────────────────────────────────────────

def one_min_means(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert a 180×50 packet array into 1-minute mean samples.

    Returns:
        min_ts  : (15,) int64 — epoch-second start of each minute
        means   : (15, 48) float64 — mean of the 12 × 5 s rows, PT104S dropped
    """
    # cols 1:49 = RAW_SENSOR_COLS[0:48] = CANON_SENSOR_COLS (PT104S at col 49 dropped)
    canon = data[:, 1:49]
    reshaped = canon.reshape(MINS_PER_PACKET, ROWS_PER_MIN, len(CANON_SENSOR_COLS))
    means = reshaped.mean(axis=1)
    min_ts = data[::ROWS_PER_MIN, 0].astype(np.int64)
    return min_ts, means
