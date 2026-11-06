"""Offline saved-provider replay, local approved candidates and disposable SQLite only."""
import json
import os
import sys
import tempfile
from pathlib import Path
from pytest import MonkeyPatch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_telegram_pilot_sqlite_replay import _run_replay

saved = json.loads((ROOT / 'reports/b2_2d_20261106/p01_coverage_live_20261106_transfer.json').read_text(encoding='utf-8'))
all_results = {}
for case_id, sources in [
    ('P01_transfer_time', ('evotor/fn/fn-234.md',)),
]:
    turns = [t for t in saved['turns'] if t['case'] == case_id]
    cases = [{'id': f'{case_id}/{t["turn"]}', 'text': t['question'],
              'provider_raw': saved['understanding_calls'][t['understanding_call_indices'][-1]]['structured_output']}
             for t in turns]
    overrides = {}
    for n, turn in enumerate(turns, 1):
        if turn['generation_call_indices']:
            result = saved['generation_calls'][turn['generation_call_indices'][0]]['result']
            overrides[n] = json.loads(result['text'])
    monkeypatch = MonkeyPatch()
    try:
        if os.environ.get('P01_BASELINE') == '1':
            monkeypatch.setattr('app.source_first_service._observation_explanation', lambda *_args: None)
            monkeypatch.setattr('app.source_first_service.SourceFirstService._read_only_handoff_limit',
                                lambda *_args: None)
        with tempfile.TemporaryDirectory(prefix='rag-p01-replay-') as directory:
            all_results[case_id] = _run_replay(monkeypatch, Path(directory), cases,
                sources=sources, coordinator_enabled=True, planner_overrides=overrides,
                validate_with_state=True)
    finally:
        monkeypatch.undo()
output = ROOT / 'reports/b2_2d_20261106/p01_final_offline_baseline.json'
output.write_text(json.dumps(all_results, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
for name, turns in all_results.items():
    for turn in turns:
        print(name, turn['turn'], turn['reason'], turn['final_reply'])
