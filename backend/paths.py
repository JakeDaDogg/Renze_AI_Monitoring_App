"""
paths.py — resolve the data root for a mode. Demo and production never share a root.

- demo: <app>/demo_root, next to backend/ (created fresh for each demo run).
- prod: set explicitly, never defaulted:
      1. --root on the command line, or
      2. environment variable RENZE_PROD_ROOT, or
      3. backend/renze_paths.json  →  {"prod_root": "/absolute/path"}
  Anything else stops with an error, so production can only be used when it is named.

Every root holds: to_be_processed/  processed/ (minutes.db, inference.db)  bad/  control/
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO_ROOT = HERE.parent / 'demo_root'
CONFIG = HERE / 'renze_paths.json'
MODES = ('demo', 'prod')


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
