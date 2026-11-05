"""Cross-domain contracts, independent of LIVE scenario wording."""
import asyncio
import json
from pathlib import Path

import pytest

from app.dialogue_state import DialogueManager, DialogueState
from app.dialogue_understanding import validate_response
from app.conversation_store import ConversationStore
from app.answer_service import Answer
from app.task_operation_resolver import resolve_task_operation


def raw(text, *, intent='general', operation='explain', relation='new_task'):
    return dict(request_type='information', relation=relation, intent=intent,
        operation=operation, object=None, object_evidence=None, goal={'quote':text},
        symptom=None, entities=[], unknown_facts=[], specialist_requested=False,
        specialist_evidence=None, confidence=.95)


@pytest.mark.parametrize('first,next_text,intent,operation', [
    ('В 1С банк списал возврат по эквайрингу. Какая операция?',
     'Нужно сверить исходное списание, чтобы не задвоить возврат.', 'bank_statement','check'),
    ('В aQsi Online добавляем сотрудника.',
     'Теперь для его роли задаём права просмотра.', 'access','configure'),
])
def test_semantic_continuation_keeps_product_through_sqlite_reopen(tmp_path, first, next_text, intent, operation):
    store=ConversationStore(tmp_path/'isolated.sqlite3')
    cid=store.new(1,1)
    first_raw=raw(first,intent='bank_statement' if '1С' in first else 'credentials',operation='explain' if '1С' in first else 'add_employee')
    _,_,_,obs=validate_response(first_raw,first,1)
    manager=DialogueManager()
    state=manager.advance(DialogueState(),first,1,observation=obs)
    _,_,_,obs2=validate_response(raw(next_text,intent=intent,operation=operation,relation='continue'),next_text,2,state)
    continued=manager.advance(state,next_text,2,observation=obs2)
    assert continued.task_id==state.task_id
    assert continued.task_entities==state.task_entities
    assert continued.routing_service==state.routing_service
    # Persist the actual validated observations through the production store.
    for text,payload in [(first,first_raw),(next_text,raw(next_text,intent=intent,operation=operation,relation='continue'))]:
        from app.dialogue_understanding import Understanding,understanding_to_dict
        before=store.dialogue_state(cid)
        kind,specialist,unknown,observation=validate_response(payload,text,'current',before)
        u=Understanding(kind,specialist,tuple(unknown),observation,{},'test',0)
        mid=store.begin(cid,text,semantic_mode=True,understanding=understanding_to_dict(u))
        store.complete(mid,Answer('ok'))
    before=store.dialogue_state(cid)
    after=ConversationStore(tmp_path/'isolated.sqlite3').dialogue_state(cid)
    assert before.to_dict()==after.to_dict()
    assert after.task_entity('software') or after.task_entity('service')
    switched='Новый вопрос: как на Эвотор 6 проверить время?'
    _,_,_,obs3=validate_response(raw(switched,operation='check',relation='continue'),switched,3,after)
    new=manager.advance(after,switched,3,observation=obs3)
    assert new.task_id!=after.task_id
    assert not new.task_entity('software') and not new.task_entity('service')


@pytest.mark.parametrize('text,family,operation', [
    ('Терминал выходит по Wi-Fi, но мобильный интернет через SIM недоступен.', 'network_diagnostics','check'),
    ('В 1С DirectBank активен. Как загрузить банковскую выписку из файла?', 'bank_statement','list'),
    ('В 1С хотим начать акт сверки с поставщиком: какие исходные данные?', 'reconciliation','reconcile'),
])
def test_subject_precedes_coarse_speech_act(text,family,operation):
    resolution=resolve_task_operation(text,operation='explain',intent='general')
    assert (resolution.task_category,resolution.operation)==(family,operation)


def test_secret_boundary_keeps_technical_support_available():
    from app.secret_safety import redact_client_secrets,needs_secret_warning
    assert needs_secret_warning('В другом сервисе ключ доступа: можно отправить вам?')
    assert needs_secret_warning('Не отправляю пароль. Подскажите безопасную диагностику входа.')
    assert not needs_secret_warning('Где в кабинете найти раздел настройки токена?')
    secret='synthetic-credential-98213'
    cleaned=redact_client_secrets('API token='+secret+'; ошибка подключения 403')
    assert secret not in cleaned and '403' in cleaned
    assert redact_client_secrets('Ошибка ФН 234, релиз 3.0.207')=='Ошибка ФН 234, релиз 3.0.207'


