"""Regressions for partial evidence, real knowledge content and permission safety."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx

from app.answer_service import AnswerService, _role_issue, _safe_alternative, _validation_issue
from app.dialogue_state import DialogueManager, DialogueState
from app.llm_client import Generation, GenerationError, generate
from app.rag import SearchResult
from test_expert import settings


# Preserve the observed d720ab3 evidence while the live draft is split/enriched.
# These regressions deliberately exercise the original, incomplete procedure.
CARD = Path(__file__).parent / 'fixtures/aqsi-add-user-d720ab3.txt'
PROCEDURE = CARD.read_text(encoding='utf-8').strip()


@pytest.mark.parametrize('question,raw,required,forbidden', [
    ('Нужен доступ новому сотруднику в aQsi Online, как создать учётную запись?',
     'Перейдите в раздел «Пользователи». Нажмите кнопку «Новая запись». Введите имя и e-mail, затем нажмите «Сохранить». Пользователь получит письмо.',
     ('создаёт новую учётную запись', 'имя и email', 'заранее созданную роль'),
     ('Новая запись', 'Сохранить', 'получит письмо')),
    ('Где отредактировать доступ существующего пользователя aQsi Online?',
     'Откройте раздел «Пользователи». В меню «Настроить доступ» выберите роль «Наблюдатель» для просмотра отчётов.',
     ('Пользователи', 'через меню этой записи'),
     ('Настроить доступ', 'Наблюдатель')),
])
def test_recorded_card_recovers_supported_actions_without_a_second_call(monkeypatch, tmp_path, question, raw, required, forbidden):
    hit = SearchResult('aqsi_online/account/add-user.md', PROCEDURE, .9,
                       metadata={'category': 'account', 'section': 'Что можно объяснить и проверить'})
    rag = SimpleNamespace(search=lambda *args, **kwargs: [hit], build_context=lambda results: PROCEDURE)
    calls = []
    async def recorded(*args):
        calls.append(True)
        return Generation(json.dumps({'scenario': 'answer', 'response': raw}), 'model', 20, 15, 35)
    monkeypatch.setattr('app.answer_service.generate', recorded)
    answer = asyncio.run(AnswerService(rag, settings(tmp_path, groq_reasoning_effort='medium')).answer(question))
    assert len(calls) == 1
    assert answer.scenario == 'answer' and answer.validation_status == 'modified'
    assert all(value in answer.text for value in required)
    assert all(value not in answer.text for value in forbidden)
    assert answer.total_tokens == 35 and answer.raw_model_text
    assert answer.response_repair['removed'] and answer.response_repair['evidence']


def test_neutral_role_wording_and_documented_actions_are_not_permission_claims():
    for answer in ('Роль должна соответствовать задачам сотрудника.',
                   'Назначьте заранее созданную роль.',
                   'Измените существующего пользователя через меню этой записи.',
                   'Создайте учётную запись, укажите имя и e‑mail сотрудника.'):
        assert _validation_issue(answer, PROCEDURE, 'добавление сотрудника') is None
    # The administrator in a procedure is the actor, not a documented role.
    assert _role_issue('Назначьте роль «Администратор».', PROCEDURE) == 'unsupported_role_or_permissions'


def test_procedure_arguments_are_grounded_even_without_an_invalid_button_name(monkeypatch, tmp_path):
    hit = SearchResult('aqsi_online/account/add-user.md', PROCEDURE, .9, metadata={'category': 'account'})
    rag = SimpleNamespace(search=lambda *a, **kw: [hit], build_context=lambda results: PROCEDURE)
    async def model(*args):
        # Different unsupported fields from the observed surname regression:
        # the fix must come from source grounding, not a list of field names.
        return Generation('Создайте сотрудника, укажите телефон и должность.', 'model')
    monkeypatch.setattr('app.answer_service.generate', model)
    answer = asyncio.run(AnswerService(rag, settings(tmp_path)).answer('Как добавить сотрудника в aQsi Online?'))
    assert answer.generation_status == 'generated' and answer.validation_status == 'modified'
    assert answer.validation_reason == 'procedural_details_not_grounded'
    assert 'телефон' not in answer.text and 'должность' not in answer.text
    assert 'имя и email' in answer.text and answer.text.count('учётную запись') == 1


@pytest.mark.parametrize('context,answer,expected', [
    ('Роль «Наблюдатель» позволяет просматривать кассы и отчёты, но не менять настройки.',
     'Назначьте роль «Наблюдатель»: сотрудник сможет смотреть кассы и отчёты, но не сможет менять настройки.', None),
    ('Роль «Администратор» позволяет менять настройки. Роль «Наблюдатель» позволяет смотреть отчёты.',
     'Роль «Наблюдатель» позволяет менять настройки.', 'unsupported_role_or_permissions'),
    ('Роль «Наблюдатель» не позволяет смотреть отчёты, но позволяет менять настройки.',
     'Роль «Наблюдатель» позволяет смотреть отчёты, но не позволяет менять настройки.', 'unsupported_role_or_permissions'),
])
def test_permissions_bind_role_capability_and_local_negation(context, answer, expected):
    assert _role_issue(answer, context) == expected


def test_repair_cannot_use_evidence_outside_the_sent_context():
    question = 'Как создать сотрудника в aQsi Online?'
    state = DialogueManager().advance(DialogueState(), question, 1)
    diagnostics = {}
    text = _safe_alternative('Нажмите кнопку «Неизвестно».', 'unsupported_ui_label:Неизвестно',
                             question, context='Краткое описание сервиса.', state=state,
                             results=[SearchResult('aqsi_online/account/add-user.md', PROCEDURE, .9)],
                             diagnostics=diagnostics)
    assert 'создаёт' not in text and not diagnostics['evidence']


def test_repair_shows_a_documented_matrix_instead_of_claiming_all_role_information_is_missing():
    context = 'Роль «Наблюдатель» позволяет просматривать кассы и отчёты, но не менять настройки.'
    raw = 'С ролью «Владелец» сотрудник может менять настройки.'
    state = DialogueState(intent='access', operation='assign_role')
    issue = _validation_issue(raw, context, 'назначение роли сотруднику')
    assert issue == 'unsupported_role_or_permissions'
    repaired = _safe_alternative(raw, issue, 'назначение роли сотруднику', context=context,
                                  state=state, results=[SearchResult('service/roles.md', context, .9)])
    assert repaired == context and 'Владелец' not in repaired


def test_missing_evidence_is_human_readable_and_does_not_call_a_model(monkeypatch, tmp_path):
    result = SimpleNamespace(documents=[], sufficient=False, insufficiency_reason='no_task_matched_candidates',
                             context='', diagnostics=lambda: {'sufficient': False, 'context': ''})
    rag = SimpleNamespace(search_for_state=lambda *args: result)
    async def forbidden(*args):
        raise AssertionError('No generation without task documentation')
    monkeypatch.setattr('app.answer_service.generate', forbidden)
    answer = asyncio.run(AnswerService(rag, settings(tmp_path)).answer('Как изменить права сотрудника в АТОЛ Онлайн?'))
    assert not answer.llm_call_attempted and answer.generation_status == 'no_context'
    assert 'АТОЛ Онлайн' in answer.text
    assert not any(term in answer.text for term in ('сервис:', 'цель:', 'ограничения:', 'no_task', 'RAG', 'task_category'))
    assert answer.rag_query and answer.retrieval_diagnostics


def test_provider_failure_keeps_safe_status_without_response_body(monkeypatch, tmp_path):
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            return httpx.Response(429, headers={'retry-after': '12'}, text='PRIVATE PROVIDER BODY',
                                  request=httpx.Request('POST', url))
    monkeypatch.setattr('app.llm_client.httpx.AsyncClient', Client)
    with pytest.raises(GenerationError) as caught:
        asyncio.run(generate([], settings(tmp_path)))
    error = caught.value
    assert error.http_status == 429 and error.retry_after_seconds == 12
    assert error.error_type == 'HTTPStatusError'
    assert str(error) == 'LLM request failed'


def test_provider_payload_failure_records_local_stage_without_response_body(monkeypatch, tmp_path):
    class Response:
        def raise_for_status(self): pass
        def json(self): return []

    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return Response()

    monkeypatch.setattr('app.llm_client.httpx.AsyncClient', Client)
    with pytest.raises(GenerationError) as caught:
        asyncio.run(generate([], settings(tmp_path)))
    error = caught.value
    assert error.error_type == 'ValueError'
    assert error.stage == 'validate_payload'
    assert error.cause_message == 'Unexpected completion response'
    assert 'ValueError' in error.traceback_text


def test_empty_completion_failure_is_distinguished_from_http_failure(monkeypatch, tmp_path):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'choices': [{'message': {'content': ''}}]}

    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return Response()

    monkeypatch.setattr('app.llm_client.httpx.AsyncClient', Client)
    with pytest.raises(GenerationError) as caught:
        asyncio.run(generate([], settings(tmp_path)))
    error = caught.value
    assert error.error_type == 'ValueError'
    assert error.stage == 'validate_content'
    assert error.cause_message == 'Empty completion'
