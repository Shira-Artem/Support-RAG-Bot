"""Offline regressions for the P0 free-dialogue response contract.

The model is stubbed in every test.  The fixtures deliberately contain generic
access documentation so the assertions exercise the grounding contract rather
than a product-specific exception.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.answer_service import AnswerService
from app.dialogue_state import DialogueManager, DialogueState
from app.llm_client import Generation
from app.rag import SearchResult
from app.retrieval_pipeline import RetrievalResult
from test_expert import settings


ROLE_CONTEXT = (
    "Во вкладке «Роли» задайте название роли. "
    "Выберите доступные инструменты и отметьте режим просмотра либо редактирования. "
    "Внизу формы можно выбрать пользователей для назначения роли.\n\n"
    "Текст статьи называет блок «Расширения», а официальный рисунок 30 — «Разрешения». "
    "На рисунке видны разделы мониторинга, магазинов, касс, документов, пользователей, "
    "чеков и услуг с колонками просмотра и редактирования. Это пример настроенной роли, "
    "а не обязательный набор прав для каждой роли.\n\n"
    "Развёрнутые разрешения на рисунке скрыты. Нельзя обещать права на конкретный отчёт "
    "или изменение кассы по одному названию раздела. Для задачи «только смотреть кассы "
    "и отчёты» специалист должен сверить актуальные подразделы и проверить доступ тестовой "
    "учётной записью.\n\n"
    "Откройте «Пользователи» → «Добавить пользователя». Заполните имя и email, "
    "назначьте предварительно созданную роль из вкладки «Роли» и сохраните форму."
)


def _retrieval(*, context: str, operation: str, full: bool, missing=()):
    hit = SearchResult(
        "generic/access-guide.md", context, 0.9,
        metadata={
            "document_id": "generic-access-guide", "service": "aQsi Online",
            "task_category": "access", "operations": [operation],
            "status": "approved", "evidence_coverage": {operation: "full" if full else "partial"},
        },
    )
    steps = [{"source": hit.source, "text": line} for line in context.split("\n")
             if line and not line.startswith("Текст статьи")]
    return RetrievalResult(
        "access workflow", [], [], [hit], full, None if full else "access_evidence_incomplete",
        context, evidence_status="full" if full else "partial",
        missing_evidence=list(missing), supported_steps=steps,
    )


def test_confirmed_add_employee_steps_survive_paraphrase(monkeypatch, tmp_path):
    context = 'Откройте «Пользователи» → «Добавить пользователя». Заполните имя и email, назначьте предварительно созданную роль из вкладки «Роли» и сохраните форму. Изображение необязательно.'
    retrieval = _retrieval(context=context, operation="add_employee", full=True)
    state = DialogueManager().advance(DialogueState(), "Привет! Как добавить нового сотрудника в aQsi Online?", 1)
    raw = {
        "scenario": "answer",
        "response": "Откройте «Пользователи» → «Добавить пользователя». Введите имя и email, выберите нужную роль из вкладки «Роли» и сохраните форму. Изображение необязательно.",
    }

    async def stub(messages, config):
        return Generation(json.dumps(raw, ensure_ascii=False), "stub-model")

    monkeypatch.setattr("app.answer_service.generate", stub)
    answer = asyncio.run(AnswerService(
        SimpleNamespace(search_for_state=lambda *args: retrieval), settings(tmp_path)
    ).answer(state.task.value, state=state))

    assert answer.validation_status == "passed"
    assert all(term in answer.text for term in ("имя", "email", "роль", "сохран"))


def test_clarification_is_not_followed_by_a_template_warning(monkeypatch, tmp_path):
    manager, state = DialogueManager(), DialogueState()
    state = manager.advance(state, "Привет! Как добавить нового сотрудника в aQsi Online?", 1)
    state = manager.advance(state, "А какую роль ему назначить?", 2)
    retrieval = _retrieval(context=ROLE_CONTEXT, operation="assign_role", full=False,
                           missing=("access_workflow_unverified",))
    raw = {
        "scenario": "clarify",
        "reason": "нужны задачи сотрудника",
        "clarification_slot": "task",
        "response": "Уточните, какие задачи будет выполнять сотрудник: только просмотр или также изменение данных?",
    }

    async def stub(messages, config):
        return Generation(json.dumps(raw, ensure_ascii=False), "stub-model")

    monkeypatch.setattr("app.answer_service.generate", stub)
    answer = asyncio.run(AnswerService(
        SimpleNamespace(search_for_state=lambda *args: retrieval), settings(tmp_path)
    ).answer(state.task.value, state=state))

    assert answer.scenario == "clarify"
    assert answer.text == raw["response"]
    assert "Полная последовательность" not in answer.text


def test_partial_role_answer_keeps_documented_workflow_and_limits_claims(monkeypatch, tmp_path):
    manager, state = DialogueManager(), DialogueState()
    state = manager.advance(state, "Привет! Как добавить нового сотрудника в aQsi Online?", 1)
    state = manager.advance(state, "А какую роль ему назначить?", 2)
    state = manager.advance(state, "Мне нужно, чтобы он мог смотреть кассы и отчёты, но не менять настройки. Как это сделать?", 3)
    retrieval = _retrieval(
        context=ROLE_CONTEXT, operation="assign_role", full=False,
        missing=("access_workflow_unverified", "requested_role_or_permissions_unverified"),
    )
    raw = {
        "scenario": "answer",
        "response": (
            "1. Откройте раздел «Роли» в aQsi Online. 2. Нажмите «Создать роль», "
            "введите название (например, «Смотритель касс»). 3. В блоке «Разрешения» "
            "включите только режим просмотра для разделов «Кассы» и «Отчёты» "
            "(отключите режим редактирования). 4. Сохраните роль. 5. Перейдите в "
            "«Пользователи» → «Добавить пользователя», заполните данные сотрудника, "
            "выберите только что созданную роль и сохраните. После этого сотрудник "
            "сможет просматривать кассы и отчёты, но не сможет менять настройки."
        ),
    }

    async def stub(messages, config):
        return Generation(json.dumps(raw, ensure_ascii=False), "stub-model")

    monkeypatch.setattr("app.answer_service.generate", stub)
    answer = asyncio.run(AnswerService(
        SimpleNamespace(search_for_state=lambda *args: retrieval), settings(tmp_path)
    ).answer(state.task.value, state=state))

    assert answer.validation_status == "modified"
    assert "задайте название роли" in answer.text
    assert "режим просмотра либо редактирования" in answer.text
    assert "назначьте предварительно созданную роль" in answer.text
    assert "Смотритель касс" not in answer.text
    assert "Конкретная роль и её полномочия" in answer.text
    assert "сможет просматривать кассы" not in answer.text


def test_invented_named_role_and_permissions_never_survive_repair(monkeypatch, tmp_path):
    manager, state = DialogueManager(), DialogueState()
    state = manager.advance(state, "Как назначить роль сотруднику в aQsi Online?", 1)
    retrieval = _retrieval(context=ROLE_CONTEXT, operation="assign_role", full=False,
                           missing=("requested_role_or_permissions_unverified",))
    raw = {
        "scenario": "answer",
        "response": "Назначьте роль «Наблюдатель»: она позволяет смотреть кассы и отчёты, но не менять настройки.",
    }

    async def stub(messages, config):
        return Generation(json.dumps(raw, ensure_ascii=False), "stub-model")

    monkeypatch.setattr("app.answer_service.generate", stub)
    answer = asyncio.run(AnswerService(
        SimpleNamespace(search_for_state=lambda *args: retrieval), settings(tmp_path)
    ).answer(state.task.value, state=state))

    assert "Наблюдатель" not in answer.text
    assert "позволяет смотреть кассы" not in answer.text
    assert "Конкретная роль и её полномочия" in answer.text
