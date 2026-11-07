"""Client-visible continuation and ledger checks through bot.handle_message."""
import json
from pathlib import Path
import pytest
from test_telegram_pilot_sqlite_replay import _run_replay, ROOT

TRACE = json.loads((ROOT / 'reports/b2_2d_20261106/p01_live_final.json').read_text(encoding='utf-8'))
TURNS = [t for t in TRACE['turns'] if t['case'] == 'N04']
SECTION = 'evotor-fn-234-360005580254::Первое различение причины'


def run_dialogue(monkeypatch, tmp_path, second=None):
    cases = [{'id': f'N04/{t["turn"]}', 'text': t['question'],
              'provider_raw': TRACE['understanding_calls'][t['understanding_call_indices'][-1]]['structured_output']}
             for t in TURNS]
    if second is not None:
        cases[1] = {'id':'independent', 'text':second, 'provider_raw': {
            'request_type':'information', 'relation':'continue', 'intent':'unknown',
            'operation':'diagnose', 'object':None, 'object_evidence':None,
            'goal':{'quote':second} if '?' in second else None, 'symptom':None,
            'entities':[], 'unknown_facts':[], 'specialist_requested':False,
            'specialist_evidence':None, 'confidence':.9}}
    planner = {i: {'mode':'select','section_id':SECTION,'applicability_confirmed':True,
                    'source_order_complete':True,'reason':'saved approved section'} for i in (1,2)}
    return _run_replay(monkeypatch, tmp_path, cases, sources=('evotor/fn/fn-234.md',),
                       coordinator_enabled=True, validate_with_state=True, planner_overrides=planner)


def test_n04_reported_observation_explained_without_advancing_check(monkeypatch, tmp_path):
    first, second = run_dialogue(monkeypatch, tmp_path)
    answer = second['final_reply'].casefold()
    assert 'неправильные' in answer and 'неверное время может создать ложное впечатление' in answer
    assert 'специалист' in answer and 'настройки →' not in answer
    assert 'evotor/fn/fn-234.md' in answer
    before = first['state_after_sqlite_reopen']['task_context']['checks']
    after = second['state_after_sqlite_reopen']['task_context']['checks']
    assert len(after) == len(before) == 1
    assert before[0]['unit_id'] == after[0]['unit_id'] and after[0]['status'] == 'asked'
    assert not after[0].get('result_span')


@pytest.mark.parametrize('message', [
    'Я собираюсь проверить дату и время. Что теперь проверить?',
    'Пока не проверял дату и время. Что теперь проверить?',
    'Дата и время на кассе неверные?',
])
def test_future_or_question_does_not_claim_observation(monkeypatch, tmp_path, message):
    _, turn = run_dialogue(monkeypatch, tmp_path, message)
    assert turn['reason'] != 'source_first_observation_explanation'
    checks = turn['state_after_sqlite_reopen']['task_context']['checks']
    assert all(item['status'] != 'passed' for item in checks)
    assert 'неверное время может создать ложное впечатление' not in turn['final_reply'].casefold()

@pytest.mark.parametrize(('message','status'), [
    ('Дата и время верны. Что теперь проверить?', 'passed'),
    ('Дата верна. Что теперь проверить?', 'unknown'),
    ('Время верно. Что теперь проверить?', 'unknown'),
    ('Дата верна, время неправильное. Что теперь проверить?', 'failed'),
    ('Проверил дату и время, они не совпадают. Что теперь проверить?', 'failed'),
])
def test_explicit_check_result_keeps_real_ledger_outcome(monkeypatch, tmp_path, message, status):
    _, turn = run_dialogue(monkeypatch, tmp_path, message)
    checks = turn['state_after_sqlite_reopen']['task_context']['checks']
    assert any(check['status'] == status and check.get('result_span') for check in checks)
    assert turn['reason'] != 'source_first_observation_explanation'
    subjects = checks[0].get('subject_results', [])
    if 'верн' in message and 'не совпадают' not in message:
        assert len({item['subject'] for item in subjects}) == 2
    if 'неправильное' in message:
        assert {item['status'] for item in subjects} == {'passed', 'failed'}


