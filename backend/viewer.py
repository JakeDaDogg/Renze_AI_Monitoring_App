"""
viewer.py — live rolling-window plot of the reader's inference output (read-only).

Separate process for the live demo. It polls processed/inference.db and never writes to any
database. The reader keeps both databases in WAL mode, so this read-only connection never
blocks its commits.

- Opens inference.db as `file:<path>?mode=ro` (URI) with a short busy timeout.
- Polls on a matplotlib timer on the main thread (no background threads; macOS GUI rule).
- Incremental fetch: only rows with ts > last_ts, ordered by ts. The first fetch (and any
  catch-up after a long gap) loads at most the last WINDOW_H of data.
- Rolling window in data time: keeps points within WINDOW_H of the newest timestamp; the
  x-limits move with the data. Every series is drawn as dots only (no connecting lines).
- Missing DB or table → "waiting for inference.db", keep polling. Locked/busy → skip the tick.
- If the DB file is replaced (new demo run), the viewer reconnects and starts over.

Usage:
    python viewer.py [--db PATH] [--window-h HOURS] [--refresh-ms MS] [--tz UTC|Asia/Taipei]
"""
from __future__ import annotations

import argparse
import signal
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent.parent / 'demo_root' / 'processed' / 'inference.db'  # --db
TABLE   = 'inference'          # reader.py: ts INTEGER PRIMARY KEY (epoch s, UTC), vcb2_x2 REAL
TS_COL  = 'ts'

# (column, label, color) — one dot series per entry
SERIES: list[tuple[str, str, str]] = [
    ('vcb2_x2', '2 × VCB2-Power (stub)', 'tab:blue'),
    # Future RUL models (column names to be confirmed by that ticket):
    # ('pipe_rul_h', 'Pipe RUL (h)', 'tab:orange'),
    # ('hx_rul_h',   'HX RUL (h)',   'tab:green'),
]

WINDOW_H    = 24.0             # rolling window, data hours            (--window-h)
REFRESH_MS  = 200              # poll interval, wall ms                (--refresh-ms)
BUSY_S      = 0.05             # sqlite busy timeout; short so the GUI never stalls
MARKER      = '.'
MARKER_SIZE = 4
Y_LIM: tuple[float, float] | None = None   # fixed y-limits, or None to autoscale
Y_MARGIN    = 0.05             # autoscale margin, fraction of the data range
DISPLAY_TZ  = 'UTC'            # x-axis / status timezone, e.g. 'Asia/Taipei'  (--tz)

FIG_SIZE    = (11.0, 5.5)      # inches
TITLE       = 'Renze — live inference'
TITLE_FS    = 13
STATUS_FS   = 9
LABEL_FS    = 10
TICK_FS     = 9
LEGEND_FS   = 9
X_LABEL     = 'data time ({tz})'
Y_LABEL     = 'inference output'

# ── Data source ───────────────────────────────────────────────────────────────


