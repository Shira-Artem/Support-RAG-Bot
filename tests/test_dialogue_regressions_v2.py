"""Offline target-behavior regressions for a future DialogueState v2.

All conversation wording is synthetic and reconstructed from the task brief.
These tests make no network, Telegram, provider, or SQLite-default-database calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.answer_service import Answer
from app.conversation_store import ConversationStore
from app.dialogue_state import DialogueManager, DialogueState, Fact
from app.rag_query import QueryNeedsClarification, build_rag_query


FIXTURE = Path(__file__).parent / "fixtures" / "dialogue_regressions_v2.json"
SCENARIOS = json.loads(FIXTURE.read_text(encoding="utf-8"))["scenarios"]


def scenario(key):
    return SCENARIOS[key]


def advance(messages, clarification=None):
    manager, state = DialogueManager(), DialogueState()
    for i, message in enumerate(messages[:1], 1):
        state = manager.advance(state, message, i)
    if clarification:
        state = manager.observe_answer(
            state,
            scenario="clarify",
            reason=None,
            question=clarification["question"],
            message_id="assistant:1",
            slot=clarification["slot"],
        )
    rest = messages[1:]
    for offset, message in enumerate(rest, 2):
        state = manager.advance(state, message, offset)
    return state


def query_or_none(state):
    try:
        return build_rag_query(state)
    except QueryNeedsClarification:
        return None


@pytest.mark.xfail(strict=True, reason="v1 lexical analysis binds the FN argument as a new fiscal_drive task")
def test_a_receipt_search_survives_fn_parameter():
    case = scenario("A")
    state = advance(case["messages"])
    query = query_or_none(state)
    assert state.intent == "receipt"
    assert state.operation == "search"
    assert state.routing_service == "Платформа ОФД"
    assert state.task_id == "task:1"
    assert state.parameters and "ФН" in state.parameters[-1].value
    assert query and "чек" in query and "Платформа ОФД" in query


@pytest.mark.xfail(strict=True, reason="v1 leaves the relation unresolved and suppresses retrieval for these credential follow-ups")
def test_b_password_recovery_followups_continue_with_retrieval():
    case = scenario("B")
    state = advance(case["messages"], case["expected_before_followup"])
    assert state.intent == "credentials" and state.operation == "reset_password"
    assert state.task_id == "task:1"
    assert state.expected is None
    assert not state.analysis_required
    assert query_or_none(state)


@pytest.mark.xfail(strict=True, reason="v1 classifies the contradiction as unresolved instead of a task relation")
def test_c_missing_report_section_is_a_contradiction_on_same_task():
    case = scenario("C")
    state = advance(case["messages"], case["expected_before_followup"])
    assert state.intent == "report" and state.task_id == "task:1"
    assert state.transition in {"contradiction", "continue_task"}
    assert not state.analysis_required
    assert query_or_none(state)


@pytest.mark.xfail(strict=True, reason="v1 retains stale task/clarification when the new OFD-document question is not classified")
def test_d_new_ofd_question_cancels_tspiot_equipment_clarification():
    case = scenario("D")
    state = advance(case["messages"], case["expected_before_followup"])
    query = query_or_none(state)
    assert state.task_id == "task:2"
    assert state.expected is None
    assert state.routing_service == "Платформа ОФД"
    assert state.intent == "receipt"
    assert query and "ТС ПиОТ" not in query


@pytest.mark.xfail(strict=True, reason="v1 has no bank-statement intent/object vocabulary and cannot bind the elliptical follow-up")
def test_e_1c_directbank_keeps_bank_statement_task():
    case = scenario("E")
    state = advance(case["messages"])
    assert state.intent == "bank_statement"
    assert state.task_id == "task:1"
    assert not state.analysis_required
    assert query_or_none(state)


@pytest.mark.xfail(strict=True, reason="v1 has no repeat_print operation; analyzer leaves the operation unknown")
def test_f_evotor_old_receipt_records_repeat_print_operation():
    case = scenario("F")
    state = advance(case["messages"])
    query = query_or_none(state)
    assert state.intent == "receipt"
    assert state.operation == "repeat_print"
    assert query and "повтор" in query and "ФД" in query


def test_g_service_switch_preserves_requirements_without_mixing_products():
    case = scenario("G")
    state = advance(case["messages"])
    query = query_or_none(state)
    assert state.task_id == "task:1"
    assert state.routing_service == "АТОЛ Онлайн"
    assert state.goals and state.constraints
    assert query and "АТОЛ Онлайн" in query and "aQsi Online" not in query


def test_h_new_task_clears_task_facts_but_keeps_session_entities():
    manager = DialogueManager()
    state = manager.advance(DialogueState(), "aQsi Online, добавить сотрудника", 1)
    state.goals.append(Fact.span("мне нужно", 1))
    state.parameters.append(Fact.span("по ФД 123", 1))
    new = manager.advance(state, "Новый вопрос: что такое НДС?", 2)
    assert new.task_id != state.task_id
    assert new.entity("service") == "aQsi Online"
    assert not new.goals and not new.constraints and not new.parameters


@pytest.mark.xfail(strict=True, reason="v1 reuses the previous session service as the new task route without a user fact")
def test_h_session_service_is_not_implicitly_bound_to_new_task():
    manager = DialogueManager()
    state = manager.advance(DialogueState(), "aQsi Online, добавить сотрудника", 1)
    new = manager.advance(state, "Новый вопрос: как восстановить пароль?", 2)
    assert new.entity("service") == "aQsi Online"  # session fact remains available
    assert new.routing_service is None
    assert "service" not in new.task_entities


def test_h_assistant_clarification_does_not_become_a_client_fact():
    manager = DialogueManager()
    state = manager.advance(DialogueState(), "aQsi Online, восстановить пароль", 1)
    before = state.to_dict()
    after = manager.observe_answer(state, scenario="clarify", reason=None,
                                   question="Подтвердите пароль", message_id=2, slot="details")
    assert after.to_dict() == {**before, "expected": {
        "slot": "details", "question": "Подтвердите пароль", "message_id": 2, "reason": None}}


def test_h_new_conversation_reload_and_pending_recovery_are_isolated(tmp_path):
    path = tmp_path / "offline.sqlite3"
    store = ConversationStore(path)
    first = store.new(7, 70)
    pending = store.begin(first, "Платформа ОФД, найти чек")
    store.complete(pending, Answer("Ответ", scenario="answer"))
    expected = store.dialogue_state(first).to_dict()
    assert ConversationStore(path).dialogue_state(first).to_dict() == expected

    second = store.new(7, 71)
    assert ConversationStore(path).dialogue_state(second).task_id is None
    interrupted = store.begin(second, "aQsi Online, восстановить пароль")
    store.recover_pending()
    recovered = store.dialogue_state(second)
    assert recovered.task_id is not None and recovered.expected is None
    with store.connect() as db:
        row = db.execute("SELECT status FROM messages WHERE id=?", (interrupted,)).fetchone()
    assert row["status"] == "complete"


def test_h_fact_citations_are_exact_and_ambiguous_entities_are_not_invented():
    manager = DialogueManager()
    source = "АТОЛ Онлайн, найти чек"
    state = manager.advance(DialogueState(), source, 41)
    fact = state.entities["service"][0]
    assert source[fact.start:fact.end] == fact.quote
    assert fact.message_id == 41

    ambiguous = manager.advance(DialogueState(), "Как изменить права: aQsi Online или АТОЛ Онлайн?", 42)
    assert ambiguous.entity("service") is None
    assert ambiguous.analysis_required
