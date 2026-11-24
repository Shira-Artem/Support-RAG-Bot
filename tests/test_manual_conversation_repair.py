import asyncio
import json
from types import SimpleNamespace

import pytest

from app.ai_coordinator import coordinate
from app.config import Settings
from app.dialogue_state import DialogueState, Fact, TaskContext
from app.dialogue_understanding import UnderstandingError, understand_message
from app.llm_client import Generation
from app.retrieval_pipeline import _state_task_category
from app.source_first_service import (SourceFirstService, _initial_diagnostic_checks,
    _technical_section_covers_observed_subject)
from app.task_operation_resolver import resolve_task_operation


@pytest.mark.parametrize('text', [
    'Касса перестала отправлять чеки', 'Чеки не уходят',
    'Документы перестали передаваться', 'ККТ не отправляет чеки',
])
def test_delivery_failure_has_same_family_across_intent_and_wording(text):
    state = DialogueState(intent='device', operation='diagnose',
        task=Fact(text, 1, text, 0, len(text)))
    assert _state_task_category(state, text) == 'receipt_transmission'
    if 'чек' in text.casefold():
        assert resolve_task_operation(text, operation='diagnose').task_category == 'receipt_transmission'


def test_social_understanding_does_not_require_an_article(tmp_path, monkeypatch):
    import app.source_first_service as module
    settings = Settings('', '', 'unused', 'test', '', False, tmp_path,
        semantic_composer_enabled=True, llm_provider='hubris')
    text = 'Какие задачи вам можно поручить?'
    history = [{'role':'user', 'content':text, 'semantic_mode':True,
                'understanding':{'request_type':'conversation'}}]
    async def generate(messages, settings, **kwargs):
        assert 'ИИ-помощник' in messages[0]['content']
        assert json.loads(messages[-1]['content'])['current_message'] == text
        return Generation('Я ИИ-помощник. Помогаю разобраться с кассами и ОФД простыми словами.', 'offline')
    monkeypatch.setattr(module, 'generate', generate)
    state = DialogueState()
    decision = coordinate(history[-1]['understanding'], state)
    assert decision.route == 'conversation'
    answer = asyncio.run(SourceFirstService(None, settings, tmp_path).answer(
        text, state=state, history=history, coordinator_decision=decision))
    assert answer.scenario == 'answer'


def test_explanation_generator_receives_previous_turns_and_current_question(tmp_path, monkeypatch):
    import app.source_first_service as module
    settings = Settings('', '', 'unused', 'test', '', False, tmp_path, llm_provider='hubris')
    state = DialogueState(intent='general', operation='explain', object='ОФД')
    state.relation = 'continue'
    question = 'А сколько он действует?'
    history = [{'role':'user','content':'Что такое ОФД?'},
               {'role':'assistant','content':'ОФД передаёт данные чеков.'}]
    async def generate(messages, settings, **kwargs):
        payload = json.loads(messages[-1]['content'])
        assert payload['recent_history'] == history
        assert payload['current_message'] == question
        assert 'Не здоровайся повторно' in messages[0]['content']
        return Generation('Срок обслуживания ОФД зависит от выбранного договора.', 'offline')
    monkeypatch.setattr(module, 'generate', generate)
    answer = asyncio.run(SourceFirstService(None, settings, tmp_path)._general_knowledge_fallback(
        question, state, 0, {}, retrieval_checked=False, history=history))
    assert answer.scenario == 'answer'


@pytest.mark.parametrize('code,calls', [('invalid_json',2),('structured_response_shape',2),('transport_error',1)])
def test_hubris_format_recovery_is_bounded_and_not_a_transport_replay(monkeypatch,code,calls):
    import app.dialogue_understanding as module
    seen=[]
    async def once(*args):
        seen.append(args)
        raise UnderstandingError('offline failure',code=code)
    monkeypatch.setattr(module,'_understand_message_once',once)
    with pytest.raises(UnderstandingError):
        asyncio.run(understand_message('Вопрос',1,[],DialogueState(),SimpleNamespace(llm_provider='hubris')))
    assert len(seen)==calls


def test_incident_observation_cannot_enter_the_social_generator(tmp_path,monkeypatch):
    import app.source_first_service as module
    settings = Settings('', '', 'unused', 'test', '', False, tmp_path, llm_provider='hubris')
    state=DialogueState(intent='receipt',operation='diagnose',task=Fact.span('Чеки не уходят',1))
    state.symptom=Fact.span('Чеки не уходят',1)
    decision=coordinate({'request_type':'conversation'},state)
    assert decision.route=='technical_action'
    async def forbidden(*a,**kw):raise AssertionError('No ungrounded diagnostic advice')
    monkeypatch.setattr(module,'generate',forbidden)
    assert asyncio.run(SourceFirstService(None,settings,tmp_path)._general_knowledge_fallback(
        'Интернет доступен',state,0,{},retrieval_checked=False,conversation=True)) is None


def test_initial_diagnosis_offers_first_check_and_preserves_warning():
    def section(heading,text):
        return {'document_id':'independent-guide','section':heading,'text':text}
    symptom=section('Признаки','Документы перестают уходить в сервис.')
    check=section('Шаг 1. Проверка подписки','Проверьте статус подписки в кабинете оператора.')
    warning=section('Важно','Не меняйте настройки без проверки параметров.')
    later=section('Шаг 2. Диагностика','Откройте диагностический отчёт.')
    assert _initial_diagnostic_checks([symptom,later,check,warning])==[check,warning]
    assert _initial_diagnostic_checks([symptom])==[symptom]


def test_first_check_relevance_uses_approved_family_and_confirmed_scope():
    symptom=Fact.span('Касса перестала отправлять чеки',1)
    task=TaskContext(task_id='test',intent='receipt',operation='diagnose',
        task_fact=symptom,symptom=symptom,
        entities={'manufacturer':[Fact.span('Эвотор',2)],'equipment':[Fact.span('Эвотор 7.3',2)]})
    state=DialogueState(task_context=task)
    item={'title':'Проверка связи','section':'Шаг 1. Проверка подписки',
        'text':'Проверьте статус подписки в кабинете оператора.',
        'scope':{'manufacturer':'Эвотор','model':'Эвотор 7.3','service':'Эвотор',
                 'task_category':'receipt_transmission'}}
    assert _technical_section_covers_observed_subject(state,item)
    item['scope']['model']='Эвотор 6'
    assert not _technical_section_covers_observed_subject(state,item)
