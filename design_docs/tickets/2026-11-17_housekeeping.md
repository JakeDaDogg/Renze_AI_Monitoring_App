# Ticket 2026-11-17 — housekeeping before the first C9 demo run

Status: open · Hand to Claude Code in this repo

Repo: `~/Desktop/BALA/AI_Monitor_App` · Scope: C9 demo only · Requested by: Yuhan
Reference: `design_docs/app file structure.md` (task 1 creates it). The repo copy is the master; the claude.ai project copy is refreshed by hand.

Rules
- Do not change pipeline behaviour (reader/writer logic, schema, time zone, zero placeholder rows); those are open design decisions.
- Copy source data from `~/Desktop/BALA/AI_for_Renze`, never move or delete it (notebooks there still use it).
- One commit per task; message `20261117 ticket #<n>: <summary>`.
- After each task, update `design_docs/app file structure.md` (entry + change log).

## Tasks

- [ ] 1. Put the structure reference in the repo
  - Save it as `design_docs/app file structure.md` (Yuhan provides the current text from the project).

- [ ] 2. Rewrite `README.md`
  - Purpose (Renze AI monitoring system: C9 replay demo now, production later), layout (backend/, frontend/ planned, demo_assets/, design_docs/, model_training_history/), run order, link to the structure doc.

- [ ] 3. Delete the root `renze_paths.json`
  - Placeholder (`/path/to/renze_prod`), untracked, never read: `paths.py` reads `backend/renze_paths.json` only.

- [ ] 4. Park `backfill.py`
  - `git mv backend/backfill.py backend/_parked/backfill.py`.
  - `.gitignore` has `backend/_archive*/` only, so `_parked/` stays tracked.
  - Fix its imports (`paths`, `db`, `packet_io` live one level up): add `backend/` to `sys.path` or run as documented; check `python backend/_parked/backfill.py --dry-run` still prints the counts.

- [ ] 5. One Python venv, in `backend/` only
  - Remove the root `.venv/` and root `.python-version`; keep `backend/.venv/` and `backend/.python-version`.
  - Reason: `frontend/` (Next.js) will sit beside `backend/` with its own `package.json` / `node_modules/`; the root stays language-neutral.
  - Write `backend/requirements.txt` from `backend/.venv` (`pip freeze`), trimmed to what the code imports (numpy, pandas, tensorflow 2.12, matplotlib, ...).

- [ ] 6. Demo assets: models and C9 data (shared drive, on request; not in git)
  - Decision (Yuhan, 2026-11-17): repo is private, but model weights, scalers and C9 data stay out of git for now; teammates get them on request. Only `demo_assets/MANIFEST.md` is tracked.
  - The sharing method (shared drive or an alternative) is still to be discussed; do not build anything for it beyond the MANIFEST.
  - Layout:
    ```
    demo_assets/
    ├── MANIFEST.md                            tracked: what to request, where to put it, sha256
    ├── models/                                ignored
    │   ├── pipe_rul_v3_traindev.weights.h5   ← AI_for_Renze/09-RUL Model/
    │   ├── pipe_rul_v3_traindev_scaler.pkl   ← AI_for_Renze/09-RUL Model/
    │   ├── hxg_rul_v3_traindev.weights.h5    ← AI_for_Renze/09-B-HXG_RUL_Model/
    │   └── hxg_rul_v3_traindev_scaler.pkl    ← AI_for_Renze/09-B-HXG_RUL_Model/
    ├── data/                                  ignored
    │   └── series6_cycle_9_converted.npy     ← AI_for_Renze/08-Data/ (396 MB)
    └── c9_window.npz                          ignored (built by build_demo_assets.py)
    ```
  - `.gitignore`: replace `/demo_assets/` with
    ```
    /demo_assets/*
    !/demo_assets/MANIFEST.md
    ```
  - `MANIFEST.md`: per file — name, target path, size, sha256, source version, and "request from Yuhan" (sharing method TBD). Plus a 3-line check, e.g. `shasum -a 256 demo_assets/models/*`.
  - Optional: `backend/check_assets.py` that compares local files with the MANIFEST hashes and prints what is missing.
  - Use the v3 `traindev` files only (not `pipe_rul_v2*`). Copy from AI_for_Renze, do not move.
  - Point the default `--source` of `build_demo_assets.py` (and the fallback in `replay_agent.py`) at `demo_assets/data/series6_cycle_9_converted.npy`; keep `--source` overridable. A missing file should print "see demo_assets/MANIFEST.md".
  - Add `ASSETS = <app>/demo_assets` and `MODELS = ASSETS / 'models'` to `paths.py`. Do not wire the models into `process()` in this ticket.
  - Note: the series6 clock is Taiwan local time labelled UTC (check of 2026-11-17); do not shift it here.

- [ ] 7. First real run on the Mac
  - `python build_demo_assets.py`, then `python replay_agent.py --run-minutes 3` and `python reader.py --mode demo`, then `python viewer.py`.
  - The stale v2.1 `demo_root/` (142 CSVs, old-schema DBs) is replaced by the writer on start.
  - Report: did the reader keep up (target 2,016 files/s at 3 min; also try 5 min, 1,210 files/s), minutes and inference row counts, any exit code, files in `bad/`, whether viewer.py reads the v3 `inference` table.

- [ ] 8. Keep the structure doc current
  - Every task above updates its entry and the change log. Also add `frontend/ [planned]` to the tree.

## Out of scope (open decisions, do not change)
- The four reader differences from the design doc; prod reader exit-after-1-h vs always-on.
- Time zone convention (real UTC vs labelled local time).
- Backfill zero placeholder rows; production root; daily maintenance decision (`maint_recovery.py`).
