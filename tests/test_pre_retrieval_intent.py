from __future__ import annotations

import asyncio
import json

import pytest

from app.answer_service import AnswerService
from app.dialogue_state import DialogueManager, DialogueState
from app.llm_client import Generation
from app.rag import SearchResult
from test_expert import settings


class RetrievalMustNotRun:
    def search(self, *args, **kwargs):
        raise AssertionError("retrieval must not run for a non-task turn")

    def build_context(self, *args, **kwargs):
        raise AssertionError("context must not be built for a non-task turn")


@pytest.mark.parametrize(
    ("message", "reason", "scenario"),
    [
        ("Привет!", "pre_retrieval_greeting", "answer"),
        ("Привет! Помоги мне", "task_not_specified", "clarify"),
        ("У меня проблема", "task_not_specified", "clarify"),
        ("Спасибо", "pre_retrieval_thanks", "answer"),
        ("Что ты умеешь?", "pre_retrieval_capabilities", "answer"),
    ],
)
def test_non_task_turns_bypass_retrieval_and_do_not_create_a_task(tmp_path, message, reason, scenario):
    state = DialogueManager().advance(DialogueState(), message, 1)
    answer = asyncio.run(AnswerService(RetrievalMustNotRun(), settings(tmp_path)).answer(message, state=state))

    assert state.task_id is None and state.task is None
    assert answer.scenario == scenario and answer.scenario_reason == reason
    assert answer.rag_query is None and answer.retrieval_diagnostics is None
    assert answer.raw_model_text is None and answer.validation_status == "not_run"
    assert not answer.llm_call_attempted and answer.rag_chunks == 0


def test_concrete_question_with_greeting_uses_normal_task_routing(tmp_path):
    message = "Привет, как найти чек?"
    state = DialogueManager().advance(DialogueState(), message, 1)
    answer = asyncio.run(AnswerService(RetrievalMustNotRun(), settings(tmp_path)).answer(message, state=state))

    assert state.intent == "receipt" and state.operation == "search"
    assert answer.active_request == "поиск чека"
    assert answer.scenario_reason == "service_not_confirmed"
    assert answer.scenario == "clarify"


def test_thanks_preserves_existing_task_and_pending_clarification(tmp_path):
    manager = DialogueManager()
    state = manager.advance(DialogueState(), "Как добавить сотрудника?", 1)
    state = manager.observe_answer(
        state, scenario="clarify", reason="service_not_confirmed",
        question="В каком сервисе?", message_id=2, slot="service",
    )
    before = state.to_dict()
    after = manager.advance(state, "Спасибо", 3)
    answer = asyncio.run(AnswerService(RetrievalMustNotRun(), settings(tmp_path)).answer("Спасибо", state=after))
    completed = manager.observe_answer(
        after, scenario=answer.scenario, reason=answer.scenario_reason,
        question=answer.text, message_id=4, slot=answer.clarification_slot,
    )

    assert completed.task_id == before["task_id"]
    assert completed.task.value == before["task"]["value"]
    assert completed.expected.question == "В каком сервисе?"


def test_clarification_in_existing_dialogue_reaches_retrieval(monkeypatch, tmp_path):
    manager = DialogueManager()
    state = manager.advance(DialogueState(), "Как добавить сотрудника?", 1)
    state = manager.observe_answer(
        state, scenario="clarify", reason="service_not_confirmed",
        question="В каком сервисе?", message_id=2, slot="service",
    )
    state = manager.advance(state, "В aQsi Online", 3)
    searches = []

    class Rag:
        def search_for_service(self, query, service, top_k):
            searches.append((query, service))
            return [SearchResult(
                "aqsi_online/account/add-user.md",
                "В разделе «Пользователи» администратор создаёт учётную запись.",
                .9,
            )]

        def build_context(self, results):
            return results[0].text

    async def fake_generate(*args):
        return Generation(json.dumps({
            "scenario": "answer",
            "response": "В разделе «Пользователи» администратор создаёт учётную запись.",
        }), "model")

    monkeypatch.setattr("app.answer_service.generate", fake_generate)
    answer = asyncio.run(AnswerService(Rag(), settings(tmp_path)).answer("В aQsi Online", state=state))

    assert searches and searches[0][1] == "aQsi Online"
    assert "добавление сотрудника" in searches[0][0]
    assert answer.rag_query == searches[0][0]


def test_greeting_with_concrete_new_topic_switches_without_stale_route(tmp_path):
    manager = DialogueManager()
    state = manager.advance(DialogueState(), "aQsi Online, добавить сотрудника", 1)
    switched = manager.advance(state, "Привет! В Платформе ОФД как найти чек?", 2)

    assert switched.task_id == "task:2" and switched.transition == "new_task"
    assert switched.intent == "receipt" and switched.operation == "search"
    assert switched.routing_service == "Платформа ОФД"
    assert "aQsi Online" not in switched.task.value