def test_new_task_does_not_reuse_old_observation_or_ledger(monkeypatch, tmp_path):
    first = TURNS[0]
    text = 'Новый вопрос: как найти чек в Платформе ОФД?'
    cases = [dict(id='first', text=first['question'],
                  provider_raw=TRACE['understanding_calls'][first['understanding_call_indices'][-1]]['structured_output']),
             dict(id='switch', text=text, provider_raw={
                 'request_type':'information', 'relation':'new_task', 'intent':'receipt',
                 'operation':'search', 'object':'чек', 'object_evidence':{'quote':'чек'},
                 'goal':{'quote':text}, 'symptom':None,
                 'entities':[{'slot':'service','value':'Платформа ОФД','evidence':{'quote':'Платформе ОФД'}}],
                 'unknown_facts':[], 'specialist_requested':False, 'specialist_evidence':None, 'confidence':.95})]
    trace = _run_replay(monkeypatch, tmp_path, cases, coordinator_enabled=True, validate_with_state=True,
                        sources=('evotor/fn/fn-234.md','platformaofd/ofd/lkk-receipt-search.md'))
    task = trace[1]['state_after_sqlite_reopen']['task_context']
    assert trace[1]['state']['task_changed']
    assert all('fn-234.md' not in str(check.get('source')) for check in task['checks'])
    assert 'время может создать' not in trace[1]['final_reply'].casefold()


def run_scanner(monkeypatch, tmp_path, second=None, raw_override=None, sources=None):
    turns = [t for t in TRACE['turns'] if t['case'] == 'N03']
    cases = [{'id':f'N03/{t["turn"]}', 'text':t['question'],
              'provider_raw':TRACE['understanding_calls'][t['understanding_call_indices'][-1]]['structured_output']}
             for t in turns]
    if second is not None:
        cases[1] = {'id':'other', 'text':second, 'provider_raw':raw_override or {
            'request_type':'information', 'relation':'continue', 'intent':'device', 'operation':'diagnose',
            'object':None,'object_evidence':None,'goal':{'quote':second},'symptom':None,
            'entities':[], 'unknown_facts':[], 'specialist_requested':False,
            'specialist_evidence':None,'confidence':.9}}
    plans = {i: json.loads(TRACE['generation_calls'][t['generation_call_indices'][0]]['result']['text'])
             for i,t in enumerate(turns,1)}
    return _run_replay(monkeypatch, tmp_path, cases, coordinator_enabled=True, validate_with_state=True,
        planner_overrides=plans, sources=sources or ('aqsi_devices/peripherals/scanner.md',
                                                    'aqsi_devices/errors/goods-not-on-device.md'))


def test_n03_conditional_limit_does_not_advance_previous_check(monkeypatch, tmp_path):
    first, second = run_scanner(monkeypatch, tmp_path)
    answer = second['final_reply'].casefold()
    assert 'гарантирован' in answer and 'usb' in answer and 'специалист' in answer
    assert 'если стандартные проверки не помогли' in answer
    assert 'aqsi_devices/peripherals/scanner.md' in answer
    before=first['state_after_sqlite_reopen']['task_context']['checks']
    after=second['state_after_sqlite_reopen']['task_context']['checks']
    assert [(x['unit_id'],x['status']) for x in before] == [(x['unit_id'],x['status']) for x in after]


