"""The existing ordinary explanation uses reducer-owned task context only."""
import asyncio
import json

import pytest
from app.dialogue_state import DialogueState,Fact
from app.llm_client import Generation
from app.source_first_service import SourceFirstService
from test_source_first_dialogue_contract import settings,HISTORICAL_KB_ROOT


@pytest.mark.parametrize('followup',['Не понимаю, объясни проще','Можно пояснить другими словами?','А для чего это нужно?'])
def test_contextual_explanation_uses_saved_subject_without_requiring_its_repetition(tmp_path,monkeypatch,followup):
    original='Объясни, зачем нужен ОФД'
    state=DialogueState(intent='general',operation='explain',object='ОФД',relation='continue',
        task=Fact(original,1,original,0,len(original)))
    async def generate(messages,_settings,**kwargs):
        payload=json.loads(messages[-1]['content'])
        assert payload['current_message']==followup
        assert payload['active_task']['object']=='ОФД'
        return Generation('ОФД получает документы от кассы и передаёт их налоговой службе.','offline-context',prompt_tokens=1,completion_tokens=1,total_tokens=2)
    monkeypatch.setattr('app.source_first_service.generate',generate)
    result=asyncio.run(SourceFirstService(None,settings(tmp_path),HISTORICAL_KB_ROOT)._general_knowledge_fallback(
        followup,state,0,{},retrieval_checked=False))
    assert result.scenario=='answer'
    assert result.retrieval_diagnostics['general_knowledge_fallback']['relevance_basis']=='active_task_and_current_message'


@pytest.mark.parametrize('answer',['Откройте настройки ОФД и измените адрес сервера.','Закройте архив ФН, затем замените накопитель.','ОФД описан здесь: https://invented.example/'])
def test_saved_subject_does_not_allow_unapproved_actions_or_citations(tmp_path,monkeypatch,answer):
    original='Расскажи об ОФД'
    state=DialogueState(intent='general',operation='explain',object='ОФД',relation='continue',
        task=Fact(original,1,original,0,len(original)))
    async def generate(*args,**kwargs):
        return Generation(answer,'offline-negative',prompt_tokens=1,completion_tokens=1,total_tokens=2)
    monkeypatch.setattr('app.source_first_service.generate',generate)
    result=asyncio.run(SourceFirstService(None,settings(tmp_path),HISTORICAL_KB_ROOT)._general_knowledge_fallback(
        'Поясни подробнее',state,0,{},retrieval_checked=False))
    assert result.scenario=='escalate'


def test_new_topic_cannot_pass_relevance_by_repeating_previous_subject(tmp_path,monkeypatch):
    original='Что такое DNS?'
    state=DialogueState(intent='general',operation='explain',object='DNS',relation='new_task',
        task=Fact(original,1,original,0,len(original)))
    async def generate(*args,**kwargs):
        return Generation('ОФД получает документы от кассы.','offline-mismatch',prompt_tokens=1,completion_tokens=1,total_tokens=2)
    monkeypatch.setattr('app.source_first_service.generate',generate)
    result=asyncio.run(SourceFirstService(None,settings(tmp_path),HISTORICAL_KB_ROOT)._general_knowledge_fallback(
        original,state,0,{},retrieval_checked=False))
    assert result.scenario=='escalate'
