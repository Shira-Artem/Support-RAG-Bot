"""Independent B1 controls for grounded promotion and procedure outcomes."""
from copy import deepcopy

import pytest

from app.dialogue_state import DialogueManager, DialogueState, Fact, Observation, TaskContext
from app.dialogue_understanding import (Understanding, UnderstandingError,
    observation_from_dict, understanding_to_dict, validate_response)


def observation(text, mid, *, intent="unknown", operation="unknown", relation="continue",
                symptom=False):
    fact = Fact.span(text, mid)
    return Observation(evidence=fact, intent=intent, operation=operation, relation=relation,
                       symptom=fact if symptom else None)


def test_vague_device_task_promotes_when_first_specific_symptom_arrives():
    manager = DialogueManager()
    opening = "Помогите разобраться с оборудованием"
    first = manager.advance(DialogueState(), opening, 1, observation=observation(
        opening, 1, intent="device", operation="diagnose", relation="new_task"))
    detail = "Документы не поступают оператору"
    second = manager.advance(first, detail, 2, observation=observation(
        detail, 2, intent="receipt", operation="diagnose", symptom=True))
    assert second.task_id == first.task_id
    assert (second.intent, second.operation) == ("receipt", "diagnose")
    assert second.task.value == detail
    assert second.symptom.quote == detail


def test_specific_existing_device_symptom_does_not_get_silently_relabelled():
    manager = DialogueManager()
    opening = "Касса не включается"
    first = manager.advance(DialogueState(), opening, 1, observation=observation(
        opening, 1, intent="device", operation="diagnose", relation="new_task", symptom=True))
    detail = "Чеки не отправляются оператору"
    second = manager.advance(first, detail, 2, observation=observation(
        detail, 2, intent="receipt", operation="diagnose", symptom=True))
    assert second.intent == "device"
    assert second.task.value == opening


def _raw_model(text, relation="continue", slot="manufacturer", value="Эвотор 7.3"):
    return {"request_type": "information", "relation": relation, "intent": "receipt",
            "operation": "diagnose", "object": None, "object_evidence": None,
            "goal": None, "symptom": None, "entities": [{"slot": slot,
                "value": value, "evidence": {"quote": "Модель 7.3"}}],
            "unknown_facts": [], "specialist_requested": False,
            "specialist_evidence": None, "confidence": 0.9}


def test_explicit_bare_model_uses_only_confirmed_active_manufacturer():
    state = DialogueState(task_context=TaskContext(task_id="task:1", intent="receipt",
        operation="diagnose", entities={"manufacturer": [Fact.span("Эвотор", 1)]}))
    text = "Модель 7.3. Интернет работает."
    _, _, _, obs = validate_response(_raw_model(text), text, 2, state)
    assert obs.entities["equipment"][0].value == "Эвотор 7.3"
    assert obs.entities["equipment"][0].quote == "7.3"
    _, _, _, numeric = validate_response(_raw_model(text, slot="equipment", value="7.3"), text, 5, state)
    assert numeric.entities["equipment"][0].value == "Эвотор 7.3"
    persisted = understanding_to_dict(Understanding("information", False, (), numeric, {}, "test", 1))
    reopened, _ = observation_from_dict(persisted, text, 5, state)
    assert reopened.entities["equipment"][0].value == "Эвотор 7.3"
    with pytest.raises(UnderstandingError):
        observation_from_dict(persisted, text, 5, DialogueState())
    _, _, _, fresh = validate_response(_raw_model(text, "new_task"), text, 3, state)
    assert "equipment" not in fresh.entities
    _, _, _, unknown = validate_response(_raw_model(text), text, 4, DialogueState())
    assert "equipment" not in unknown.entities
    _, _, _, unscoped = validate_response(_raw_model(text, slot="equipment", value="7.3"),
                                           text, 6, DialogueState())
    assert "equipment" not in unscoped.entities