@pytest.mark.parametrize('question', [
    'Гарантирует ли смена режима USB работу стороннего сканера?',
    'Можно ли переключить USB у внешнего сканера для гарантированного результата?',
])
def test_new_scanner_questions_keep_source_condition(monkeypatch, tmp_path, question):
    first, turn = run_scanner(monkeypatch, tmp_path, question)
    assert turn['reason'] == 'source_first_rejected_handoff_limit'
    assert 'если стандартные проверки не помогли' in turn['final_reply'].casefold()
    assert [(x['unit_id'],x['status']) for x in first['state_after_sqlite_reopen']['task_context']['checks']] == [
        (x['unit_id'],x['status']) for x in turn['state_after_sqlite_reopen']['task_context']['checks']]


def test_request_for_instructions_does_not_enter_informational_bypass(monkeypatch,tmp_path):
    _, turn = run_scanner(monkeypatch,tmp_path, 'Как настроить USB у внешнего сканера?')
    assert turn['reason'] != 'source_first_rejected_handoff_limit'
    assert 'передать специалисту, если стандартные проверки' not in turn['final_reply'].casefold()


def test_missing_approved_article_does_not_invent_usb_answer(monkeypatch,tmp_path):
    _, turn=run_scanner(monkeypatch,tmp_path,sources=('aqsi_devices/errors/goods-not-on-device.md',))
    assert turn['reason'] != 'source_first_rejected_handoff_limit'
    assert 'источник: data/knowledge/aqsi_devices/peripherals/scanner.md' not in turn['final_reply'].casefold()

@pytest.mark.parametrize(('question','slot','value'), [
    ('Новый вопрос: в aQsi Online можно изменить USB режим внешнего сканера?', 'service', 'aQsi Online'),
    ('Новый вопрос: для АТОЛ можно изменить USB режим внешнего сканера?', 'manufacturer', 'АТОЛ'),
])
def test_handoff_limit_does_not_cross_product_scope(monkeypatch,tmp_path,question,slot,value):
    raw={'request_type':'information','relation':'new_task','intent':'device','operation':'diagnose',
         'object':None,'object_evidence':None,'goal':{'quote':question},'symptom':None,
         'entities':[{'slot':slot,'value':value,'evidence':{'quote':value}}],
         'unknown_facts':[],'specialist_requested':False,'specialist_evidence':None,'confidence':.9}
    _,turn=run_scanner(monkeypatch,tmp_path,question,raw)
    assert turn['reason'] != 'source_first_rejected_handoff_limit'
    assert 'aqsi_devices/peripherals/scanner.md — когда передавать специалисту' not in turn['final_reply'].casefold()
    assert all('scanner.md' not in str(x.get('source','')) for x in turn['state_after_sqlite_reopen']['task_context']['checks'])

def test_scanner_compatibility_question_is_limited_to_conditional_handoff(monkeypatch,tmp_path):
    first,turn = run_scanner(monkeypatch,tmp_path, 'Совместим ли внешний сканер с USB режимом?')
    assert turn['reason'] == 'source_first_rejected_handoff_limit'
    text=turn['final_reply'].casefold()
    assert 'сканера' in text and 'usb' in text and 'если стандартные проверки не помогли' in text
    assert 'подключите' not in text and 'нажмите' not in text
    assert [x['status'] for x in first['state_after_sqlite_reopen']['task_context']['checks']] == [
        x['status'] for x in turn['state_after_sqlite_reopen']['task_context']['checks']]


def test_independent_scanner_diagnosis_first_turn_reaches_approved_evidence(monkeypatch,tmp_path):
    turn=next(t for t in TRACE['turns'] if t['case']=='P01_aQsi_paraphrase' and t['turn']==1)
    raw=TRACE['understanding_calls'][turn['understanding_call_indices'][-1]]['structured_output']
    saved_plan=json.loads(TRACE['generation_calls'][turn['generation_call_indices'][0]]['result']['text'])
    trace=_run_replay(monkeypatch,tmp_path,[{'id':'independent-first','text':turn['question'],'provider_raw':raw}],
        coordinator_enabled=True,validate_with_state=True,planner_overrides={1:saved_plan},
        sources=('aqsi_devices/peripherals/scanner.md','aqsi_devices/errors/goods-not-on-device.md'))
    reply=trace[0]['final_reply'].casefold()
    assert 'aqsi_devices/peripherals/scanner.md' in reply
    assert 'проверьте' in reply or 'свер' in reply


