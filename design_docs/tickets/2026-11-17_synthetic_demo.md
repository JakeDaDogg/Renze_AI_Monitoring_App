# Ticket 2026-11-17 — shareable demo: synthetic data + shipped weights

Status: open · Hand to Claude Code in this repo · Do after `2026-11-17_housekeeping.md`
Repo: `~/Desktop/BALA/AI_Monitor_App` · Requested by: Yuhan · Scope: **demo only, not production**

## Goal
Anyone with the repo can run the demo on their own machine: the RUL weights and scalers are in git, and the replay input is a small synthetic dataset built from the cleaned cycles 4–6. No real plant rows leave Taipower.

## Rules
- **Do not change the reading and writing procedure.** The writer still writes one CSV per 5-s row into `to_be_processed/` (atomic, via `.tmp/`); the reader still averages 12 rows into a 1-min sample, writes `minutes.db`, runs `process()` on 15-min windows and writes `inference.db`. The only change to the pipeline is which columns a row carries (task 2).
- **Production is untouched:** production keeps the full 49-sensor schema, real 5-s plant data and its own feed. The synthetic data and the 15-sensor schema are demo-only.
- Never move or delete anything in `~/Desktop/BALA/AI_for_Renze`; read only.
- One commit per task; message `20261117 synth #<n>: <summary>`. Update `design_docs/app file structure.md` (entry + change log) after each task.
- "It runs badly" is acceptable: realism of the scores is not an acceptance criterion; the pipeline running end to end is.

## Decisions (Yuhan, 2026-11-17)
- Ship the model weights and scalers; generate synthetic data instead of shipping real data.
- Synthetic data = the **last 10 operating days** of cycles **4, 5 and 6**, aligned on their **cleaning dates**. Each data point is a **random weighted average** of the three cycles: three random weights that add up to 1, drawn fresh per point. The random weights are the noise (no added Gaussian noise).
- Sensors: the 11 model sensors + the 4 extra sensors the daily decision needs = **15 sensors**.
- A **1 h shutdown tail** at the end. (Inference: the 48 h cycle-close rule will not fire; the demo ends in Critical / plant offline. Accepted.)
- The daily maintenance decision stays in the demo (wiring it into `process()` is a later ticket; this one only makes sure its sensors are in the data).
- Real C9 replay stays available internally via `--source`, outside git.

## Tasks

- [ ] 1. Commit the weights and scalers (supersedes part of housekeeping task 6)
  - Track `demo_assets/models/` (`pipe_rul_v3_traindev.weights.h5`, `pipe_rul_v3_traindev_scaler.pkl`, `hxg_rul_v3_traindev.weights.h5`, `hxg_rul_v3_traindev_scaler.pkl`) and `demo_assets/synthetic/`.
  - `.gitignore`:
    ```
    /demo_assets/*
    !/demo_assets/MANIFEST.md
    !/demo_assets/models/
    !/demo_assets/synthetic/
    ```
  - `demo_assets/data/` (real C9 `.npy`) and `c9_window.npz` stay ignored. Update `MANIFEST.md`: models and synthetic file = in git (sha256 listed); C9 data = internal only, on request.
  - Check file sizes before committing; stop and report if any tracked file is > 50 MB.

- [ ] 2. Schema switch in `packet_io.py` (the one pipeline change)
  - Two named schemas, chosen once per process, before any other module reads the constants:
    - `full49`: today's `RAW_SENSOR_COLS` (49, PT104S last). Default for `--mode prod`.
    - `synth15`: the 15 sensors below, in canonical order, no PT104S. Default for `--mode demo`.
  - Selection: env var `RENZE_SCHEMA` (`full49` | `synth15`) overrides the mode default, so the internal C9 run is `RENZE_SCHEMA=full49 python replay_agent.py --source ...` + the same for the reader.
  - Derive everything by **name**, not fixed indices: `CANON_SENSOR_COLS` = schema minus PT104S if present; `VCB2_IDX`; `MODEL_FEAT_INDICES` from the 11 model names (order must stay `MODEL_FEAT_COLS` as today); `N_COLS`; `HEADER`.
  - `synth15` columns (canonical order):
    `VCB1-Power, VCB2-Power, PT100, PT101, PV101, TT203, LIT101, LV101, TT101, FT102, LV102, FT103, PT106, PT105, ENV-0`
    - model 11: VCB1-Power, VCB2-Power, PT100, PT101, PV101, LIT101, LV101, TT101, FT102, FT103, ENV-0
    - decision 4 extra: TT203, PT105, PT106, LV102 (PT100, LIT101 already in the 11)
  - `db.py`: build tables from the active `CANON_SENSOR_COLS`; record the schema name in `db_info` and refuse to open a DB whose schema differs (same pattern as the mode label).
  - `backfill.py` (parked): force `full49`.
  - Check: with `full49`, header, `MODEL_FEAT_INDICES` and `VCB2_IDX` are identical to today's values (assert in a quick test).

