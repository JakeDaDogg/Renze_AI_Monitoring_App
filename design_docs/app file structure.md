# Renze AI Monitor App — file structure

Master copy: this file in the repo (`design_docs/app file structure.md`). The claude.ai project copy is refreshed by hand.
Scope today: the C9 replay demo. Production comes later through the same reader/writer contract.

## Tree

```
AI_Monitor_App/
├── README.md                       purpose, layout, demo run order
├── .gitignore
├── backend/
│   ├── .python-version             Python version for backend/.venv (3.13)
│   ├── .venv/                      the only Python venv (ignored)
│   ├── requirements.txt            numpy, pandas, matplotlib (TensorFlow noted, not installed)
│   ├── paths.py                    data roots: demo_root/ (demo) or the named prod root
│   ├── packet_io.py                file contract: one CSV per 5-s row, column definitions
│   ├── db.py                       SQLite schema for minutes.db and inference.db
│   ├── replay_agent.py             demo writer: replays the C9 window into to_be_processed/
│   ├── build_demo_assets.py        cuts the C9 window into demo_assets/c9_window.npz
│   ├── check_assets.py             compares local demo_assets/ files with MANIFEST.md hashes
│   ├── reader.py                   reader: minutes track + inference track (process() is a stub)
│   ├── viewer.py                   live plot of inference.db (read-only)
│   ├── _parked/
│   │   └── backfill.py             parked: production minutes.db history (series6 cycles 1–8)
│   ├── maint_recovery.py           daily maintenance decision (recovered kWh), not wired yet
│   ├── maint_recovery_v0.json      coefficients for maint_recovery.py
│   └── renze_paths.json            machine-specific prod root (ignored)
├── demo_root/                      runtime, recreated by every demo run (ignored)
├── demo_assets/                    demo inputs; only MANIFEST.md is tracked
│   ├── MANIFEST.md                 tracked: what to request, target path, size, sha256
│   ├── models/                     ignored: pipe/hxg_rul_v3_traindev .weights.h5 + _scaler.pkl
│   ├── data/                       ignored: series6_cycle_9_converted.npy (415 MB)
│   └── c9_window.npz               ignored: built by build_demo_assets.py
├── design_docs/
│   ├── app file structure.md       this file
│   ├── Renze backend v3 — C9 replay demo and backend design.md / .pdf
│   ├── packet_io.py Walkthrough.pdf
│   └── tickets/                    work tickets handed to Claude Code
└── model_training_history/         RUL_Pipe_Model.ipynb, RUL_HXG_Model.ipynb (training record)
```

Outside the repo, read only: `~/Desktop/BALA/AI_for_Renze` (source data `08-Data/`, model weights `09-RUL Model/`, `09-B-HXG_RUL_Model/`). Never move or delete anything there.

## Entries

### Root
- `README.md` — purpose (C9 replay demo now, production later), layout, demo run order, links to this file and the design doc.
- `.gitignore` — ignores venvs, `__pycache__`, `.DS_Store`, `/demo_root/`, `/demo_assets/*` except `MANIFEST.md`, `backend/renze_paths.json`, `backend/_archive*/`, `*.db*`.
- No Python files at the root: it stays language-neutral so `frontend/` (Next.js) can sit beside `backend/` with its own `package.json` / `node_modules/`.

### backend/
- `.venv/`, `.python-version`, `requirements.txt` — the one Python environment. `pip install -r backend/requirements.txt`. TensorFlow 2.12 (RUL models) needs Python ≤ 3.11 and is listed as a comment only.
- `paths.py` — `resolve_root(mode)`: demo → `<app>/demo_root`; prod → `--root`, `RENZE_PROD_ROOT` or `backend/renze_paths.json`, never defaulted; refuses overlap with the demo root. `ASSETS` = `<app>/demo_assets`, `MODELS` = `ASSETS/models`, `MANIFEST`. `layout(root)` creates `to_be_processed/ (.tmp/) processed/ bad/ control/`.
- `packet_io.py` — contract: `renze_YYYYMMDDTHHMMSSZ.csv`, header `ts,<49 sensors>`, one data line, 9 significant digits, published via `.tmp/` + `os.replace`. Defines `RAW_SENSOR_COLS` (49, PT104S last), `CANON_SENSOR_COLS` (48), `VCB2_IDX`, `MODEL_FEAT_INDICES` (11), `ROW_S=5`, `MIN_S=60`, `BUNDLE_S=900`.
- `db.py` — `minutes` (ts, ts_utc, n_rows, n_filled, 48 sensors) and `inference` (ts, ts_utc, vcb2_x2, saved_power, model_version) tables, WAL; `db_info` holds mode and schema version, a DB of another mode is refused.
- `replay_agent.py` — demo writer. Resets `demo_root/`, locks the speed scale in `control/speed.json`, writes one CSV per 5-s row, heartbeat in `control/writer_status.json`. Default window 2026-04-27 → 2026-05-18 (C9), `--run-minutes` 5 (min 3). Source: `demo_assets/c9_window.npz`, else `demo_assets/data/series6_cycle_9_converted.npy`, or `--source`; missing → "see demo_assets/MANIFEST.md".
- `build_demo_assets.py` — cuts the C9 window from the converted `.npy` (default `demo_assets/data/`, `--source` overridable) into `demo_assets/c9_window.npz`.
- `check_assets.py` — hashes the local demo assets against `MANIFEST.md`, prints ok / MISSING / MISMATCH, exit 1 if any.
- `reader.py` — `--mode demo|prod`. Averages 12 rows into a 1-min sample (`minutes.db`), scores 15-min windows with `process()` (`inference.db`). `process()` is a stub (2 × VCB2-Power).
- `viewer.py` — matplotlib live plot of `inference.vcb2_x2`, read-only connection.
- `_parked/backfill.py` — parked (tracked; `.gitignore` only drops `backend/_archive*/`). Production history from series6 cycles 1–8, zero placeholder rows for gaps. Adds `backend/` to `sys.path`, so `python backend/_parked/backfill.py --dry-run` works from any folder.
- `maint_recovery.py` + `maint_recovery_v0.json` — recovered kWh from cleaning tomorrow; sensors TT203, PT100, PT105, LIT101, PT106, LV102.

### demo_assets/
- Models and C9 data stay out of git (decision 2026-11-17); teammates request them from Yuhan, sharing method TBD. v3 `traindev` models only. The series6 clock is Taiwan local time labelled UTC; not shifted.

### design_docs/
- Design doc v3 (md + pdf), the packet_io walkthrough, this file, `tickets/`.

### model_training_history/
- Copies of the pipe and HXG RUL training notebooks.

## Change log
- 2026-11-18 — housekeeping #1: file created in the repo (drafted from the repo state; merge with the claude.ai project copy by hand).
- 2026-11-18 — housekeeping #2: README rewritten.
- 2026-11-18 — housekeeping #3: root `renze_paths.json` deleted (untracked placeholder; `paths.py` reads `backend/renze_paths.json` only).
- 2026-11-18 — housekeeping #4: `backfill.py` parked in `backend/_parked/`, imports fixed, `--dry-run` checked (672,999 minutes, 287,411 with data).
- 2026-11-18 — housekeeping #5: root `.venv/` and `.python-version` removed; `backend/requirements.txt` added.
- 2026-11-18 — housekeeping #6: `demo_assets/` layout (models + C9 data copied from AI_for_Renze, ignored), `MANIFEST.md` tracked, `check_assets.py`, `paths.ASSETS/MODELS`, default sources point at `demo_assets/data/`.
