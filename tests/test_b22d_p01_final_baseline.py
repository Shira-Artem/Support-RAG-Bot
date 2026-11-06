"""Known P0.1 failures: exact saved Groq outputs, local candidates, disposable DB."""
import json
from unittest.mock import AsyncMock
import pytest
from test_telegram_pilot_sqlite_replay import ROOT, _run_replay

TRACE = json.loads((ROOT / 'reports/b2_2d_20261106/p01_coverage_live_20261106_transfer.json').read_text(encoding='utf8'))


def replay(monkeypatch, tmp_path, *, first_order=None):
    turns = [item for item in TRACE['turns'] if item['case'] == 'P01_transfer_time']
    cases = [dict(id=str(t['turn']), text=t['question'],
                  provider_raw=TRACE['understanding_calls'][t['understanding_call_indices'][-1]]['structured_output'])
             for t in turns]
    plans = {i: json.loads(TRACE['generation_calls'][t['generation_call_indices'][0]]['result']['text'])
             for i, t in enumerate(turns, 1) if t['generation_call_indices']}
    if first_order is not None:
        plans[1]['source_order_complete'] = first_order
    return _run_replay(monkeypatch, tmp_path, cases, sources=('evotor/fn/fn-234.md',),
                       coordinator_enabled=True, validate_with_state=True, planner_overrides=plans)


def test_saved_groq_replacement_question_receives_fact(monkeypatch, tmp_path):
    first, _ = replay(monkeypatch, tmp_path)
    reply = first['final_reply'].casefold()
    assert 'ложное впечатление' in reply and 'замен' in reply
    assert 'одного кода недостаточно' in reply
    assert 'уточните модель' not in reply
    assert 'проверьте' not in reply and 'предлагается проверить' not in reply
    assert 'замена обязательна' not in reply
    assert 'data/knowledge/evotor/fn/fn-234.md — первое различение причины' in reply
    assert not first['state_after_sqlite_reopen']['task_context']['checks']
    assert not first['state_after_sqlite_reopen']['task_context']['shown_units']
    assert not first['state_after_sqlite_reopen']['task_context']['eligible_units']
    assert first['state_after_sqlite_reopen']['task_context']['procedure_id'] is None
    assert first['state_after_sqlite_reopen']['task_context']['expected'] is None
    assert first['state_after_sqlite_reopen']['task_id']


def test_informational_question_does_not_create_check_when_planner_order_is_complete(monkeypatch, tmp_path):
    first, second = replay(monkeypatch, tmp_path, first_order=True)
    assert first['reason'] == 'source_first_incomplete_order_fact'
    assert 'одного кода недостаточно' in first['final_reply'].casefold()
    assert not first['state_after_sqlite_reopen']['task_context']['checks']
    assert second['reason'] == 'source_first_observation_fact'
    assert not second['state_after_sqlite_reopen']['task_context']['checks']


def test_mismatched_indexed_section_never_admits_fact_only_answer(monkeypatch, tmp_path):
    from test_telegram_pilot_sqlite_replay import LocalApprovedCandidates
    original_init = LocalApprovedCandidates.__init__

    def altered_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        for hit in self.hits:
            if hit.metadata.get('section') == 'Первое различение причины':
                hit.text += ' Несовпадающий индексированный фрагмент.'

    monkeypatch.setattr(LocalApprovedCandidates, '__init__', altered_init)
    first, _ = replay(monkeypatch, tmp_path)
    assert first['reason'] != 'source_first_incomplete_order_fact'
    assert 'одного кода недостаточно' not in first['final_reply'].casefold()
    assert not first['state_after_sqlite_reopen']['task_context']['checks']


def test_real_action_request_does_not_take_fact_only_route(monkeypatch, tmp_path):
    turn = next(item for item in TRACE['turns'] if item['case'] == 'P01_transfer_time')
    case = dict(id='action', text=turn['question'] + ' Покажите, как заменить ФН?',
                provider_raw=TRACE['understanding_calls'][turn['understanding_call_indices'][-1]]['structured_output'])
    plan = json.loads(TRACE['generation_calls'][turn['generation_call_indices'][0]]['result']['text'])
    first, = _run_replay(monkeypatch, tmp_path, [case], sources=('evotor/fn/fn-234.md',),
                         coordinator_enabled=True, validate_with_state=True,
                         planner_overrides={1: plan})
    assert first['reason'] != 'source_first_incomplete_order_fact'
    assert 'одного кода недостаточно' not in first['final_reply'].casefold()
    assert not first['state_after_sqlite_reopen']['task_context']['checks']