class Source:
    """Read-only, incremental reader of the inference table."""

    def __init__(self, path: Path, columns: list[str], window_s: int):
        self.path = path
        self.columns = columns
        self.window_s = window_s
        self.conn: sqlite3.Connection | None = None
        self.inode: int | None = None
        self.sql: str | None = None
        self.last_ts: int | None = None

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
        self.conn = self.inode = self.sql = self.last_ts = None

    def _connect(self) -> bool:
        """Connect (or reconnect after the file was replaced). False if there is no DB yet."""
        try:
            inode = self.path.stat().st_ino
        except FileNotFoundError:
            self.close()
            return False
        if self.conn is not None and inode == self.inode:
            return True
        self.close()
        uri = f'file:{self.path.resolve().as_posix()}?mode=ro'
        self.conn = sqlite3.connect(uri, uri=True, timeout=BUSY_S)
        self.inode = inode
        return True

    def _prepare(self) -> bool:
        """Build the query once the table exists. False if the table is not created yet."""
        if self.sql is not None:
            return True
        info = self.conn.execute(f'PRAGMA table_info("{TABLE}")').fetchall()
        if not info:
            return False
        have = {row[1] for row in info}
        missing = [c for c in self.columns if c not in have]
        if missing:
            raise SystemExit(f'viewer: column(s) {missing} not in {TABLE}; have {sorted(have)}')
        cols = ', '.join(f'"{c}"' for c in self.columns)
        # ts > last_ts (incremental) and never older than one window before the newest row,
        # so the first tick and any catch-up load at most WINDOW_H of data.
        self.sql = (f'SELECT "{TS_COL}", {cols} FROM "{TABLE}" '
                    f'WHERE "{TS_COL}" > ? '
                    f'AND "{TS_COL}" >= (SELECT MAX("{TS_COL}") FROM "{TABLE}") - ? '
                    f'ORDER BY "{TS_COL}"')
        return True

    def fetch(self) -> tuple[str, np.ndarray | None, bool]:
        """
        One poll. Returns (state, rows, reset):
            state 'ok'      — query ran; rows is (n, 1 + k) float64 (n may be 0)
            state 'waiting' — no DB file or no table yet
            state 'skip'    — locked/busy or another transient error; try next tick
        reset is True when the DB was (re)opened and old points should be dropped.
        """
        old_inode = self.inode
        try:
            if not self._connect():
                return 'waiting', None, False
            reset = self.inode != old_inode
            if not self._prepare():
                return 'waiting', None, reset
            after = self.last_ts if self.last_ts is not None else -(1 << 62)
            rows = self.conn.execute(self.sql, (after, self.window_s)).fetchall()
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if 'no such table' in msg or 'unable to open' in msg:
                self.close()
                return 'waiting', None, False
            return 'skip', None, False                 # locked / busy: quietly retry
        arr = np.array(rows, dtype=np.float64).reshape(-1, 1 + len(self.columns))  # NULL → nan
        if len(arr):
            self.last_ts = int(arr[-1, 0])
        return 'ok', arr, reset


# ── Plot ──────────────────────────────────────────────────────────────────────

_EPOCH_DAYS = mdates.date2num(datetime(1970, 1, 1, tzinfo=timezone.utc))


def _to_mpl(ts: np.ndarray | float) -> np.ndarray | float:
    """Epoch seconds (UTC) → matplotlib date numbers."""
    return _EPOCH_DAYS + np.asarray(ts, dtype=np.float64) / 86400.0


