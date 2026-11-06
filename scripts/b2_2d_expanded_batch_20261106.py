"""Serial isolated LIVE cases; stop on incomplete run or provider failure."""
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for case, expected in [('m01', 2), ('u01', 1), ('u02', 1), ('N01', 2), ('N02', 2),
                       ('N03', 2), ('N04', 2), ('N05', 2), ('N06', 2), ('N07', 1), ('negative', 1)]:
    print('Starting', case, flush=True)
    result = subprocess.run([sys.executable, '-u', str(root / 'scripts/b2_2d_expanded_live_20261106.py'), case], cwd=root)
    path = root / f'reports/b2_2d_20261105/expanded_live_20261106_{case}.json'
    if result.returncode or not path.exists():
        print('Stopped: runner failed', case, result.returncode, flush=True)
        break
    data = json.loads(path.read_text(encoding='utf-8'))
    if len(data['turns']) != expected or data.get('provider_errors'):
        print('Stopped: incomplete or provider error', case, flush=True)
        break
    print('Completed', case, flush=True)
