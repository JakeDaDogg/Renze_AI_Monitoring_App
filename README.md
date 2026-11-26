# Renze AI Monitoring App

Monitoring system for the Renze plant: it reads plant sensor rows every 5 s, averages them
into 1-min samples, scores 15-min windows with the RUL models (pipe and heat exchanger) and
supports the daily maintenance (cleaning) decision.

- **Now:** a replay demo. A writer replays synthetic data (internally also the recorded cycle 9,
  C9) as one CSV per 5-s row; the reader processes it exactly as it will process the live feed.
- **Later:** production, with the real plant feed through the same reader/writer contract.

## Layout

```
backend/       Python backend: writer, reader, schema, viewer (own venv: backend/.venv)
demo_assets/   demo inputs: RUL models + synthetic data (in git), C9 data (internal, not in git)
```

## Run the demo

The demo data is **synthetic**: random weighted averages of three cleaned operating cycles
(C4–C6), not plant data (`demo_assets/synthetic/README.md`). The data and the RUL model weights
are in the repo, so a clone is enough.

```bash
git clone <repo> AI_Monitor_App && cd AI_Monitor_App/backend
python3 -m venv .venv && source .venv/bin/activate      # Python 3.10 or newer
pip install -r requirements.txt

python replay_agent.py --run-minutes 3    # terminal 1: writer (resets demo_root/), 10 days + 1 h of data in 3 min
python reader.py --mode demo              # terminal 2: reader, start after the writer
python viewer.py                          # terminal 3: live plot of inference.db (optional)
```

The demo ends with a 1-h shutdown (plant offline). The demo uses the 15-sensor `synth15`
schema; production uses all 49 sensors (`full49`) through the same reader and writer.

### Internal: replay the real C9 data

Needs `demo_assets/data/series6_cycle_9_converted.npy` (internal, on request, see
[demo_assets/MANIFEST.md](demo_assets/MANIFEST.md)). Run writer and reader with the same schema:

```bash
RENZE_SCHEMA=full49 python replay_agent.py --run-minutes 3
RENZE_SCHEMA=full49 python reader.py --mode demo
```

To check file hashes against the MANIFEST: `shasum -a 256 ../demo_assets/models/* ../demo_assets/synthetic/*.npz`.
Demo and production never share a data root (`backend/paths.py`).

## Run the backend in isolation (manual inspection)

For watching each step and testing outages by hand. Run every script from `backend/` in its venv, one terminal per script. Recommended writer scale for visual inspection: **180** (3 data minutes per wall second).

### What the backend simulates

The demo plays the plant's data path, from SCADA readings to model output, on your own computer:

1. **Plant SCADA:** the plant records its sensors every 5 s.
2. **Writer (`replay_agent.py`):** turns each 5-s row into one CSV file in `to_be_processed/`. In production the plant feed does this; in the demo the writer replays stored data, sped up by `--scale`.
3. **Reader, step 1 (`reader.py`):** averages each minute's 12 rows into one 1-min sample and saves it in `minutes.db`.
4. **Reader, step 2:** for every minute, takes the last 15 minutes and runs the pipe and heat-exchanger RUL models, then saves the result in `inference.db`. For now a placeholder (2 × VCB2 power) stands in for the models.
5. **Viewer (`viewer.py`):** plots `inference.db` live; the planned dashboard will take its place.

Demo vs plant: the demo uses synthetic data with 15 sensors instead of the plant's 49, and the daily maintenance decision is not wired in yet.

### Config per script

#### Writer — `replay_agent.py` (terminal 1, always start first)

```bash
python replay_agent.py --scale 180 --end 20000102T000000Z
```

| Flag | Value | Effect |
|---|---|---|
| `--scale` | `180` | Data time / wall time; overrides `--run-minutes` |
| `--end` | `20000102T000000Z` | Stops after the first synthetic data day (≈ 8 min wall). Omit it for the whole file (10 d + 1 h, ≈ 80 min) |

**How the `--start` / `--end` values are encoded.** The format is `YYYYMMDDTHHMMSSZ`: date, `T`, time, `Z`. The writer reads it as UTC epoch seconds, so `20000102T000000Z` = 2000-01-02 00:00:00 UTC = epoch 946,771,200.

- **Synthetic data:** its clock is made up. It starts at `20000101T000000Z` with one row every 5 s, so `20000102T000000Z` means "after 24 data hours". Read as UTC+8 it would be 2000-01-02 08:00, but no real date or Taiwan time lies behind it.
- **Real C9 data (`full49`):** the stored clock is Taiwan local time labelled as UTC (checked 2026-11-17). Read the digits directly as Taiwan time, without adding 8 h: `20260427T000000Z` = 27 Apr 2026, 00:00 in Taiwan.
- **Wall time:** run length = data span ÷ `--scale`. One data day at scale 180 = 86,400 s ÷ 180 = 480 s, about 8 min.

Wait for its `Source …` line before starting the reader.

#### Reader — `reader.py` (terminal 2)

```bash
python reader.py --mode demo --scale 180
```

| Flag | Value | Effect |
|---|---|---|
| `--mode` | `demo` | Demo root and the `synth15` schema |
| `--scale` | `180` | Scans every 0.33 s (60 / 180) and tolerates 20 s of writer silence (3600 / 180). Changes polling only, not results |
| `--resume` | — | Add when restarting the reader mid-run |

With `--scale`, the reader does not wait for a running writer. Start it after the writer, or the writer's reset deletes `demo_root/` underneath it.

#### Viewer — `viewer.py` (terminal 3, optional)

```bash
python viewer.py
```

Defaults: 24 h rolling window, 200 ms refresh, times shown as stored (`UTC`). The viewer does not exit when the writer stops: close the window or press Ctrl-C.

### Scenarios

#### 1. All three running together

1. Terminal 1: start the writer; wait for its `Source …` line.
2. Terminal 2: start the reader.
3. Terminal 3: start the viewer.

#### 2. Writer down, reader keeps reading

1. Terminal 1: press **Ctrl-Z**. The writer freezes; the reader keeps scanning and finds nothing new.
2. Terminal 1: type **`fg`** within 20 seconds. The writer first writes the rows it missed, then returns to its normal pace. The reader catches up without a restart.

Use Ctrl-Z, not Ctrl-C: Ctrl-C sets the writer status to `stopped` and the reader exits on that. A pause longer than 20 seconds also ends the reader. Either way, restart it as in scenario 3.

#### 3. Reader down, writer keeps writing

1. Terminal 2: press **Ctrl-C**. The writer keeps going and files pile up. To watch the backlog:

   ```bash
   ls ../demo_root/to_be_processed | wc -l
   ```

2. Terminal 2: restart the reader:

   ```bash
   python reader.py --mode demo --scale 180 --resume
   ```

   It continues from the last committed minute and works through the backlog.
