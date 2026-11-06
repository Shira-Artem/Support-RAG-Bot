"""Fixed P0.1 cases and pre-existing independent manifest, real Groq only."""
import asyncio, json, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from b2_2d_bounded_live_20261105 import CASES, run
root = Path(__file__).resolve().parents[1]
expanded = json.loads((root / 'reports/b2_2d_20261105/expanded_live_manifest_20261106.json').read_text(encoding='utf-8'))
independent = json.loads((root / 'reports/b2_2d_20261106/p01_targeted_live_manifest.json').read_text(encoding='utf-8'))
CASES.update({name: expanded['cases'][name] for name in ('N03','N04')})
CASES.update(independent)
transfer = json.loads((root / 'reports/b2_2d_20261106/p01_transfer_manifest_20261106.json').read_text(encoding='utf-8-sig'))
CASES.update(transfer)
run_name = sys.argv[1] if len(sys.argv) > 1 else 'run'
assert run_name in {'repeat', 'transfer'}
case_names = 'N03,N03_new' if run_name == 'repeat' else ','.join(transfer)
args = SimpleNamespace(cases=case_names,
    output='reports/b2_2d_20261106/p01_coverage_live_20261106_' + run_name + '.json', pause=12, runtime_dir=None)
with patch('app.llm_client._MAX_GROQ_429_RETRIES', 0):
    asyncio.run(run(args))
