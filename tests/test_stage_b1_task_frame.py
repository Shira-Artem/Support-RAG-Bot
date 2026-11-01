"""B1: frozen pilot replay plus independent state and routing controls."""
import json
from pathlib import Path

import pytest

from app.dialogue_state import DialogueManager, DialogueState, Fact, Observation
from app.dialogue_understanding import validate_response
from app.rag_query import build_rag_query
from app.retrieval_pipeline import _state_task_category
from app.task_operation_resolver import resolve_task_operation


TRACE = Path(__file__).resolve().parents[1] / "reports/architecture_audit_20261101/production_trace_redacted.json"


def _replay(ids):
    cases = {item["question_message_id"]: item for item in json.loads(TRACE.read_text(encoding="utf-8"))}
    state = DialogueState()
    states = {}
    for message_id in ids:
        case = cases[message_id]
        kind, _, _, observation = validate_response(case["raw_understanding"], case["question"], message_id)
        state = DialogueManager().advance(state, case["question"], message_id, observation=observation)
        states[message_id] = (state, kind, build_rag_query(state))
    return states


def _obs(text, mid, *, intent="unknown", operation="unknown", subject=None,
         relation="new_task", request_type="diagnosis", entities=None, symptom=False):
    fact = Fact.span(text, mid)
    return Observation(intent=intent, operation=operation, object=subject,
                       relation=relation, request_type=request_type, evidence=fact,
                       symptom=fact if symptom else None,
                       entities={slot: [Fact.span(text, mid, value=value)]
                                 for slot, value in (entities or {}).items()})


def test_frozen_evotor_first_turn_continuation_and_successful_branch():
    first = _replay([557, 559])
    success = _replay([561])
    for mid, (state, kind, query) in {**first, **success}.items():
        frame = state.task_frame
        assert frame.request_type == kind
        assert (frame.intent, frame.operation) == ("receipt", "diagnose")
        assert _state_task_category(state, query) == "receipt_transmission"
        assert state.task_entity("equipment") == "Эвотор 7.3"
        assert "Эвотор 7.3" in query
        assert frame.task_id == state.task_id
    assert first[559][0].task_id == first[557][0].task_id


def test_frozen_clarification_promotes_without_expected_slot():
    replay = _replay([563, 565])
    vague, _, _ = replay[563]
    state, _, query = replay[565]
    assert (vague.intent, vague.operation, vague.expected) == ("general", "unknown", None)
    assert state.task_id == vague.task_id
    assert state.task_frame.relation == "answer_to_clarification"
    assert (state.task_frame.intent, state.task_frame.operation) == ("receipt", "diagnose")
    assert state.task.value.startswith("Эвотор 7.3")
    assert state.task_entity("equipment") == "Эвотор 7.3"
    assert "документы в ОФД" in query and "диагностика" in query
    assert _state_task_category(state, query) == "receipt_transmission"


def test_frozen_concept_subject_is_ofd_not_receipt_or_fiscal_drive():
    state, _, query = _replay([569])[569]
    assert state.task_frame.subject == "ОФД"
    assert state.intent == "general" and state.operation == "explain"
    assert _state_task_category(state, query) == "ofd_connection"


@pytest.mark.parametrize("name", [
    "оператор фискальных данных", "оператора фискальных данных",
    "оператору фискальных данных", "оператором фискальных данных", "ОФД",
])
def test_ofd_registered_noun_inflections(name):
    base = _replay([569])  # confirms the registered OFD contract on a saved input
    assert base[569][0].object == "ОФД"
    from app.dialogue_understanding import _unique_object_from_current_text
    assert _unique_object_from_current_text(name)[0] == "ОФД"


@pytest.mark.parametrize("name,expected", [
    ("ФН", "ФН"), ("ФД", None), ("чек", "чек"), ("касса", "касса"),
])
def test_distinct_fiscal_subjects(name, expected):
    from app.dialogue_understanding import _unique_object_from_current_text
    result = _unique_object_from_current_text(name)
    assert (result[0] if result else None) == expected


@pytest.mark.parametrize("text,operation,expected", [
    ("На кассе итоги продаж есть, в ОФД поступлений нет", "diagnose", "receipt_transmission"),
    ("ККТ регистрирует продажи, оператору фискальных данных они не доходят", "check", "receipt_transmission"),
    ("Где на кассе повторно распечатать чек?", "repeat_print", None),
    ("Вернуть покупателю оплату через кассу", "return", "refund"),
])
def test_independent_domain_paraphrases_and_operations(text, operation, expected):
    subject = "ОФД" if "ОФД" in text or "оператору" in text else "чек"
    assert resolve_task_operation(text, operation=operation, subject=subject).task_category == expected


