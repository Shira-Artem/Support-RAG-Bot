"""Frozen synthetic P0.1 dialogs; real Groq and read-only Stage3."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from b2_2d_bounded_live_20261105 import CASES, run

root = Path(__file__).resolve().parents[1]
manifest = root / 'reports/b2_2d_20261106/p01_observation_live_manifest.json'
CASES.update(json.loads(manifest.read_text(encoding='utf-8')))
additional = root / 'reports/b2_2d_20261106/p01_observation_live_additional_manifest.json'
CASES.update(json.loads(additional.read_text(encoding='utf-8')))
args = SimpleNamespace(cases='original,independent_observation,future_check,scanner_regression,reported_result',
    output='reports/b2_2d_20261106/p01_observation_live_continued_fix.json', pause=12, runtime_dir=None)
with patch('app.llm_client._MAX_GROQ_429_RETRIES', 0):
    asyncio.run(run(args))
