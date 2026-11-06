"""Four authorized turns only. Offline replays provider interpretation, not answers.

Offline first-turn Planner responses are historical Groq cassettes. Neither
offline second turn may call Planner: actual Retrieval/SourceFirst must
prove/select the closed contract themselves. Live has no provider substitution
and may use a real Planner when Understanding chooses a different operation.
"""
import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from b2_2d_evidence_live import CASES, run

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'reports/b2_2d_20261105'


async def real_negative_controls(bot, result):
    from app.dialogue_state import DialogueState, Fact, ActiveRoute
    b01 = next(t for t in result['turns'] if t['case'] == 'b01' and t['turn'] == 2)
    h08 = next(t for t in result['turns'] if t['case'] == 'h08' and t['turn'] == 2)
    rows = []
    specs = [
        ('foreign_service', b01, 'Saby: что сверить в возврате?', 'check'),
        ('wrong_operation', b01, 'Как вернуть деньги покупателю?', 'return'),
        ('change_data', b01, 'Как изменить документ возврата?', 'change'),
        ('import', b01, 'Как загрузить банковскую выписку из файла?', 'check'),
        ('foreign_service_h08', h08, 'Saby: можно подтвердить документ?', 'diagnose'),
    ]
    attempted_provider_calls = []
    async def forbidden(*args, **kwargs):
        attempted_provider_calls.append(kwargs.get('call_stage'))
        raise AssertionError('negative control must fail before provider selection')
    with patch('app.source_first_service.generate', forbidden):
        for name, turn, question, operation in specs:
            state = DialogueState.from_dict(turn['state_after'])
            state.operation = operation
            state.task_context.task_fact = Fact.span(question, 99)
            state.task_context.goals = [Fact.span(question, 99)]
            if name.startswith('foreign_service'):
                fact = Fact.span('Saby', 99)
                state.task_context.entities = {'service': [fact]}
                state.task_context.active_route = ActiveRoute('service', fact)
            before = state.to_dict()
            answer = await bot.source_first_service.answer(question, state=state,
                coordinator_decision={'route': 'technical_action'})
            diagnostics = answer.retrieval_diagnostics or {}
            assert not diagnostics.get('source_section_selection'), name
            assert answer.scenario != 'answer', (name, answer.text)
            assert not attempted_provider_calls, name
            assert state.to_dict() == before
            rows.append(dict(control=name, question=question, answer=answer.text,
                scenario=answer.scenario, reason=answer.scenario_reason,
                retrieval=diagnostics, state_unchanged=True, provider_calls_attempted=0))
        # Unknown completion/third-party inspection never grants permission.
        state = DialogueState.from_dict(h08['state_after'])
        before = state.to_dict()
        first = next(t for t in result['turns'] if t['case'] == 'h08' and t['turn'] == 1)
        question = 'Не знаю, проверен ли товар. Можно подписать документ, если сверку сделал поставщик?'
        answer = await bot.source_first_service.answer(question, state=state,
            history=[{'role': 'assistant', 'content': first['answer']}],
            coordinator_decision={'route': 'technical_action'})
        assert 'Не подписывайте УПД до проверки товара.' in answer.text
        assert not answer.progress_update and state.to_dict() == before
        rows.append(dict(control='unconfirmed_condition', question=question, answer=answer.text,
            scenario=answer.scenario, reason=answer.scenario_reason,
            retrieval=answer.retrieval_diagnostics, state_unchanged=True,
            permission_granted=False))
    return rows


