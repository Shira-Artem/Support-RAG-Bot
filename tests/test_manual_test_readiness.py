import asyncio
import json
from types import SimpleNamespace

import pytest

from app.answer_service import AnswerService
from app.bot_runtime import write_runtime_receipt
from app.dialogue_state import DialogueManager, DialogueState
from app.rag_query import build_rag_query
from app.retrieval_pipeline import RetrievalPipeline
from test_expert import settings
from test_retrieval_pipeline import Source
from app.knowledge import DocumentLoader, Chunker
from app.llm_client import Generation
from app.rag import SearchResult
from pathlib import Path


@pytest.mark.parametrize('message', [
    'Где посмотреть отчёты по кассам после замены ФН в АТОЛ Онлайн?',
    'После замены ФН где посмотреть отчёты в АТОЛ Онлайн?',
    'Как найти отчёт после перерегистрации кассы в АТОЛ Онлайн?',
    'Отчёты после замены ФН где посмотреть в АТОЛ Онлайн?',
])
def test_requested_report_is_not_its_contextual_hardware(message):
    state = DialogueManager().advance(DialogueState(), message, 1)
    assert (state.intent, state.operation, state.object) == ('report', 'view_reports', 'отчёт')
    assert state.routing_service == 'АТОЛ Онлайн'
    query = build_rag_query(state)
    assert 'просмотр отчётов' in query and 'проверка ФН' not in query
    assert message in query  # Keep the requested report kind/conditions grounded.


@pytest.mark.parametrize('message,operation', [
    ('Как создать новую роль в aQsi Online?', 'create_role'),
    ('Как добавить роль в aQsi Online?', 'create_role'),
    ('Как назначить роль сотруднику в aQsi Online?', 'assign_role'),
    ('Как изменить права существующего пользователя в aQsi Online?', 'change_permissions'),
    ('Как поменять роль сотруднику в aQsi Online?', 'change_permissions'),
    ('Как дать доступ существующему сотруднику в aQsi Online?', 'change_permissions'),
    ('Как создать пользователя с ролью «Менеджер» в aQsi Online?', 'add_employee'),
])
def test_role_operation_depends_on_action_and_target(message, operation):
    state = DialogueManager().advance(DialogueState(), message, 1)
    assert state.operation == operation and state.routing_service == 'aQsi Online'


@pytest.mark.parametrize('service', ['aQsi Online', 'АТОЛ Онлайн', 'Платформа ОФД'])
def test_new_employee_access_is_service_agnostic(service):
    state = DialogueManager().advance(
        DialogueState(), f'Как дать новому сотруднику доступ в {service}?', 1)
    assert state.intent == 'access' and state.operation == 'add_employee'


def test_fn_state_question_resolves_to_safe_inspection():
    state = DialogueManager().advance(
        DialogueState(),
        'Как в АТОЛ Онлайн понять, сколько ещё прослужит ФН и насколько он заполнен?',
        1,
    )
    query = build_rag_query(state)
    assert state.intent == 'fiscal_drive'
    assert state.operation == 'check'
    assert state.routing_service == 'АТОЛ Онлайн'
    assert 'проверка' in query and 'ФН' in query
    assert 'прослужит' in query and 'заполнен' in query


def test_ambiguous_employee_access_stays_uncertain():
    state = DialogueManager().advance(
        DialogueState(), 'Как дать сотруднику доступ?', 1)
    assert state.intent == 'access'
    assert state.operation == 'unknown'
    assert state.analysis_required is True


def test_report_query_uses_latest_explicit_request_after_switching_cabinet():
    manager=DialogueManager()
    state=manager.advance(DialogueState(),'Где посмотреть отчёты после замены ФН в АТОЛ Онлайн?',1)
    state=manager.advance(state,'А в aQsi Online где посмотреть отчёты?',2)
    query=build_rag_query(state)
    assert state.operation=='view_reports' and 'aQsi Online' in query
    assert 'АТОЛ' not in query


