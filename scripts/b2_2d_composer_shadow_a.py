import asyncio, json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from b2_2d_bounded_live_20261105 import CASES, run
root = Path(__file__).resolve().parents[1]
cases = json.loads((root / 'reports/b2_2d_20261106/composer_shadow_manifest.json').read_text(encoding='utf-8-sig'))
CASES.update(cases)
args = SimpleNamespace(cases=','.join(cases), output='reports/b2_2d_20261106/composer_shadow_a.json', pause=12, runtime_dir=None)
with patch('app.llm_client._MAX_GROQ_429_RETRIES', 0):
    asyncio.run(run(args))