def test_conditional_inspection_must_match_the_reported_scanner_symptom(monkeypatch, tmp_path):
    question = 'Касса aQsi не видит USB сканер. Что проверить?'
    _, turn = run_scanner(monkeypatch, tmp_path, question)
    assert turn['reason'] != 'source_first_rejected_conditional_inspection'
    assert 'состояние наклейки' not in turn['final_reply'].casefold()


def test_unchecked_compound_does_not_pass(monkeypatch, tmp_path):
    _, turn = run_dialogue(monkeypatch, tmp_path, 'Пока не проверял дату и время.')
    checks = turn['state_after_sqlite_reopen']['task_context']['checks']
    assert all(check['status'] != 'passed' for check in checks)


@pytest.mark.parametrize(('question', 'service'), [
    ('На aQsi Online DataMatrix читается плохо. Что проверить?', 'aQsi Online'),
    ('Для АТОЛ DataMatrix читается плохо. Что проверить?', 'АТОЛ'),
])
def test_rejected_inspection_does_not_cross_first_turn_scope(monkeypatch, tmp_path, question, service):
    slot = 'service' if 'Online' in service else 'manufacturer'
    raw = {'request_type':'diagnosis','relation':'new_task','intent':'device','operation':'diagnose',
           'object':None,'object_evidence':None,'goal':{'quote':question},'symptom':None,
           'entities':[{'slot':slot,'value':service,'evidence':{'quote':service}}],
           'unknown_facts':[],'specialist_requested':False,'specialist_evidence':None,'confidence':.9}
    trace = _run_replay(monkeypatch,tmp_path,[{'id':'negative','text':question,'provider_raw':raw}],
        coordinator_enabled=True,validate_with_state=True,
        sources=('aqsi_devices/peripherals/scanner.md','aqsi_devices/errors/goods-not-on-device.md'))
    assert trace[0]['reason'] != 'source_first_rejected_conditional_inspection'
    assert 'aqsi_devices/peripherals/scanner.md' not in trace[0]['final_reply']


def test_rejected_inspection_refuses_modification_request(monkeypatch,tmp_path):
    question = 'На aQsi DataMatrix не читается. Как переключить режим USB?'
    raw = {'request_type':'diagnosis','relation':'new_task','intent':'device','operation':'diagnose',
           'object':None,'object_evidence':None,'goal':{'quote':question},'symptom':None,
           'entities':[{'slot':'manufacturer','value':'aQsi','evidence':{'quote':'aQsi'}}],
           'unknown_facts':[],'specialist_requested':False,'specialist_evidence':None,'confidence':.9}
    trace = _run_replay(monkeypatch,tmp_path,[{'id':'action','text':question,'provider_raw':raw}],
        coordinator_enabled=True,validate_with_state=True,
        sources=('aqsi_devices/peripherals/scanner.md','aqsi_devices/errors/goods-not-on-device.md'))
    assert trace[0]['reason'] != 'source_first_rejected_conditional_inspection'


