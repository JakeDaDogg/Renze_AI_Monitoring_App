"""
Quick check of the sensor schema switch in packet_io.py. Run from backend/:

    python tests/test_schema.py

Each schema is chosen once per process, so every case runs in its own interpreter.
full49 must give exactly the values packet_io had before the switch (2026-11-17).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

# packet_io before the schema switch (commit 2962f0c)
FULL49_BEFORE = {
    'HEADER': 'ts,VCB1-Power,VCB1-Voltage-LL-AVG,VCB1-Current-AVG,VCB1-PF,VCB2-Power,'
              'VCB2-Voltage-LL-AVG,VCB2-Current-AVG,VCB2-PF,VCB3-Power,VCB3-Voltage-LL-AVG,'
              'VCB3-Current-AVG,VCB3-PF,PT100,PT101,PV101,PT203,TT203,LIT202,TT202A,LIT101,LV101,'
              'TT101,TT202B,TT202C,PT102,PV102,LIT102,FT102,LV102,FT103,TV103,TT103,LIT103,PT106,'
              'PT104,TT104,VFDB-Power,VFDC-Frequency,VFDC-Power,PT105,FT105,PT204,TT204,ENV-0,'
              'PT205,PT201,TT205,TT201,PT104S',
    'MODEL_FEAT_INDICES': [0, 4, 12, 13, 14, 19, 20, 21, 27, 29, 43],
    'VCB2_IDX': 4,
    'N_COLS': 50,
    'N_CANON': 48,
}
MODEL_11 = ['VCB1-Power', 'VCB2-Power', 'PT100', 'PT101', 'PV101', 'LIT101', 'LV101', 'TT101',
            'FT102', 'FT103', 'ENV-0']
DECISION = ['TT203', 'PT100', 'PT105', 'LIT101', 'PT106', 'LV102']   # maint_recovery.py sensors

PROBE = """
import json, packet_io as p
print(json.dumps({'SCHEMA': p.SCHEMA_NAME, 'HEADER': p.HEADER, 'MODEL_FEAT_INDICES': p.MODEL_FEAT_INDICES,
  'VCB2_IDX': p.VCB2_IDX, 'N_COLS': p.N_COLS, 'N_CANON': len(p.CANON_SENSOR_COLS),
  'CANON': p.CANON_SENSOR_COLS, 'MODEL': [p.CANON_SENSOR_COLS[i] for i in p.MODEL_FEAT_INDICES]}))
"""


def probe(code: str, **env) -> dict:
    e = {k: v for k, v in os.environ.items() if k != 'RENZE_SCHEMA'} | env
    out = subprocess.run([sys.executable, '-c', code], cwd=BACKEND, env=e,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def main() -> None:
    full = probe(PROBE, RENZE_SCHEMA='full49')
    for k, v in FULL49_BEFORE.items():
        assert full[k] == v, f'full49 {k}: {full[k]!r} != {v!r}'
    assert full['MODEL'] == MODEL_11

    syn = probe(PROBE, RENZE_SCHEMA='synth15')
    assert syn['N_COLS'] == 16 and syn['N_CANON'] == 15 and 'PT104S' not in syn['CANON']
    assert syn['MODEL'] == MODEL_11, syn['MODEL']
    assert syn['CANON'][syn['VCB2_IDX']] == 'VCB2-Power'
    assert set(DECISION) <= set(syn['CANON'])

    # mode defaults (via paths.preselect_schema) and the RENZE_SCHEMA override
    pre = "import paths, sys; paths.preselect_schema(sys.argv[1]);" + PROBE
    assert probe(pre.replace('sys.argv[1]', "'demo'"))['SCHEMA'] == 'synth15'
    assert probe(pre.replace('sys.argv[1]', "'prod'"))['SCHEMA'] == 'full49'
    assert probe(pre.replace('sys.argv[1]', "'demo'"), RENZE_SCHEMA='full49')['SCHEMA'] == 'full49'
    assert probe(PROBE)['SCHEMA'] == 'full49'                     # nothing set → full49
    # db.py labels a new DB with its sensor schema and refuses a DB of the other schema
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        mk = (f"import db, pathlib; db.open_db(pathlib.Path({tmp!r}) / 'm.db', 'minutes', 'demo')"
              ".close(); print('{}')")
        probe(mk, RENZE_SCHEMA='full49')
        r = subprocess.run([sys.executable, '-c', mk], cwd=BACKEND, capture_output=True, text=True,
                           env=os.environ | {'RENZE_SCHEMA': 'synth15'})
        assert r.returncode != 0 and "sensor schema 'full49'" in r.stderr, r.stderr
        probe(mk, RENZE_SCHEMA='full49')                               # same schema reopens

    print('schema checks passed: full49 unchanged, synth15 consistent, mode defaults, '
          'override, db refuses the other schema')


if __name__ == '__main__':
    main()
