"""Known P0.1 failures: exact saved Groq outputs, local candidates, disposable DB."""
import json
import pytest
from test_telegram_pilot_sqlite_replay import ROOT, _run_replay

TRACE = json.loads((ROOT / 'reports/b2_2d_20261106/p01_coverage_live_20261106_transfer.json').read_text(encoding='utf8'))


def replay(monkeypatch, tmp_path):
    turns = [item for item in TRACE['turns'] if item['case'] == 'P01_transfer_time']
    cases = [dict(id=str(t['turn']), text=t['question'],
                  provider_raw=TRACE['understanding_calls'][t['understanding_call_indices'][-1]]['structured_output'])
             for t in turns]
    plans = {i: json.loads(TRACE['generation_calls'][t['generation_call_indices'][0]]['result']['text'])
             for i, t in enumerate(turns, 1) if t['generation_call_indices']}
    return _run_replay(monkeypatch, tmp_path, cases, sources=('evotor/fn/fn-234.md',),
                       coordinator_enabled=True, validate_with_state=True, planner_overrides=plans)


@pytest.mark.xfail(strict=True, reason='P0.1: informational answer blocked by incomplete source order')
def test_saved_groq_replacement_question_receives_fact(monkeypatch, tmp_path):
    first, _ = replay(monkeypatch, tmp_path)
    reply = first['final_reply'].casefold()
    assert 'ложное впечатление' in reply and 'замен' in reply
    assert not first['state_after_sqlite_reopen']['task_context']['checks']


@pytest.mark.xfail(strict=True, reason='P0.1: new observation not reflected in answer')
def test_saved_groq_clock_observation_is_used(monkeypatch, tmp_path):
    first, second = replay(monkeypatch, tmp_path)
    reply = second['final_reply'].casefold()
    assert 'час' in reply and 'ложное впечатление' in reply
    assert first['state_after_sqlite_reopen']['task_context']['task_id'] == second['state_after_sqlite_reopen']['task_context']['task_id']