def test_saved_groq_clock_observation_is_used(monkeypatch, tmp_path):
    first, second = replay(monkeypatch, tmp_path)
    reply = second['final_reply'].casefold()
    assert 'час' in reply and 'ложное впечатление' in reply
    assert first['state_after_sqlite_reopen']['task_context']['task_id'] == second['state_after_sqlite_reopen']['task_context']['task_id']
    first_task = first['state_after_sqlite_reopen']['task_context']
    second_task = second['state_after_sqlite_reopen']['task_context']
    assert any(item['quote'] == 'неверные часы на кассе' for item in second_task['details'])
    for field in ('checks', 'shown_units', 'eligible_units', 'procedure_id'):
        assert first_task[field] == second_task[field]
    assert 'специалист' in reply and 'проверьте' not in reply
    assert 'evotor/fn/fn-234.md — первое различение причины' in reply


def _independent_second_turn(monkeypatch, tmp_path, observation, question, *, source_root=ROOT):
    turns = [item for item in TRACE['turns'] if item['case'] == 'P01_transfer_time']
    first = turns[0]
    second_text = f'{observation}. {question}'
    raw = {'request_type': 'diagnosis', 'relation': 'continue', 'intent': 'device',
           'operation': 'diagnose', 'object': None, 'object_evidence': None,
           'goal': {'quote': question}, 'symptom': {'quote': observation}, 'entities': [],
           'unknown_facts': [], 'specialist_requested': False, 'specialist_evidence': None,
           'confidence': .9}
    cases = [dict(id='first', text=first['question'],
                  provider_raw=TRACE['understanding_calls'][first['understanding_call_indices'][-1]]['structured_output']),
             dict(id='independent', text=second_text, provider_raw=raw)]
    plans = {i: json.loads(TRACE['generation_calls'][turn['generation_call_indices'][0]]['result']['text'])
             for i, turn in enumerate(turns, 1)}
    return _run_replay(monkeypatch, tmp_path, cases, sources=('evotor/fn/fn-234.md',),
                       coordinator_enabled=True, validate_with_state=True, planner_overrides=plans,
                       source_root=source_root)


@pytest.mark.parametrize(('observation', 'question'), [
    ('На экране кассы время отстаёт на несколько часов', 'Может ли это исказить вывод о сроке накопителя?'),
    ('Время на терминале выставлено неправильно', 'Как это связано с выводом о сроке накопителя?'),
])
def test_independent_observation_uses_model_selected_source_fact(monkeypatch, tmp_path, observation, question):
    first, second = _independent_second_turn(monkeypatch, tmp_path, observation, question)
    assert second['reason'] == 'source_first_observation_fact'
    assert observation.casefold() in second['final_reply'].casefold()
    assert 'ложное впечатление' in second['final_reply'].casefold()
    assert 'специалист' in second['final_reply'].casefold()
    assert any(item['quote'] == observation for item in second['state_after_sqlite_reopen']['task_context']['details'])
    for field in ('checks', 'shown_units', 'eligible_units', 'procedure_id'):
        assert first['state_after_sqlite_reopen']['task_context'][field] == second['state_after_sqlite_reopen']['task_context'][field]


@pytest.mark.parametrize('fixture', [
    'p01_observation_live_understanding.json',
    'p01_observation_live_equipment_error.json',
])
def test_saved_live_observation_preserves_task_and_current_fact(monkeypatch, tmp_path, fixture):
    manifest = json.loads((ROOT / 'reports/b2_2d_20261106/p01_observation_live_manifest.json').read_text(encoding='utf-8'))
    raw = json.loads((ROOT / 'tests/fixtures' / fixture).read_text(encoding='utf-8'))
    turns = [item for item in TRACE['turns'] if item['case'] == 'P01_transfer_time']
    plans = {i: json.loads(TRACE['generation_calls'][turn['generation_call_indices'][0]]['result']['text'])
             for i, turn in enumerate(turns, 1)}
    cases = [dict(id=str(index), text=text, provider_raw=raw[index - 1])
             for index, text in enumerate(manifest['independent_observation'], 1)]
    first, second = _run_replay(monkeypatch, tmp_path, cases, sources=('evotor/fn/fn-234.md',),
                                coordinator_enabled=True, validate_with_state=True, planner_overrides=plans)
    assert second['reason'] == 'source_first_observation_fact'
    assert 'время отстаёт на несколько часов' in second['final_reply'].casefold()
    assert 'ложное впечатление' in second['final_reply'].casefold()
    assert first['state_after_sqlite_reopen']['task_id'] == second['state_after_sqlite_reopen']['task_id']
    assert first['state_after_sqlite_reopen']['task_context']['checks'] == []
    assert second['state_after_sqlite_reopen']['task_context']['checks'] == []


def test_unrelated_observation_semantic_rejection_fails_closed(monkeypatch, tmp_path):
    from app.llm_client import Generation
    judge = AsyncMock(return_value=(False, 'answer_does_not_address_current_question_semantically',
                                    {'verdict': 'irrelevant'}, Generation('{}', 'offline', 0, 0, 0)))
    monkeypatch.setattr('app.source_first_service._judge_observation_fact', judge)
    _, second = _independent_second_turn(monkeypatch, tmp_path,
        'В магазине пропал интернет', 'Влияет ли это на вывод о сроке накопителя?')
    assert second['reason'] == 'observation_fact_not_confirmed'
    assert 'ложное впечатление' not in second['final_reply'].casefold()
    assert not second['state_after_sqlite_reopen']['task_context']['checks']


