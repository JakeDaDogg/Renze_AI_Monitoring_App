# Renze AI Monitoring App

Monitoring system for the Renze plant: it reads plant sensor rows every 5 s, averages them
into 1-min samples, scores 15-min windows with the RUL models (pipe and heat exchanger) and
supports the daily maintenance (cleaning) decision.

- **Now:** a replay demo. A writer replays recorded cycle 9 (C9) data as one CSV per 5-s row;
  the reader processes it exactly as it will process the live feed.
- **Later:** production, with the real plant feed through the same reader/writer contract.

## Layout

```
backend/                 Python backend: writer, reader, schema, viewer (own venv: backend/.venv)
frontend/                planned: Next.js dashboard (own package.json / node_modules)
demo_assets/             demo inputs: models and data; only MANIFEST.md is tracked
design_docs/             design doc, file structure reference, tickets
model_training_history/  RUL model training notebooks (record only)
```

Full file-by-file reference: [design_docs/app file structure.md](design_docs/app%20file%20structure.md).
Design: [design_docs/Renze backend v3 — C9 replay demo and backend design.md](design_docs/Renze%20backend%20v3%20%E2%80%94%20C9%20replay%20demo%20and%20backend%20design.md).

## Run order (demo)

From `backend/`, in its venv:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python build_demo_assets.py               # once: cuts the C9 window into demo_assets/c9_window.npz
python replay_agent.py --run-minutes 3    # terminal 1: writer (resets demo_root/)
python reader.py --mode demo              # terminal 2: reader, start after the writer
python viewer.py                          # terminal 3: live plot of inference.db (optional)
```

The demo data and model files are not in git; see [demo_assets/MANIFEST.md](demo_assets/MANIFEST.md).
Demo and production never share a data root (`backend/paths.py`).