class Viewer:
    def __init__(self, source: Source, window_s: int, refresh_ms: int, tz: ZoneInfo):
        self.src = source
        self.window_s = window_s
        self.tz = tz
        self.ts = np.empty(0, dtype=np.float64)
        self.vals = np.empty((0, len(SERIES)), dtype=np.float64)
        self.last_fetch: float | None = None
        self.state = 'waiting'

        self.fig, self.ax = plt.subplots(figsize=FIG_SIZE)
        self.fig.suptitle(TITLE, fontsize=TITLE_FS)
        self.lines = [
            self.ax.plot([], [], linestyle='none', marker=MARKER, markersize=MARKER_SIZE,
                         color=color, label=label)[0]
            for _, label, color in SERIES
        ]
        self.ax.xaxis_date(tz=tz)
        locator = mdates.AutoDateLocator(tz=tz)
        self.ax.xaxis.set_major_locator(locator)
        self.ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz=tz))
        self.ax.set_xlabel(X_LABEL.format(tz=tz.key), fontsize=LABEL_FS)
        self.ax.set_ylabel(Y_LABEL, fontsize=LABEL_FS)
        self.ax.tick_params(labelsize=TICK_FS)
        self.ax.grid(True, alpha=0.3)
        self.ax.legend(loc='upper left', fontsize=LEGEND_FS, markerscale=2)
        if Y_LIM is not None:
            self.ax.set_ylim(*Y_LIM)
        self.status = self.ax.set_title('', fontsize=STATUS_FS, loc='left')
        self._status_text = None

        self.timer = self.fig.canvas.new_timer(interval=refresh_ms)
        self.timer.add_callback(self.tick)
        self.fig.canvas.mpl_connect('close_event', lambda _evt: self.timer.stop())

    # ── one poll ──
    def tick(self) -> None:
        state, rows, reset = self.src.fetch()
        dirty = False
        if reset and len(self.ts):
            self.ts = self.ts[:0]
            self.vals = self.vals[:0]
            dirty = True
        if state == 'ok':
            self.last_fetch = time.time()
            if len(rows):
                self.ts = np.concatenate([self.ts, rows[:, 0]])
                self.vals = np.concatenate([self.vals, rows[:, 1:]])
                keep = self.ts >= self.ts[-1] - self.window_s
                self.ts, self.vals = self.ts[keep], self.vals[keep]
                dirty = True
        if state != 'skip':
            self.state = state
        if dirty:
            self._redraw_data()
        if self._update_status() or dirty:
            self.fig.canvas.draw_idle()

    def _redraw_data(self) -> None:
        x = _to_mpl(self.ts)
        for line, col in zip(self.lines, self.vals.T):
            line.set_data(x, col)
        if not len(self.ts):
            return
        newest = self.ts[-1]
        self.ax.set_xlim(_to_mpl(newest - self.window_s), _to_mpl(newest))
        if Y_LIM is None:
            finite = self.vals[np.isfinite(self.vals)]
            if len(finite):
                lo, hi = float(finite.min()), float(finite.max())
                pad = (hi - lo) * Y_MARGIN or max(abs(hi) * Y_MARGIN, 1.0)
                self.ax.set_ylim(lo - pad, hi + pad)

    def _fmt(self, epoch: float) -> str:
        return datetime.fromtimestamp(epoch, tz=self.tz).strftime('%Y-%m-%d %H:%M:%S')

    def _update_status(self) -> bool:
        if self.state == 'waiting':
            text = f'waiting for inference.db … ({self.src.path})'
        else:
            newest = self._fmt(self.ts[-1]) if len(self.ts) else '—'
            fetched = self._fmt(self.last_fetch) if self.last_fetch else '—'
            text = (f'newest data: {newest}   ·   points in window: {len(self.ts)}'
                    f'   ·   last fetch: {fetched}  ({self.tz.key})')
        if text == self._status_text:
            return False
        self._status_text = text
        self.status.set_text(text)
        return True

    def run(self) -> None:
        self.tick()                     # draw the first frame straight away
        self.timer.start()
        plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description='Live rolling-window plot of inference.db (read-only)')
    ap.add_argument('--db', type=Path, default=DB_PATH, help=f'default: {DB_PATH}')
    ap.add_argument('--window-h', type=float, default=WINDOW_H, metavar='HOURS',
                    help=f'rolling window in data hours (default {WINDOW_H:g})')
    ap.add_argument('--refresh-ms', type=int, default=REFRESH_MS, metavar='MS',
                    help=f'poll interval in wall ms (default {REFRESH_MS})')
    ap.add_argument('--tz', default=DISPLAY_TZ,
                    help=f'display timezone, e.g. UTC or Asia/Taipei (default {DISPLAY_TZ})')
    args = ap.parse_args()
    if args.window_h <= 0 or args.refresh_ms < 1:
        ap.error('--window-h must be > 0 and --refresh-ms >= 1')
    try:
        tz = ZoneInfo(args.tz)
    except Exception:
        ap.error(f'unknown timezone: {args.tz}')

    window_s = int(round(args.window_h * 3600))
    source = Source(args.db, [c for c, _, _ in SERIES], window_s)
    viewer = Viewer(source, window_s, args.refresh_ms, tz)
    # Ctrl+C: the handler runs on the next timer tick and closes the window, ending plt.show().
    signal.signal(signal.SIGINT, lambda *_: plt.close('all'))
    try:
        viewer.run()
    except KeyboardInterrupt:
        pass
    finally:
        viewer.timer.stop()
        source.close()


if __name__ == '__main__':
    main()