def test_planned_check_is_not_reported_as_a_completed_observation(monkeypatch, tmp_path):
    _, second = _independent_second_turn(monkeypatch, tmp_path,
        'Завтра собираюсь проверить дату и время', 'Влияет ли это на вывод о сроке накопителя?')
    assert second['reason'] != 'source_first_observation_fact'
    checks = second['state_after_sqlite_reopen']['task_context']['checks']
    assert all(check['status'] != 'passed' and not check.get('result_span') for check in checks)


def test_saved_live_future_check_gets_factual_answer_without_result(monkeypatch, tmp_path):
    manifest = json.loads((ROOT / 'reports/b2_2d_20261106/p01_observation_live_manifest.json').read_text(encoding='utf-8'))
    raw = json.loads((ROOT / 'tests/fixtures/p01_observation_future_live.json').read_text(encoding='utf-8'))
    turns = [item for item in TRACE['turns'] if item['case'] == 'P01_transfer_time']
    plans = {i: json.loads(TRACE['generation_calls'][turn['generation_call_indices'][0]]['result']['text'])
             for i, turn in enumerate(turns, 1)}
    cases = [dict(id=str(index), text=text, provider_raw=raw[index - 1])
             for index, text in enumerate(manifest['future_check'], 1)]
    first, second = _run_replay(monkeypatch, tmp_path, cases, sources=('evotor/fn/fn-234.md',),
                                coordinator_enabled=True, validate_with_state=True, planner_overrides=plans)
    assert second['reason'] == 'source_first_continued_fact'
    assert 'одного кода недостаточно' in second['final_reply'].casefold()
    assert 'вы сообщили' not in second['final_reply'].casefold()
    assert first['state_after_sqlite_reopen']['task_id'] == second['state_after_sqlite_reopen']['task_id']
    assert not second['state_after_sqlite_reopen']['task_context']['checks']


def test_future_check_does_not_authorize_a_technical_action(monkeypatch, tmp_path):
    _, second = _independent_second_turn(monkeypatch, tmp_path,
        'Завтра собираюсь проверить дату и время', 'Как закрыть архив ФН?')
    reply = second['final_reply'].casefold()
    assert second['reason'] != 'source_first_continued_fact'
    assert 'откройте' not in reply and 'нажмите' not in reply
    assert all(check['status'] != 'passed' for check in second['state_after_sqlite_reopen']['task_context']['checks'])


def test_reported_result_without_existing_check_is_quoted_but_not_marked_complete(monkeypatch, tmp_path):
    first, second = _independent_second_turn(monkeypatch, tmp_path,
        'Я проверил время на кассе: оно установлено неверно',
        'Меняет ли это вывод о сроке накопителя?')
    assert second['reason'] == 'source_first_observation_fact'
    assert 'проверил время' in second['final_reply'].casefold()
    assert first['state_after_sqlite_reopen']['task_context']['checks'] == []
    assert second['state_after_sqlite_reopen']['task_context']['checks'] == []


def test_uncertain_observation_is_not_reported_as_confirmed(monkeypatch, tmp_path):
    _, second = _independent_second_turn(monkeypatch, tmp_path,
        'Мне кажется, время на терминале неверное', 'Влияет ли это на вывод о сроке накопителя?')
    assert second['reason'] != 'source_first_observation_fact'
    assert 'вы сообщили:' not in second['final_reply'].casefold()


def test_source_changed_during_semantic_judgment_is_rejected(monkeypatch, tmp_path):
    from app.llm_client import Generation
    root = tmp_path / 'source-root'
    relative = 'data/knowledge/evotor/fn/fn-234.md'
    source = root / relative
    source.parent.mkdir(parents=True)
    source.write_bytes((ROOT / relative).read_bytes())

    async def change_after_selection(*_args):
        source.write_text(source.read_text(encoding='utf-8') + '\nизменено', encoding='utf-8')
        return True, 'semantic_relevance_accepted', {'verdict': 'relevant'}, Generation('{}', 'offline', 0, 0, 0)

    monkeypatch.setattr('app.source_first_service._judge_observation_fact', change_after_selection)
    _, second = _independent_second_turn(monkeypatch, tmp_path,
        'Время на терминале выставлено неправильно', 'Как это связано с выводом о сроке накопителя?',
        source_root=root)
    assert second['reason'] == 'observation_fact_source_changed'
    assert 'ложное впечатление' not in second['final_reply'].casefold()
    assert not second['state_after_sqlite_reopen']['task_context']['checks']