def test_promotion_keeps_confirmed_facts_and_subsequent_checks():
    manager = DialogueManager()
    vague = "Нужна помощь с АТОЛ Онлайн, модель АТОЛ 30Ф"
    state = manager.advance(DialogueState(), vague, 1, observation=_obs(vague, 1,
        intent="general", entities={"service": "АТОЛ Онлайн", "equipment": "АТОЛ 30Ф",
                                    "manufacturer": "АТОЛ"}))
    for mid, text in [(2, "Фискальные документы не передаются, сеть уже проверил"),
                      (3, "Проверил соединение, оно работает"),
                      (4, "Проверил очередь, она не уменьшается")]:
        state = manager.advance(state, text, mid, observation=_obs(text, mid,
            intent="receipt" if mid == 2 else "unknown",
            operation="diagnose" if mid == 2 else "unknown",
            relation="answer_to_clarification" if mid == 2 else "continue",
            symptom=mid == 2))
    frame = state.task_frame
    assert (frame.intent, frame.operation, frame.relation) == ("receipt", "diagnose", "continue")
    assert state.task_entity("service") == "АТОЛ Онлайн"
    assert state.task_entity("equipment") == "АТОЛ 30Ф"
    assert state.task_id == "task:1"
    assert "АТОЛ 30Ф" in build_rag_query(state)


def test_new_task_and_explicit_reset_do_not_inherit_scope():
    manager = DialogueManager()
    first = "Эвотор 6 не печатает чек"
    state = manager.advance(DialogueState(), first, 1, observation=_obs(first, 1,
        intent="receipt", operation="diagnose", symptom=True,
        entities={"manufacturer": "Эвотор", "equipment": "Эвотор 6"}))
    other = "Новый вопрос: у Saby не приходит УПД"
    next_state = manager.advance(state, other, 2, observation=_obs(other, 2,
        intent="delivery_document", operation="diagnose", relation="new_task",
        entities={"service": "Saby"}, symptom=True))
    assert next_state.task_id == "task:2"
    assert next_state.task_entity("equipment") is None
    assert next_state.task_entity("service") == "Saby"
    assert "Эвотор" not in build_rag_query(next_state)
    fresh = manager.advance(DialogueState(), other, 3, observation=_obs(other, 3,
        intent="delivery_document", operation="diagnose", entities={"service": "Saby"}))
    assert fresh.task_id == "task:3" and fresh.task_entity("equipment") is None


def test_old_snapshot_loads_with_unknown_request_type():
    state = _replay([561])[561][0]
    snapshot = state.to_dict()
    snapshot["task_context"].pop("request_type")
    snapshot.pop("request_type")
    restored = DialogueState.from_dict(snapshot)
    assert restored.task_frame.request_type == "unknown"
    assert restored.task_frame.intent == "receipt"
    assert build_rag_query(restored) == build_rag_query(state)


def test_service_switch_drops_old_task_scope_but_keeps_session_history():
    manager = DialogueManager()
    first = "АТОЛ Онлайн, касса АТОЛ 30Ф не передаёт чеки"
    state = manager.advance(DialogueState(), first, 1, observation=_obs(first, 1,
        intent="receipt", operation="diagnose", symptom=True,
        entities={"service": "АТОЛ Онлайн", "manufacturer": "АТОЛ", "equipment": "АТОЛ 30Ф"}))
    second = "Теперь в Saby другая задача с УПД"
    switched = manager.advance(state, second, 2, observation=_obs(second, 2,
        intent="delivery_document", operation="check", relation="new_task",
        entities={"service": "Saby"}))
    assert switched.task_entity("equipment") is None
    assert switched.entity("equipment") == "АТОЛ 30Ф"
    assert switched.task_frame.entities["service"][0].value == "Saby"
    assert "АТОЛ" not in build_rag_query(switched)


def test_unknown_claim_does_not_erase_confirmed_model_or_invent_replacement():
    manager = DialogueManager()
    first = "На Эвотор 6 не печатается чек"
    state = manager.advance(DialogueState(), first, 1, observation=_obs(first, 1,
        intent="receipt", operation="diagnose", symptom=True,
        entities={"manufacturer": "Эвотор", "equipment": "Эвотор 6"}))
    reply = "Не знаю номер версии"
    obs = _obs(reply, 2, relation="answer_to_clarification")
    obs.unknown_facts = {"details": Fact.span(reply, 2)}
    updated = manager.advance(state, reply, 2, observation=obs, unknown_facts=["details"])
    assert updated.task_frame.entities["equipment"][0].value == "Эвотор 6"
    assert updated.task_frame.unknown_facts == ("details",)
    assert updated.task_frame.intent == "receipt" and updated.task_frame.operation == "diagnose"
    assert "Эвотор 6" in build_rag_query(updated)
