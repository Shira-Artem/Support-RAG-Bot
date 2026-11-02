"""Independent B1.1 task-boundary transitions and durable semantic replay."""
from dataclasses import asdict

from app.answer_service import Answer
from app.conversation_store import ConversationStore
from app.dialogue_state import DialogueManager, DialogueState, ExpectedClarification, Fact, Observation
from app.dialogue_understanding import Understanding, _entity_value_supported, understanding_to_dict, validate_response


def observed(text, mid, *, relation, intent="unknown", operation="unknown", symptom=None,
             entity=None, parameter=None, constraint=None, request_type="diagnosis"):
    def span(quote, value=None):
        start = text.index(quote)
        return Fact.span(text, mid, start, start + len(quote), value=value)

    return Observation(evidence=Fact.span(text, mid), relation=relation, intent=intent,
        operation=operation, request_type=request_type,
        symptom=span(symptom) if symptom else None,
        entities={entity[0]: [span(entity[1], entity[2])] } if entity else {},
        parameters=[span(parameter)] if parameter else [],
        constraints=[span(constraint)] if constraint else [])


def test_vague_task_promotes_despite_false_new_task_label_and_missing_expected_slot():
    manager = DialogueManager()
    opening = "Нужна помощь с кассой, пока не могу описать сбой."
    first = manager.advance(DialogueState(), opening, 1, observation=observed(
        opening, 1, relation="new_task", intent="device", operation="diagnose"))
    assert first.expected is None
    detail = "Это Эвотор, чеки не доходят до ОФД."
    second = manager.advance(first, detail, 2, observation=observed(
        detail, 2, relation="new_task", intent="receipt", operation="diagnose",
        symptom="чеки не доходят до ОФД", entity=("manufacturer", "Эвотор", "Эвотор")))
    assert second.task_id == first.task_id
    assert (second.intent, second.operation) == ("receipt", "diagnose")
    assert second.symptom.quote == "чеки не доходят до ОФД"
    assert second.relation == "continue"


def test_false_new_task_with_expected_slot_is_clarification():
    manager = DialogueManager()
    opening = "Нужна помощь с кассой"
    first = manager.advance(DialogueState(), opening, 1, observation=observed(
        opening, 1, relation="new_task", intent="device", operation="diagnose"))
    first.expected = ExpectedClarification("details", "Что случилось?")
    text = "Чеки не передаются в ОФД"
    second = manager.advance(first, text, 2, observation=observed(
        text, 2, relation="new_task", intent="receipt", operation="diagnose",
        symptom="Чеки не передаются в ОФД"))
    assert second.task_id == first.task_id
    assert second.relation == "answer_to_clarification"
    assert second.expected is None


def test_false_new_task_does_not_drop_contextual_model_but_explicit_reset_does():
    previous = DialogueManager().advance(DialogueState(), "Это Эвотор, чеки не уходят", 1,
        observation=observed("Это Эвотор, чеки не уходят", 1, relation="new_task",
            intent="receipt", operation="diagnose", symptom="чеки не уходят",
            entity=("manufacturer", "Эвотор", "Эвотор")))
    def raw():
        return {"request_type": "information", "relation": "new_task", "intent": "receipt",
            "operation": "diagnose", "object": None, "object_evidence": None,
            "goal": None, "symptom": None,
            "entities": [{"slot": "equipment", "value": "7.3",
                          "evidence": {"quote": "7.3"}}],
            "unknown_facts": [], "specialist_requested": False,
            "specialist_evidence": None, "confidence": 0.9}
    text = "Модель 7.3"
    _, _, _, obs = validate_response(raw(), text, 2, previous)
    assert obs.entities["equipment"][0].value == "Эвотор 7.3"
    continued = DialogueManager().advance(previous, text, 2, observation=obs)
    assert continued.task_id == previous.task_id
    assert continued.task_entity("equipment") == "Эвотор 7.3"
    reset = "Новый вопрос: модель 7.3"
    _, _, _, reset_obs = validate_response(raw(), reset, 3, previous)
    assert "equipment" not in reset_obs.entities
    assert not _entity_value_supported("equipment", "кассой", "кассой")


def test_new_operation_and_explicit_new_question_do_not_merge_with_vague_task():
    manager = DialogueManager()
    opening = "Помогите с кассой"
    first = manager.advance(DialogueState(), opening, 1, observation=observed(
        opening, 1, relation="new_task", intent="device", operation="diagnose"))
    operation = "Как повторно распечатать чек?"
    changed_operation = manager.advance(first, operation, 2, observation=observed(
        operation, 2, relation="new_task", intent="receipt", operation="repeat_print"))
    assert changed_operation.task_id != first.task_id
    topic = "Новый вопрос: что такое ОФД?"
    changed_topic = manager.advance(first, topic, 3, observation=observed(
        topic, 3, relation="new_task", intent="general", operation="explain",
        request_type="information"))
    assert changed_topic.task_id != first.task_id


