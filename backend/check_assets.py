"""
check_assets.py — compare the local demo_assets/ files with demo_assets/MANIFEST.md.

    python check_assets.py

Reads every manifest table row that carries a sha256 (columns: file | target path | size | sha256 …),
hashes the local file and prints ok / MISSING / MISMATCH. Exit code 1 if anything is missing or
different. Files you do not have: request them as MANIFEST.md says.
"""
from __future__ import annotations

import hashlib
import re
import sys

from paths import ASSETS, MANIFEST

_ROW = re.compile(r'^\|\s*`?([^|`]+?)`?\s*\|\s*`?([^|`]+?)`?\s*\|[^|]*\|\s*`?([0-9a-f]{64})`?\s*\|')


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    if not MANIFEST.exists():
        print(f'{MANIFEST} not found')
        return 1
    rows = [m.groups() for line in MANIFEST.read_text().splitlines() if (m := _ROW.match(line))]
    bad = 0
    for name, target, digest in rows:
        path = ASSETS.parent / target
        if not path.exists():
            print(f'MISSING   {target}')
            bad += 1
        elif sha256(path) != digest:
            print(f'MISMATCH  {target}')
            bad += 1
        else:
            print(f'ok        {target}')
    print(f'{len(rows) - bad} of {len(rows)} files ok' + (' — see demo_assets/MANIFEST.md' if bad else ''))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
