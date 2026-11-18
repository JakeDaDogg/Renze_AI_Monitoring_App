# Renze AI Monitoring App

Monitoring system for the Renze plant: it reads plant sensor rows every 5 s, averages them
into 1-min samples, scores 15-min windows with the RUL models (pipe and heat exchanger) and
supports the daily maintenance (cleaning) decision.

- **Now:** a replay demo. A writer replays synthetic data (internally also the recorded cycle 9,
  C9) as one CSV per 5-s row; the reader processes it exactly as it will process the live feed.
- **Later:** production, with the real plant feed through the same reader/writer contract.

## Layout

```
backend/                 Python backend: writer, reader, schema, viewer, tools/ (own venv: backend/.venv)
frontend/                planned: Next.js dashboard (own package.json / node_modules)
demo_assets/             demo inputs: models + synthetic data (in git), C9 data (internal)
design_docs/             design doc, file structure reference, tickets
model_training_history/  RUL model training notebooks (record only)
```

Full file-by-file reference: [design_docs/app file structure.md](design_docs/app%20file%20structure.md).
Design: [design_docs/Renze backend v3 — C9 replay demo and backend design.md](design_docs/Renze%20backend%20v3%20%E2%80%94%20C9%20replay%20demo%20and%20backend%20design.md).

## Run the demo

The demo data is **synthetic**: random weighted averages of three cleaned operating cycles
(C4–C6), not plant data (`demo_assets/synthetic/README.md`). The data and the RUL model weights
are in the repo, so a clone is enough.

```bash
git clone <repo> AI_Monitor_App && cd AI_Monitor_App/backend
python3 -m venv .venv && source .venv/bin/activate      # Python version: backend/.python-version
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
RENZE_SCHEMA=full49 python build_demo_assets.py           # once: demo_assets/c9_window.npz
RENZE_SCHEMA=full49 python replay_agent.py --run-minutes 3
RENZE_SCHEMA=full49 python reader.py --mode demo
```

`python check_assets.py` compares your `demo_assets/` with the MANIFEST hashes.
Demo and production never share a data root (`backend/paths.py`).