def test_resolution_then_new_task_and_old_topic_reference_are_independent():
    manager = DialogueManager()
    first_text = "Эвотор не отправляет чеки"
    first = manager.advance(DialogueState(), first_text, 1, observation=observed(
        first_text, 1, relation="new_task", intent="receipt", operation="diagnose",
        symptom="не отправляет чеки", entity=("manufacturer", "Эвотор", "Эвотор")))
    closed = manager.advance(first, "Спасибо, вопрос решён", 2)
    assert closed.task_id == first.task_id and closed.task_frame.closed
    next_text = "Вернёмся к Эвотор: как распечатать копию чека?"
    next_task = manager.advance(closed, next_text, 3, observation=observed(
        next_text, 3, relation="continue", intent="receipt", operation="repeat_print",
        entity=("manufacturer", "Эвотор", "Эвотор")))
    assert next_task.task_id != first.task_id
    assert next_task.symptom is None
    assert next_task.task_entity("manufacturer") == "Эвотор"


def test_new_dialogue_button_has_new_conversation_and_no_old_scope(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    import asyncio
    import bot

    store_path = tmp_path / "new-dialogue.sqlite3"
    store = ConversationStore(store_path)
    old_id = store.new(42, 42)
    text = "Эвотор не передаёт чеки"
    obs = observed(text, "current", relation="new_task", intent="receipt", operation="diagnose",
                   symptom="не передаёт чеки", entity=("manufacturer", "Эвотор", "Эвотор"))
    pending = store.begin(old_id, text, semantic_mode=True,
                          understanding=understanding_to_dict(Understanding("diagnosis", False, (), obs, {}, "test", 0)))
    store.complete(pending, Answer("test"))
    message = SimpleNamespace(text="Новый диалог", reply_text=AsyncMock())
    update = SimpleNamespace(message=message, effective_message=message,
                             effective_user=SimpleNamespace(id=42), effective_chat=SimpleNamespace(id=42))
    with patch.object(bot, "conversations", store):
        asyncio.run(bot.handle_message(update, None))
    new_id = store.state(42, 42)["conversation_id"]
    assert new_id != old_id
    assert ConversationStore(store_path).dialogue_state(new_id).task_id is None
    assert ConversationStore(store_path).dialogue_state(old_id).task_entity("manufacturer") == "Эвотор"


def test_task_boundary_matrix_and_sqlite_reopen(tmp_path):
    """Expected task identities are fixed before replay, including negative neighbors."""
    rows = [
        ("На Эвотор 7.3 чеки не доходят до ОФД", "new_task", "receipt", "diagnose", "чеки не доходят до ОФД", ("equipment", "Эвотор 7.3", "Эвотор 7.3"), None, None, "new"),
        ("Модель 7.3 подтверждаю", "new_task", "receipt", "diagnose", None, ("equipment", "7.3", "Эвотор 7.3"), None, None, "same"),
        ("Проверил сеть, чек всё ещё не ушёл", "continue", "receipt", "diagnose", "чек всё ещё не ушёл", None, None, None, "same"),
        ("Параметр адреса уточнил", "parameter_update", "receipt", "diagnose", None, None, "адреса", None, "same"),
        ("Требование: без сброса кассы", "constraint_update", "receipt", "diagnose", None, None, None, "без сброса кассы", "same"),
        ("Я ошибся: модель Эвотор 6", "contradiction", "receipt", "diagnose", None, ("equipment", "Эвотор 6", "Эвотор 6"), None, None, "same"),
        ("Новый вопрос: в Saby не вижу входящий УПД", "new_task", "delivery_document", "diagnose", "не вижу входящий УПД", ("service", "Saby", "Saby"), None, None, "new"),
        ("Теперь другая задача: в 1С через DirectBank не загружается выписка", "new_task", "bank_statement", "diagnose", "не загружается выписка", ("integration", "DirectBank", "DirectBank"), None, None, "new"),
    ]
    store_path = tmp_path / "lifecycle.sqlite3"
    store = ConversationStore(store_path)
    cid = store.new(42, 42)
    prior_task = None
    first_symptom = None
    for number, (text, relation, intent, operation, symptom, entity, parameter, constraint, identity) in enumerate(rows, 1):
        obs = observed(text, "current", relation=relation, intent=intent, operation=operation,
                       symptom=symptom, entity=entity, parameter=parameter, constraint=constraint)
        payload = understanding_to_dict(Understanding("diagnosis", False, (), obs, {}, "test", 0))
        pending = store.begin(cid, text, semantic_mode=True, understanding=payload)
        store.complete(pending, Answer("test"))
        current = store.dialogue_state(cid)
        reopened = ConversationStore(store_path).dialogue_state(cid)
        assert current.to_dict() == reopened.to_dict(), number
        assert asdict(current.task_frame) == asdict(reopened.task_frame), number
        if identity == "same":
            assert current.task_id == prior_task, number
        else:
            assert current.task_id != prior_task, number
        if number == 1:
            first_symptom = current.symptom.quote
        if 2 <= number <= 6:
            assert current.symptom.quote == first_symptom, number
        if number == 7:
            assert current.task_entity("equipment") is None
            assert current.symptom.quote == "не вижу входящий УПД"
        if number == 8:
            assert current.task_entity("integration") == "DirectBank"
            assert current.symptom.quote == "не загружается выписка"
        if number == 4:
            assert current.parameters[-1].quote == text
            assert current.relation == "parameter_update"
        if number == 5:
            assert current.constraints[-1].quote == text
            assert current.relation == "constraint_update"
        prior_task = current.task_id
