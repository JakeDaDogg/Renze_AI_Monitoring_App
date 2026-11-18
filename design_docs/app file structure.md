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
│   ├── packet_io.py                file contract: one CSV per 5-s row; sensor schemas full49 / synth15
│   ├── db.py                       SQLite schema for minutes.db and inference.db
│   ├── replay_agent.py             demo writer: replays the synthetic file (synth15) or C9 (full49)
│   ├── build_demo_assets.py        full49 only: cuts the C9 window into demo_assets/c9_window.npz
│   ├── check_assets.py             compares local demo_assets/ files with MANIFEST.md hashes
│   ├── reader.py                   reader: minutes track + inference track (process() is a stub)
│   ├── viewer.py                   live plot of inference.db (read-only)
│   ├── tools/
│   │   └── make_synthetic_demo.py  builds demo_assets/synthetic/ from series6 C4–C6 (run once)
│   ├── tests/
│   │   └── test_schema.py          schema switch check (full49 unchanged, synth15, db refusal)
│   ├── _parked/
│   │   └── backfill.py             parked: production minutes.db history (series6 cycles 1–8)
│   ├── maint_recovery.py           daily maintenance decision (recovered kWh), not wired yet
│   ├── maint_recovery_v0.json      coefficients for maint_recovery.py
│   └── renze_paths.json            machine-specific prod root (ignored)
├── frontend/ [planned]             Next.js dashboard, own package.json / node_modules/
├── demo_root/                      runtime, recreated by every demo run (ignored)
├── demo_assets/                    demo inputs; MANIFEST.md, models/, synthetic/ tracked
│   ├── MANIFEST.md                 tracked: what to request, target path, size, sha256
│   ├── models/                     tracked: pipe/hxg_rul_v3_traindev .weights.h5 + _scaler.pkl
│   ├── synthetic/                  tracked: renze_synth_c456_v1.npz (9 MB) + README.md
│   ├── synthetic_plots/            ignored: quick-look PNGs from make_synthetic_demo.py
│   ├── data/                       ignored, internal: series6_cycle_9_converted.npy (415 MB)
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
- `.gitignore` — ignores venvs, `__pycache__`, `.DS_Store`, `/demo_root/`, `/demo_assets/*` except `MANIFEST.md`, `models/`, `synthetic/`, `backend/renze_paths.json`, `backend/_archive*/`, `*.db*`.
- No Python files at the root: it stays language-neutral so `frontend/` (Next.js) can sit beside `backend/` with its own `package.json` / `node_modules/`.

### backend/
- `.venv/`, `.python-version`, `requirements.txt` — the one Python environment. `pip install -r backend/requirements.txt`. TensorFlow 2.12 (RUL models) needs Python ≤ 3.11 and is listed as a comment only.
- `paths.py` — `resolve_root(mode)`: demo → `<app>/demo_root`; prod → `--root`, `RENZE_PROD_ROOT` or `backend/renze_paths.json`, never defaulted; refuses overlap with the demo root. `preselect_schema(mode)`. `ASSETS` = `<app>/demo_assets`, `MODELS` = `ASSETS/models`, `MANIFEST`, `missing_models()`. `layout(root)` creates `to_be_processed/ (.tmp/) processed/ bad/ control/`.
- `packet_io.py` — contract: `renze_YYYYMMDDTHHMMSSZ.csv`, header `ts,<sensors>`, one data line, 9 significant digits, published via `.tmp/` + `os.replace`. `ROW_S=5`, `MIN_S=60`, `BUNDLE_S=900`.
  - Sensor schema, chosen once per process from `RENZE_SCHEMA`: `full49` (production: 49 sensors, PT104S last) or `synth15` (demo only: the 11 model sensors + TT203, LV102, PT106, PT105; no PT104S). Entry scripts set the mode default with `paths.preselect_schema(mode)` before importing `packet_io`/`db` (demo → synth15, prod → full49); unset everywhere → full49.
  - Derived by name: `RAW_SENSOR_COLS`, `CANON_SENSOR_COLS` (minus PT104S: 48 / 15), `VCB2_IDX`, `MODEL_FEAT_INDICES` (in `MODEL_FEAT_COLS` order), `N_COLS` (50 / 16), `HEADER`. With full49 all are identical to the values before the switch (`tests/test_schema.py`).