@pytest.mark.parametrize(('last','expected'), [
    ('Время верно.', 'passed'),
    ('Время неправильное.', 'failed'),
])
def test_compound_subjects_accumulate_across_sqlite_reopens(monkeypatch, tmp_path, last, expected):
    first = TURNS[0]
    messages = ['Дата верна.', last]
    cases = [{'id':'first','text':first['question'],
              'provider_raw':TRACE['understanding_calls'][first['understanding_call_indices'][-1]]['structured_output']}]
    for text in messages:
        cases.append({'id': text, 'text': text, 'provider_raw': {
            'request_type':'information','relation':'continue','intent':'unknown','operation':'diagnose',
            'object':None,'object_evidence':None,'goal':None,'symptom':None,'entities':[],
            'unknown_facts':[],'specialist_requested':False,'specialist_evidence':None,'confidence':.9}})
    planner = {i:{'mode':'select','section_id':SECTION,'applicability_confirmed':True,
                  'source_order_complete':True,'reason':'approved section'} for i in (1,2,3)}
    turns = _run_replay(monkeypatch,tmp_path,cases,sources=('evotor/fn/fn-234.md',),
                        coordinator_enabled=True,validate_with_state=True,planner_overrides=planner)
    checks = turns[-1]['state_after_sqlite_reopen']['task_context']['checks']
    assert checks[0]['status'] == expected
    assert len({x['subject'] for x in checks[0]['subject_results']}) == 2


def test_ambiguous_mixed_clause_never_attributes_failure_to_both_subjects(monkeypatch, tmp_path):
    _, turn = run_dialogue(monkeypatch, tmp_path, 'Дата верна и время неправильное.')
    check = turn['state_after_sqlite_reopen']['task_context']['checks'][0]
    records = check.get('subject_results', [])
    assert not (len(records) == 2 and all(item['status'] == 'failed' for item in records))
    assert check['status'] != 'passed'


def test_n03_initial_turn_shows_a_real_check_not_a_fact(monkeypatch, tmp_path):
    first, _ = run_scanner(monkeypatch, tmp_path)
    answer = first['final_reply'].casefold()
    assert 'если код не читается' in answer and 'проверьте' in answer
    checks = first['state_after_sqlite_reopen']['task_context']['checks']
    assert len(checks) == 1 and 'проверьте' in checks[0]['label'].casefold()
    assert 'совместимость зависит' not in checks[0]['label'].casefold()


def test_live_continuation_with_change_intent_keeps_confirmed_scope(monkeypatch, tmp_path):
    live = json.loads((ROOT / 'reports/b2_2d_20261106/p01_coverage_live_20261106_after.json').read_text(encoding='utf8'))
    turns = [t for t in live['turns'] if t['case'] == 'N03']
    cases = [{'id':str(t['turn']), 'text':t['question'],
              'provider_raw':live['understanding_calls'][t['understanding_call_indices'][-1]]['structured_output']}
             for t in turns]
    result = _run_replay(monkeypatch,tmp_path,cases,coordinator_enabled=True,validate_with_state=True,
        sources=('aqsi_devices/peripherals/scanner.md','aqsi_devices/errors/goods-not-on-device.md'))
    first = result[0]['state_after_sqlite_reopen']['task_context']
    second = result[1]['state_after_sqlite_reopen']['task_context']
    assert second['task_id'] == first['task_id']
    assert second['active_route'] == first['active_route']
    assert second['operation'] == 'change'  # Scope retention never grants the action.
    assert 'если стандартные проверки не помогли' in result[1]['final_reply'].casefold()


def test_live_new_wording_certainty_question_keeps_handoff_condition(monkeypatch, tmp_path):
    live = json.loads((ROOT / 'reports/b2_2d_20261106/p01_coverage_live_20261106_after.json').read_text(encoding='utf8'))
    turns = [t for t in live['turns'] if t['case'] == 'N03_new']
    cases = [{'id':str(t['turn']), 'text':t['question'],
              'provider_raw':live['understanding_calls'][t['understanding_call_indices'][-1]]['structured_output']}
             for t in turns]
    result = _run_replay(monkeypatch,tmp_path,cases,coordinator_enabled=True,validate_with_state=True,
        sources=('aqsi_devices/peripherals/scanner.md','aqsi_devices/errors/goods-not-on-device.md'))
    assert 'если стандартные проверки не помогли' in result[1]['final_reply'].casefold()
    assert result[1]['state_after_sqlite_reopen']['task_context']['task_id'] == result[0]['state_after_sqlite_reopen']['task_context']['task_id']