- [ ] 3. Generator `backend/tools/make_synthetic_demo.py` (runs once, on Yuhan's Mac; the script is committed, its inputs are not)
  - Input: `~/Desktop/BALA/AI_for_Renze/08-Data/series6/series6_cycle_{4,5,6}_raw.npy` + `series6_column_labels.npy` (path overridable, `RENZE_SERIES6_DIR`). Cycles 4–6 are sampled every 60 s; downtime and rows < 300 kW were already removed (gaps).
  - Cleaning dates: read the cycle end/cleaning dates for C4–C6 from the training config in `AI_for_Renze/09-RUL Model/05-RUL_Pipe_Model_TrainDev.ipynb` (pipe and HXG share them for C4–C8). Print them next to each file's last timestamp; if they differ by more than 1 h, use the notebook date and report it.
  - Per cycle: operating-time axis counted backwards from the cleaning date (sample gaps > 5 min contribute 0); put the 15 sensors on a 1-min grid of operating minutes; keep the last 10 operating days = 14,400 minutes.
  - Align the three cycles on operating minutes-before-cleaning, giving three aligned 1-min series `C4[m], C5[m], C6[m]` (15 sensors each).
  - Random weighted average, per 5-s row: for minute `m`, each of its 12 rows gets its own weights `w = (w4, w5, w6)`, `w ~ Dirichlet(1, 1, 1)` (uniform over all triples ≥ 0 that sum to 1), and `row = w4·C4[m] + w5·C5[m] + w6·C6[m]`. The same `w` is used for all 15 sensors of that row, so the sensors stay consistent with each other. Fixed seed `--seed 0`.
    - This replaces both the equal-weight mean and the Gaussian noise; no separate upsampling noise.
    - Every value stays inside the range of the three cycles at that minute, so no clipping is needed.
    - Note (inference): the 12-row mean per minute will sit close to the equal-weight mean, so the 1-min samples the models see are smoother than the 5-s rows.
  - Shutdown tail: 60 min (720 rows) after the last minute: VCB1-Power and VCB2-Power from the three cycles' values are replaced by ≈ 0 (each cycle's tail value set to a few kW, e.g. 0–5 kW, then the same random weighting); other sensors use the three cycles' last-minute values with the same random weighting.
  - Timestamps: a fixed, obviously synthetic start, `2000-01-01T00:00:00Z`, every 5 s, no gaps (10 d + 1 h = 173,520 rows).
  - Output `demo_assets/synthetic/renze_synth_c456_v1.npz`: `ts` (int64) + `X` (float32, 173,520 × 15) + `columns`, `seed`, `weights = "Dirichlet(1,1,1) per 5-s row"`, source cycles, cleaning dates, build date. Expected ≈ 10 MB.
  - Also write `demo_assets/synthetic/README.md`: how it was built (the bullets above), and that it is synthetic (random weighted averages of three cycles), not plant data.
  - Quick look (not committed): one PNG per sensor group of the synthetic 1-min means vs the three cycles, for Yuhan to eyeball.

- [ ] 4. Point the demo at the synthetic file
  - `replay_agent.py` and `build_demo_assets.py`: under `synth15`, default source = `demo_assets/synthetic/renze_synth_c456_v1.npz`, start/end = the file's first/last ts (not the C9 window constants). `--source` stays overridable; C9 needs `RENZE_SCHEMA=full49`.
  - A source whose column count does not match the active schema → clear error naming both.
  - Missing models or data → "see demo_assets/MANIFEST.md".
  - No change to pacing, file naming, `.tmp/` publishing, heartbeat or the reader's tracks.

- [ ] 5. Run it end to end on the Mac
  - `python replay_agent.py --run-minutes 3` + `python reader.py --mode demo` (+ `python viewer.py`) from `backend/` in its venv, default schema `synth15`.
  - Report: files/s (expected ≈ 960 at 3 min), minutes and inference row counts (expected ≈ 14,460 minutes), exit codes, files in `bad/`, whether the last hour shows Critical (rolling 15-min VCB2 < 300 kW).
  - Optional, if TensorFlow is in the venv: load both models (rebuild + `load_weights`, no `model.predict()`), score the synthetic 1-min means offline and report the smoothed RUL at day 0, 3, 7, 10. Report only; no threshold.
  - Then repeat a short internal run with `RENZE_SCHEMA=full49` and the C9 `--source` to confirm the production schema still works.

- [ ] 6. Docs
  - `README.md`: "Run the demo" section (clone → venv → `pip install -r backend/requirements.txt` → 3 commands); state that the demo data is synthetic.
  - `design_docs/app file structure.md`: `demo_assets/models/` and `synthetic/` tracked, `tools/make_synthetic_demo.py`, schema switch, change log line.

## Out of scope
- Wiring the RUL models or the daily decision into `process()`.
- Any production change (49-sensor schema, prod root, backfill, time zone).
- The 48 h cycle-close rule (not triggered by the 1 h tail).
- Public release of the repo; Taipower approval for releasing the weights and the derived synthetic data is Yuhan's to obtain before the repo is made public.

## Note for production (do not lose)
The synthetic 15-sensor data and the `synth15` schema exist only so outsiders can run the demo. Production reads real plant data at 5 s with all 49 sensors (`full49`) through the same reader and writer contract.