- `db.py` — `minutes` (ts, ts_utc, n_rows, n_filled, 48 sensors) and `inference` (ts, ts_utc, vcb2_x2, saved_power, model_version) tables (sensor columns = the active `CANON_SENSOR_COLS`), WAL; `db_info` holds mode, schema version and `sensor_schema`; a DB of another mode or sensor schema is refused.
- `replay_agent.py` — demo writer. Resets `demo_root/`, locks the speed scale in `control/speed.json`, writes one CSV per 5-s row, heartbeat in `control/writer_status.json`. Schema default synth15; `speed.json` records the schema and the reader refuses a writer of another schema. `--run-minutes` 5 (min 3). Default source by schema: synth15 → `demo_assets/synthetic/renze_synth_c456_v1.npz`, whole file; full49 → `demo_assets/c9_window.npz`, else `demo_assets/data/series6_cycle_9_converted.npy`, window 2026-04-27 → 2026-05-18. `--source/--start/--end` override. A source whose column count differs from the schema → error naming both; missing file → "see demo_assets/MANIFEST.md".
- `build_demo_assets.py` — `RENZE_SCHEMA=full49`: cuts the C9 window from the converted `.npy` (default `demo_assets/data/`, `--source` overridable) into `demo_assets/c9_window.npz`. Under synth15 there is nothing to build: it checks the synthetic file and exits.
- `tools/make_synthetic_demo.py` — builds the synthetic demo data (runs once on Yuhan's Mac; inputs `series6_cycle_{4,5,6}_raw.npy`, `RENZE_SERIES6_DIR`). Last 10 operating days before each cleaning date (notebook dates), aligned, each 5-s row a Dirichlet(1,1,1)-weighted mix of C4/C5/C6, 1-h shutdown tail, ts from 2000-01-01T00:00:00Z. Method in `demo_assets/synthetic/README.md`.
- `check_assets.py` — hashes the local demo assets against `MANIFEST.md`, prints ok / MISSING / MISMATCH, exit 1 if any.
- `reader.py` — `--mode demo|prod` (also picks the schema default). Prints a note pointing at the MANIFEST if model files are missing (the stub does not need them). Averages 12 rows into a 1-min sample (`minutes.db`), scores 15-min windows with `process()` (`inference.db`). `process()` is a stub (2 × VCB2-Power).
- `viewer.py` — matplotlib live plot of `inference.vcb2_x2`, read-only connection.
- `_parked/backfill.py` — parked (tracked; `.gitignore` only drops `backend/_archive*/`). Forces `full49`. Production history from series6 cycles 1–8, zero placeholder rows for gaps. Adds `backend/` to `sys.path`, so `python backend/_parked/backfill.py --dry-run` works from any folder.
- `maint_recovery.py` + `maint_recovery_v0.json` — recovered kWh from cleaning tomorrow; sensors TT203, PT100, PT105, LIT101, PT106, LV102.

### frontend/ [planned]
- Next.js dashboard beside `backend/`; reads the backend's databases/API (design doc §2.5). Not created yet.

### demo_assets/
- Models and scalers are in git (synth decision 2026-11-17, supersedes housekeeping #6); the real C9 data stays out of git, internal only, on request from Yuhan (sharing method TBD). v3 `traindev` models only. The series6 clock is Taiwan local time labelled UTC; not shifted.

### design_docs/
- Design doc v3 (md + pdf), the packet_io walkthrough, this file, `tickets/`.

### model_training_history/
- Copies of the pipe and HXG RUL training notebooks.

## Runs
- 2026-11-18, C9, Mac (backend/.venv, Python 3.13): `build_demo_assets.py` → 362,880 rows, 79 MB. 3 min (2,016 files/s) and 5 min (1,210 files/s): reader kept up (backlog max 151 / 88 files), 30,240 minutes, 30,226 inference rows (first 14 minutes: window not fillable), 0 files in `bad/`, writer and reader exit 0; `viewer.py` reads the v3 `inference` table.

## Change log
- 2026-11-18 — housekeeping #1: file created in the repo (drafted from the repo state; merge with the claude.ai project copy by hand).
- 2026-11-18 — housekeeping #2: README rewritten.
- 2026-11-18 — housekeeping #3: root `renze_paths.json` deleted (untracked placeholder; `paths.py` reads `backend/renze_paths.json` only).
- 2026-11-18 — housekeeping #4: `backfill.py` parked in `backend/_parked/`, imports fixed, `--dry-run` checked (672,999 minutes, 287,411 with data).
- 2026-11-18 — housekeeping #5: root `.venv/` and `.python-version` removed; `backend/requirements.txt` added.
- 2026-11-18 — housekeeping #6: `demo_assets/` layout (models + C9 data copied from AI_for_Renze, ignored), `MANIFEST.md` tracked, `check_assets.py`, `paths.ASSETS/MODELS`, default sources point at `demo_assets/data/`.
- 2026-11-18 — housekeeping #7: first real C9 run on the Mac (see Runs).
- 2026-11-18 — housekeeping #8: `frontend/ [planned]` added to the tree; entries checked against the repo.
- 2026-11-18 — synth #1: `demo_assets/models/` (4 files, 146 KB) and `demo_assets/synthetic/` tracked; MANIFEST says what is in git.
- 2026-11-18 — synth #2: sensor schema switch (`full49` / `synth15`, `RENZE_SCHEMA`) in `packet_io.py`; `db_info.sensor_schema`; backfill forces full49; `tests/test_schema.py`.
- 2026-11-18 — synth #3: `tools/make_synthetic_demo.py`; `demo_assets/synthetic/renze_synth_c456_v1.npz` (173,520 × 15, 9.2 MB) + README; MANIFEST row.
- 2026-11-18 — synth #4: demo defaults to the synthetic file under synth15 (whole file); column-count check; C9 needs `RENZE_SCHEMA=full49`; `build_demo_assets.py` is full49-only.
