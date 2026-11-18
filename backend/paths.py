"""
paths.py — resolve the data root for a mode. Demo and production never share a root.

- demo: <app>/demo_root, next to backend/ (created fresh for each demo run).
- prod: set explicitly, never defaulted:
      1. --root on the command line, or
      2. environment variable RENZE_PROD_ROOT, or
      3. backend/renze_paths.json  →  {"prod_root": "/absolute/path"}
  Anything else stops with an error, so production can only be used when it is named.

Every root holds: to_be_processed/  processed/ (minutes.db, inference.db)  bad/  control/

Demo inputs (models, data) live in <app>/demo_assets; what to request: demo_assets/MANIFEST.md.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO_ROOT = HERE.parent / 'demo_root'
ASSETS = HERE.parent / 'demo_assets'
MODELS = ASSETS / 'models'
MANIFEST = ASSETS / 'MANIFEST.md'
CONFIG = HERE / 'renze_paths.json'
MODES = ('demo', 'prod')
_MODE_SCHEMA = {'demo': 'synth15', 'prod': 'full49'}   # same table as packet_io.MODE_SCHEMA


def preselect_schema(mode: str) -> str:
    """Set the sensor schema default for `mode` (demo → synth15, prod → full49) unless
    RENZE_SCHEMA is already set. Call before packet_io or db is imported: the schema is chosen
    once per process. Returns the schema name in force."""
    name = os.environ.setdefault('RENZE_SCHEMA', _MODE_SCHEMA[mode])
    pio = sys.modules.get('packet_io')
    if pio is not None and pio.SCHEMA_NAME != name:
        raise RuntimeError(f'packet_io was imported with schema {pio.SCHEMA_NAME!r} before '
                           f'preselect_schema({mode!r}) chose {name!r}')
    return name


MODEL_FILES = ('pipe_rul_v3_traindev.weights.h5', 'pipe_rul_v3_traindev_scaler.pkl',
               'hxg_rul_v3_traindev.weights.h5', 'hxg_rul_v3_traindev_scaler.pkl')


def missing_models() -> list[str]:
    """Model files absent from demo_assets/models/ (see demo_assets/MANIFEST.md)."""
    return [f for f in MODEL_FILES if not (MODELS / f).exists()]


def resolve_root(mode: str, override: Path | None = None) -> Path:
    if mode not in MODES:
        raise SystemExit(f'mode must be one of {MODES}, got {mode!r}')
    if override is not None:
        root = Path(override).expanduser().resolve()
    elif mode == 'demo':
        root = DEMO_ROOT.resolve()
    else:
        env = os.environ.get('RENZE_PROD_ROOT')
        if env:
            root = Path(env).expanduser().resolve()
        elif CONFIG.exists():
            root = Path(json.loads(CONFIG.read_text())['prod_root']).expanduser().resolve()
        else:
            raise SystemExit('production root not set: pass --root, set RENZE_PROD_ROOT, '
                             f'or write {CONFIG.name} with {{"prod_root": "/path"}}')
    demo = DEMO_ROOT.resolve()
    if mode == 'prod' and (root == demo or demo in root.parents or root in demo.parents):
        raise SystemExit(f'production root {root} overlaps the demo root {demo}')
    return root


def layout(root: Path) -> dict[str, Path]:
    """The folders inside a root (created if missing)."""
    d = {
        'tbp': root / 'to_be_processed',
        'tmp': root / 'to_be_processed' / '.tmp',
        'processed': root / 'processed',
        'bad': root / 'bad',
        'control': root / 'control',
    }
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    d['minutes_db'] = d['processed'] / 'minutes.db'
    d['inference_db'] = d['processed'] / 'inference.db'
    d['status'] = d['control'] / 'writer_status.json'
    d['speed'] = d['control'] / 'speed.json'
    return d