def test_role_creation_uses_only_matching_card_and_generates_from_partial_evidence(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[1]/'data/knowledge'
    loader = DocumentLoader(root)
    docs = [loader.load(root/'aqsi_online/account'/name) for name in ['add-user.md', 'create-role.md']]
    hits = [SearchResult(doc.source, chunk.text, .04,
                         metadata={**chunk.metadata, 'status': 'approved'})
            for doc in docs for chunk in Chunker().split(doc)]
    articles = {doc.document_id: [h for h in hits if h.metadata['document_id']==doc.document_id] for doc in docs}
    pipeline = RetrievalPipeline(Source(hits, articles))
    state = DialogueManager().advance(DialogueState(), 'Как создать роль в aQsi Online?', 1)
    result = pipeline.search(state, build_rag_query(state))
    assert {h.metadata['document_id'] for h in result.documents} == {'aqsi-online-account-create-role'}
    assert not result.sufficient and result.evidence_status == 'partial'
    assert 'role_creation_workflow_unverified' in result.missing_evidence
    calls = []
    async def fake_generate(messages, config):
        calls.append(messages)
        return Generation(json.dumps({'scenario': 'answer', 'response':
            'Во вкладке «Роли» задайте название роли.'}, ensure_ascii=False), 'stub-model')
    monkeypatch.setattr('app.answer_service.generate', fake_generate)
    answer = asyncio.run(AnswerService(SimpleNamespace(search_for_state=lambda *a: result), settings(tmp_path)).answer('Создать роль', state=state))
    assert 'Полная процедура создания роли' in answer.text
    assert 'задайте название роли' in answer.text and answer.llm_call_attempted and calls


def test_manual_role_dialogue_uses_partial_evidence_in_grounded_generation(monkeypatch, tmp_path):
    fixture = json.loads((Path(__file__).parent/'fixtures/dialogue_regressions_v2.json').read_text(encoding='utf-8'))
    questions = fixture['scenarios']['H']['messages']
    root = Path(__file__).resolve().parents[1]/'data/knowledge'
    loader = DocumentLoader(root)
    docs = [loader.load(root/'aqsi_online/account'/name) for name in ['add-user.md', 'create-role.md']]
    hits = [SearchResult(doc.source, chunk.text, .04,
                         metadata={**chunk.metadata, 'status': 'approved'})
            for doc in docs for chunk in Chunker().split(doc)]
    articles = {doc.document_id: [h for h in hits if h.metadata['document_id']==doc.document_id]
                for doc in docs}
    pipeline = RetrievalPipeline(Source(hits, articles))
    prompts = []
    responses = [
        'Откройте «Пользователи» → «Добавить пользователя».',
        ('Во вкладке «Роли» задайте название роли. Выберите доступные инструменты '
         'и отметьте режим просмотра либо редактирования.'),
        ('Во вкладке «Роли» задайте название роли. Выберите доступные инструменты '
         'и отметьте режим просмотра либо редактирования. Развёрнутые разрешения '
         'на рисунке скрыты.'),
    ]
    async def fake_generate(messages, config):
        prompts.append(messages)
        return Generation(json.dumps({'scenario': 'answer', 'response': responses[len(prompts)-1]},
                                     ensure_ascii=False), 'stub-model')
    monkeypatch.setattr('app.answer_service.generate', fake_generate)
    service = AnswerService(SimpleNamespace(search_for_state=pipeline.search), settings(tmp_path))
    manager, state, answers = DialogueManager(), DialogueState(), []
    for message_id, question in enumerate(questions, 1):
        state = manager.advance(state, question, message_id)
        answers.append(asyncio.run(service.answer(question, state=state)))

    assert answers[1].llm_call_attempted and answers[2].llm_call_attempted
    assert len(prompts) == 3
    third_prompt = prompts[2][1]['content']
    for evidence in ('задайте название роли', 'режим просмотра либо редактирования',
                     'разделы мониторинга, магазинов, касс', 'Развёрнутые разрешения',
                     'проверить доступ тестовой учётной записью'):
        assert evidence in third_prompt
    assert state.goals and state.constraints
    assert 'Конкретная роль и её полномочия' in answers[2].text
    assert not any(role in answers[2].text for role in ('Наблюдатель', 'Читатель', 'Администратор'))


def test_partial_role_generation_still_removes_invented_role(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[1]/'data/knowledge'
    loader = DocumentLoader(root)
    document = loader.load(root/'aqsi_online/account/create-role.md')
    hits = [SearchResult(document.source, chunk.text, .04,
                         metadata={**chunk.metadata, 'status': 'approved'})
            for chunk in Chunker().split(document)]
    pipeline = RetrievalPipeline(Source(hits, {document.document_id: hits}))
    manager, state = DialogueManager(), DialogueState()
    state = manager.advance(state, 'Как назначить роль сотруднику в aQsi Online?', 1)
    state = manager.advance(state, 'Он должен смотреть кассы, но не менять настройки.', 2)
    async def fake_generate(*args):
        return Generation(json.dumps({'scenario': 'answer', 'response':
            'Назначьте роль «Наблюдатель»: она позволяет смотреть кассы без изменения настроек.'},
            ensure_ascii=False), 'stub-model')
    monkeypatch.setattr('app.answer_service.generate', fake_generate)
    answer = asyncio.run(AnswerService(SimpleNamespace(search_for_state=pipeline.search),
                                       settings(tmp_path)).answer('Настройте доступ', state=state))
    assert answer.llm_call_attempted
    assert 'Наблюдатель' not in answer.text
    assert answer.validation_reason == 'unsupported_role_or_permissions'


def test_receipt_uses_actual_collection_instead_of_environment(monkeypatch, tmp_path):
    monkeypatch.setenv('QDRANT_COLLECTION', 'wrong-environment-value')
    store = SimpleNamespace(collection='actual_staging',client=SimpleNamespace(
        get_collection=lambda name: SimpleNamespace(points_count=927)))
    rag = SimpleNamespace(retriever=SimpleNamespace(store=store,demo=True))
    receipt=write_runtime_receipt(settings(tmp_path, llm_provider='groq',groq_reasoning_effort='medium'),rag,tmp_path/'receipt.json')
    assert receipt['collection']=='actual_staging' and receipt['points']==927
    assert receipt['reasoning_effort']=='medium' and 'source_sha256' in receipt
    assert not any('key' in key.lower() or 'token' in key.lower() for key in receipt)