def test_compound_check_keeps_partial_outcome_and_does_not_erase_failure():
    manager = DialogueManager()
    state = DialogueState(task_context=TaskContext(task_id="task:1", intent="receipt",
        operation="diagnose"))
    units = [
        {"unit_id": "model", "label": "Выясните модель и проверьте действительность оплаченного периода в кабинете оператора.",
         "source_verified": True},
        {"unit_id": "network", "label": "Проверьте поля EoU, наличие выхода в интернет, адрес и порт ОФД.",
         "source_verified": True},
        {"unit_id": "queue", "label": "Посмотрите очередь документов, ожидающих отправки.",
         "source_verified": True},
    ]
    state = manager.observe_answer(state, scenario="answer", reason="source_first_safe_preflight",
        question="Проверьте", progress_update={"shown_units": units, "eligible_units": units})
    for mid, text in [(2, "Интернет работает, проверил подключение."),
                      (3, "Адрес и порт ОФД совпадают с параметрами оператора."),
                      (4, "Очередь документов не уменьшается."),
                      (5, "Очередь проверил.")]:
        state = manager.advance(state, text, mid, observation=observation(text, mid))
    checks = {item["unit_id"]: item for item in state.task_frame.checks}
    assert checks["model"]["status"] == "asked"
    assert checks["network"]["status"] == "unknown"
    assert [item["status"] for item in checks["network"]["observations"]] == ["passed", "passed"]
    assert checks["queue"]["status"] == "failed"
    assert checks["queue"]["observations"][-1]["status"] == "unknown"
    restored = DialogueState.from_dict(state.to_dict())
    assert restored.task_frame.checks == state.task_frame.checks


def test_explicit_matching_and_unstable_results_replace_current_status_with_history():
    manager = DialogueManager()
    state = DialogueState(task_context=TaskContext(task_id="task:1", intent="network",
        operation="diagnose"))
    unit = {"unit_id": "connection", "label": "Проверьте подключение и связь с оператором.",
            "source_verified": True}
    state = manager.observe_answer(state, scenario="answer", reason="approved",
        question="Проверьте", progress_update={"shown_units": [unit]})
    for mid, text in [(2, "Связь с оператором стабильна."),
                      (3, "Теперь связь нестабильна и пропадает."),
                      (4, "Настройки связи проверил.")]:
        state = manager.advance(state, text, mid, observation=observation(text, mid))
    check = state.task_frame.checks[0]
    assert check["status"] == "failed"
    assert [item["status"] for item in check["observations"]] == ["passed", "failed", "unknown"]
    assert check["contradictions"][-1]["after"]["quote"].startswith("Теперь связь")


def test_one_result_does_not_complete_atomic_and_broad_procedure_units():
    manager = DialogueManager()
    state = DialogueState(task_context=TaskContext(task_id="task:1", intent="receipt",
        operation="diagnose"))
    units = [
        {"unit_id": "atomic_queue", "label": "Посмотрите очередь документов, ожидающих отправки.",
         "source_verified": True},
        {"unit_id": "whole_procedure", "label":
         "Проверьте связь и адрес передачи, затем посмотрите очередь документов, ожидающих отправки.",
         "source_verified": True},
    ]
    state = manager.observe_answer(state, scenario="answer", reason="approved",
        question="Проверьте", progress_update={"shown_units": units, "eligible_units": units})
    message = "Очередь документов не уменьшается."
    state = manager.advance(state, message, 2, observation=observation(message, 2))
    checks = {item["unit_id"]: item for item in state.task_frame.checks}
    assert checks["atomic_queue"]["status"] == "failed"
    assert checks["whole_procedure"]["status"] == "unknown"
    assert checks["whole_procedure"]["partial_result_spans"][0]["quote"] == message.rstrip(".")
    assert "observations" not in checks["whole_procedure"]


def test_residual_detail_requires_content_and_keeps_new_symptom():
    manager = DialogueManager()
    state = DialogueState(task_context=TaskContext(task_id="task:1", intent="receipt",
        operation="diagnose", task_fact=Fact.span("Чеки не уходят", 1)))
    filler = "У меня. Что дальше?"
    obs = observation(filler, 2)
    obs.goals = [Fact.span(filler, 2, filler.index("Что"))]
    after_filler = manager.advance(state, filler, 2, observation=obs)
    assert after_filler.task_frame.details == ()
    detail = "Очередь растёт. Что дальше?"
    obs = observation(detail, 3)
    obs.goals = [Fact.span(detail, 3, detail.index("Что"))]
    after_detail = manager.advance(after_filler, detail, 3, observation=obs)
    assert any(fact.value == "Очередь растёт" for fact in after_detail.task_frame.details)


@pytest.mark.parametrize("reason", ["understanding_failed", "groq_quota_deferred",
                                   "unexpected_exception", "client_requested_specialist"])
def test_failed_assistant_turn_does_not_open_task_or_erase_confirmed_state(reason):
    manager = DialogueManager()
    state = DialogueState(task_context=TaskContext(task_id="task:1", intent="receipt",
        operation="diagnose", symptom=Fact.span("Чеки не уходят", 1)))
    before = deepcopy(state.to_dict())
    after = manager.observe_answer(state, scenario="clarify", reason=reason,
                                   question="Повторите позднее", slot="details")
    assert after.to_dict() == before