def test_capability_fact_is_not_required_to_be_a_definition():
    from app.source_first_service import _conceptually_answering_sentence
    fact='Начиная с версии 3.0.188 поддержан сценарий одного документа поступления товаров и нескольких приходных ордеров для разных складов.'
    assert _conceptually_answering_sentence(fact,'Есть ли возможность поступления товаров на разные склады?')
    assert not _conceptually_answering_sentence('Акт сверки не заменяет первичные документы.','Есть ли возможность поступления товаров на разные склады?')


def test_versions_are_facts_but_numbered_instructions_remain_procedures():
    from app.response_grounding import evidence_kind
    for version in ('3.0.188','2.17.4','1.2'):
        assert evidence_kind(f'С версии {version} поддерживается обмен документами.')=='fact'
    assert evidence_kind('1. Проверьте соединение.')=='procedure'
    assert evidence_kind('Подключите кассу к сети.')=='procedure'


def test_generic_permission_switches_do_not_claim_a_target_privilege():
    from app.retrieval_pipeline import _access_evidence
    from app.rag import SearchResult
    from app.dialogue_state import Fact
    meta=dict(status='approved',operations=['create_role'],evidence_coverage={'create_role':'partial'},section='Создать роль')
    text='Задайте название роли. Выберите режим просмотра либо редактирования.'
    docs=[SearchResult('role.md',text,.9,metadata=meta)]
    state=DialogueState(task_id='task:1',intent='access',operation='create_role')
    state.task=Fact.span('Где задать режим просмотра и редактирования?',1)
    status,missing,steps=_access_evidence(state,docs,text)
    assert status=='partial' and steps
    assert missing==['role_creation_workflow_unverified']
    state.task=Fact.span('Создать роль для просмотра отчётов и изменения касс.',1)
    assert 'requested_role_or_permissions_unverified' in _access_evidence(state,docs,text)[1]


def test_mark_verification_failure_does_not_become_payment_issue():
    resolution=resolve_task_operation('При оплате терминал сообщает: марка не была проверена.',operation='diagnose')
    assert (resolution.task_category,resolution.operation)==('marking','diagnose')


def test_procedure_readiness_does_not_depend_on_provider_optional_goal():
    from app.ai_coordinator import coordinate
    from app.dialogue_state import Fact
    text='Какие предварительные условия нужны для подключения устройства?'
    state=DialogueState(task_id='task:1',intent='general',operation='explain')
    state.task=Fact.span(text,1)
    decision=coordinate({'request_type':'information','observation':{'evidence':{'quote':text},'goals':[]}},state)
    assert decision.route=='technical_action'
    assert state.goals==[]


def test_verified_warning_can_answer_followup_without_reasking_completed_check(monkeypatch):
    from dataclasses import asdict
    from app.config import Settings
    from app.knowledge import DocumentLoader
    from app.llm_client import Generation
    from app.rag import SearchResult
    from app.retrieval_pipeline import EvaluatedDocument,Relevance,RetrievalResult
    import app.source_first_service as module
    root=Path(__file__).resolve().parents[1]
    fixture=json.loads((root/'tests/fixtures/b22d_warning_continuation.json').read_text(encoding='utf-8'))
    state=DialogueState.from_dict(fixture['state'])
    source='evotor/marking/code-check-error-first-steps.md'
    document=DocumentLoader(root/'data/knowledge').load(root/'data/knowledge'/source)
    body=(root/'data/knowledge'/source).read_text(encoding='utf-8').split('---',2)[2]
    chunks=[SearchResult(source,text,.9,metadata={**asdict(document),'section':heading})
            for heading,text in module._sections(body)]
    evaluated=EvaluatedDocument(source,document.document_id,'approved',chunks[0].metadata,{},Relevance('match','match',.9),selected=True)
    retrieval=RetrievalResult('recorded query',[evaluated],[],chunks,True,None,body,evidence_status='relevance_only')
    class RAG:
        def search_for_state(self,*args): return retrieval
    async def select_warning(messages,*args,**kwargs):
        payload=json.loads(messages[1]['content'])
        assert payload['verified_source_order']
        warnings=[item for item in payload['candidate_sections'] if item['section']=='Передать инженеру']
        assert len(warnings)==1
        assert all(item['document_id']==document.document_id for item in payload['candidate_sections'])
        return Generation(json.dumps(dict(mode='select',section_id=warnings[0]['id'],applicability_confirmed=True,source_order_complete=True,reason='Source warning answers permission question')),'offline-test')
    monkeypatch.setattr(module,'generate',select_warning)
    settings=Settings(telegram_bot_token='',openrouter_api_key='',openrouter_model='',app_name='test',app_url='',show_sources=True,docs_dir=root/'data/knowledge',llm_provider='groq',groq_api_key='test',groq_model='openai/gpt-oss-20b',rag_engine='source_first')
    answer=asyncio.run(module.SourceFirstService(RAG(),settings,root).answer(fixture['question'],state=state,
        history=[dict(role='user',content=fixture['question'],understanding=fixture['understanding'],semantic_mode=True)],
        coordinator_decision=fixture['coordinator']))
    assert answer.scenario=='answer'
    assert 'не советуйте обходить ограничения маркировки' in answer.text
    assert 'Удалось выполнить' not in answer.text


