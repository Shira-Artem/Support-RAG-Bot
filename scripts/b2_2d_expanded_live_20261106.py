"""Run one named expanded gate case in its own isolated SQLite directory."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from b2_2d_bounded_live_20261105 import CASES, run

root = Path(__file__).resolve().parents[1]
folder = root / 'reports/b2_2d_20261105'
case_id = sys.argv[1]
CASES.update(json.loads((folder / 'expanded_live_manifest_20261106.json').read_text(encoding='utf-8'))['cases'])
if case_id in {'d10', 'm01', 'u01', 'u02'}:
    filenames = {'d10': 'baseline_frozen.json', 'm01': 'regressions_frozen.json',
                 'u01': 'holdout_frozen.json', 'u02': 'holdout_frozen.json'}
    cases = json.loads((folder / filenames[case_id]).read_text(encoding='utf-8'))['cases']
    CASES[case_id] = next(case['turns'] for case in cases if case['id'] == case_id)
assert case_id in {'d10', 'm01', 'u01', 'u02', 'N01', 'N02', 'N03', 'N04', 'N05', 'N06', 'N07', 'negative'}
suffix = sys.argv[2] if len(sys.argv) > 2 else ''
assert suffix in {'', '_after'}
args = SimpleNamespace(cases=case_id, output=f'reports/b2_2d_20261105/expanded_live_20261106_{case_id}{suffix}.json', pause=12, runtime_dir=None)
with patch('app.llm_client._MAX_GROQ_429_RETRIES', 0):
    asyncio.run(run(args))