async def main(mode, suffix):
    saved = json.loads((FOLDER / 'evidence_contract_live.json').read_text(encoding='utf-8'))
    turns = [t for t in saved['turns'] if t['case'] in {'b01', 'h08'}]
    for cid in ('b01', 'h08'):
        CASES[cid] = [t['question'] for t in turns if t['case'] == cid]
    output = f'reports/b2_2d_20261105/fixes_{mode}_{suffix}.json'
    args = SimpleNamespace(cases='b01,h08', output=output, pause=0 if mode == 'offline' else 12, runtime_dir=None)
    if mode == 'offline':
        args.after_turns = real_negative_controls
    replay_calls = []

    async def replay_post(client, url, *args, **kwargs):
        assert str(url) == 'https://api.groq.com/openai/v1/chat/completions', url
        request = kwargs['json']
        payload = json.loads(request['messages'][-1]['content'])
        if 'current_message' in payload and 'task' in payload:
            turn = next(t for t in turns if t['question'] == payload['current_message'])
            text = json.dumps(saved['understanding_calls'][turn['understanding_call_indices'][-1]]['structured_output'], ensure_ascii=False)
            stage = 'understanding'
        else:
            # No second-turn Planner answer exists in this replay transport.
            turn = next((t for t in turns if t['turn'] == 1 and t['question'] == payload.get('current_message')), None)
            assert turn is not None, 'Second-turn provider call forbidden; closed contract must execute'
            call = saved['generation_calls'][turn['generation_call_indices'][0]]
            assert call['stage'] == 'planner'
            text = call['result']['text']
            stage = 'historical_first_turn_planner'
        replay_calls.append(dict(case=turn['case'], turn=turn['turn'], stage=stage))
        return httpx.Response(200, request=httpx.Request('POST', str(url)), json={
            'id': 'offline-cassette-no-new-provider-call', 'model': request['model'],
            'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}})

    if mode == 'offline':
        with patch.object(httpx.AsyncClient, 'post', replay_post):
            await run(args)
    else:
        # This bounded experiment must stop on the first 429, without even
        # the runtime's usual single short-cooldown retry. No success-path
        # interpretation, retrieval or source selection is substituted.
        with patch('app.llm_client._MAX_GROQ_429_RETRIES', 0):
            await run(args)
    result = json.loads((ROOT / output).read_text(encoding='utf-8'))
    result['validation_kind'] = mode
    result['offline_provider_replay'] = replay_calls
    if mode == 'offline':
        result['pipeline'] = 'bot.handle_message -> replayed historical Understanding -> current reducer/Coordinator -> real read-only Stage3 Retrieval -> current SourceFirst; only first-turn Planner cassettes'
    (ROOT / output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    validate_result(result, mode)


def validate_result(result, mode):
    if result.get('provider_errors'):
        print('Provider error saved; no retry', flush=True)
        return
    assert len(result['turns']) == 4
    assert all(t['sqlite_reopen_equal'] for t in result['turns'])
    b01 = next(t for t in result['turns'] if t['case'] == 'b01' and t['turn'] == 2)
    h08 = next(t for t in result['turns'] if t['case'] == 'h08' and t['turn'] == 2)
    assert 'Сверить документ банка с исходной продажей/возвратом' in b01['answer']
    assert 'не отражать возврат повторно' in b01['answer']
    assert 'Перед подтверждением УПД сверяют' in h08['answer']
    assert 'Не подписывайте УПД до проверки товара.' in h08['answer']
    assert 'Unsupported document version' not in h08['answer']
    if mode == 'offline':
        for turn in (b01, h08):
            assert not turn['generation_call_indices'], 'No preset second-turn Planner/Composer answer allowed'
            selection = turn['diagnostics']['retrieval_diagnostics']['source_section_selection']
            assert selection['provider_calls'] == 0
    assert h08['state_before']['task_context']['shown_units'] == h08['state_after']['task_context']['shown_units']
    assert not any(c.get('status') in {'passed', 'failed'} for c in h08['state_after']['task_context']['checks'])
    print('PASS: actual second-turn selection, grounded answers, no preset second-turn Planner answer, reopen', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('offline', 'live'))
    parser.add_argument('--suffix', default='20261105')
    parser.add_argument('--validate-only', action='store_true', help='Inspect saved output; never send HTTP')
    options = parser.parse_args()
    if options.validate_only:
        path = FOLDER / f'fixes_{options.mode}_{options.suffix}.json'
        result = json.loads(path.read_text(encoding='utf-8'))
        validate_result(result, options.mode)
        result['validation_passed'] = not bool(result.get('provider_errors'))
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        asyncio.run(main(options.mode, options.suffix))