def test_client_credential_is_redacted_before_understanding_and_sqlite(monkeypatch,tmp_path):
    import importlib
    import sys
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.config import Settings
    from app.expert_store import ExpertStore
    from app.dialogue_understanding import Understanding
    path=tmp_path/'privacy.sqlite3'
    store=ConversationStore(path)
    cid=store.new(42,42)
    settings=Settings(telegram_bot_token='test',openrouter_api_key='',openrouter_model='',
        app_name='test',app_url='',show_sources=True,docs_dir=tmp_path/'data/knowledge',
        llm_provider='groq',groq_api_key='test',groq_model='test',rag_engine='source_first',
        source_first_telegram_ids=frozenset({42}),ai_coordinator_enabled=True)
    monkeypatch.setattr('app.config.get_settings',lambda:settings)
    monkeypatch.setattr('app.compat.build_answer_rag',lambda *_args:SimpleNamespace())
    monkeypatch.setattr('app.conversation_store.ConversationStore',lambda:store)
    monkeypatch.setattr('app.expert_store.ExpertStore',lambda:ExpertStore(tmp_path/'expert.sqlite3'))
    monkeypatch.setenv('RAG_BACKEND','qdrant')
    monkeypatch.setenv('HANDOFF_ENABLED','0')
    monkeypatch.setattr('qdrant_client.QdrantClient',lambda **_kwargs:SimpleNamespace(
        collection_exists=lambda _name:True,get_collection=lambda _name:SimpleNamespace(points_count=1)))
    sys.modules.pop('bot',None)
    bot=importlib.import_module('bot')
    synthetic='integration-fake-credential-746192'
    captured=[]
    async def understand(text,message_id,*_args):
        assert synthetic not in text and '[REDACTED_SECRET]' in text
        captured.append(text)
        payload=raw(text);payload['goal']=None
        kind,specialist,unknown,obs=validate_response(payload,text,message_id)
        return Understanding(kind,specialist,tuple(unknown),obs,{},'offline',0)
    monkeypatch.setattr(bot,'understand_message',understand)
    monkeypatch.setattr(bot.source_first_service,'answer',AsyncMock(return_value=Answer('Безопасный ответ.')))
    reply=AsyncMock()
    message=SimpleNamespace(text='API token='+synthetic+'; ошибка 403. Можно отправить боту?',
        reply_text=reply,chat=SimpleNamespace(send_action=AsyncMock()))
    update=SimpleNamespace(message=message,effective_message=message,
        effective_user=SimpleNamespace(id=42),effective_chat=SimpleNamespace(id=42))
    try:
        asyncio.run(bot.handle_message(update,None))
        with store.connect() as db:
            rows=db.execute('select content,diagnostics_json from messages where conversation_id=?',(cid,)).fetchall()
        persisted=' '.join(str(tuple(row)) for row in rows)
        assert captured and synthetic not in persisted
        assert '[REDACTED_SECRET]' in persisted
        assert 'Не присылайте токены' in reply.await_args.args[0]
        reopened=ConversationStore(path)
        assert reopened.dialogue_state(cid).to_dict()==store.dialogue_state(cid).to_dict()
    finally:
        sys.modules.pop('bot',None)


def test_secret_warning_survives_provider_failure_without_hiding_source(monkeypatch,tmp_path):
    from app.source_first_service import SourceFirstService
    from app.secret_safety import SECRET_WARNING
    async def approved(*args,**kwargs):
        return Answer('Проверьте обновления ПО. Источник: approved.md')
    service=object.__new__(SourceFirstService)
    monkeypatch.setattr(service,'_answer',approved)
    question='У сервиса токен доступа: отправить его боту?'
    result=asyncio.run(service.answer(question,state=DialogueState()))
    assert SECRET_WARNING in result.text and 'Проверьте обновления ПО' in result.text
    async def failed(*args,**kwargs):
        return Answer('Модель временно недоступна.',generation_status='error')
    monkeypatch.setattr(service,'_answer',failed)
    result=asyncio.run(service.answer(question,state=DialogueState()))
    assert SECRET_WARNING in result.text and result.generation_status=='error'
