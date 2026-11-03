"""B1.1 independent negative task boundaries and stale-model SQLite controls."""
from app.answer_service import Answer
from app.conversation_store import ConversationStore
from app.dialogue_state import Fact, Observation
from app.dialogue_understanding import Understanding, understanding_to_dict, validate_response


def _fact(text, mid, quote, value=None):
    start = text.index(quote)
    return Fact.span(text, mid, start, start + len(quote), value=value)


def _obs(text, mid, relation, intent, operation, *, symptom=None, entities=None):
    return Observation(evidence=Fact.span(text, mid), relation=relation,
        intent=intent, operation=operation, request_type="diagnosis",
        symptom=_fact(text, mid, symptom) if symptom else None,
        entities={slot: [_fact(text, mid, quote, value)]
                  for slot, quote, value in (entities or [])})


def _persist(store, cid, text, observation):
    data = understanding_to_dict(Understanding("diagnosis", False, (), observation, {}, "test", 0))
    pending = store.begin(cid, text, semantic_mode=True, understanding=data)
    store.complete(pending, Answer("test"))
    current = store.dialogue_state(cid)
    reopened = ConversationStore(store.path).dialogue_state(cid)
    assert reopened.to_dict() == current.to_dict()
    return reopened


def _evotor_state(store, cid):
    text = "Эвотор 7.3 не передаёт чеки в ОФД"
    return _persist(store, cid, text, _obs(text, "current", "new_task", "receipt", "diagnose",
        symptom="не передаёт чеки в ОФД",
        entities=[("manufacturer", "Эвотор", "Эвотор"),
                  ("equipment", "Эвотор 7.3", "Эвотор 7.3")]))


def test_generic_device_claim_is_rejected_before_persisted_revalidation(tmp_path):
    text = "Помогите разобраться с кассой, пока не знаю, что именно сломалось"
    raw = {"request_type": "diagnosis", "relation": "new_task",
           "intent": "general", "operation": "diagnose",
           "object": "кассой", "object_evidence": {"quote": "кассой"},
           "goal": {"quote": "Помогите разобраться"}, "symptom": None,
           "entities": [{"slot": "equipment", "value": "кассой",
                         "evidence": {"quote": "кассой"}}],
           "unknown_facts": [], "specialist_requested": False,
           "specialist_evidence": None, "confidence": 0.9}
    kind, _, _, observation = validate_response(raw, text, "current")
    assert "equipment" not in observation.entities
    store = ConversationStore(tmp_path / "generic-equipment.sqlite3")
    cid = store.new(42, 42)
    data = understanding_to_dict(Understanding(kind, False, (), observation, {}, "test", 0))
    pending = store.begin(cid, text, semantic_mode=True, understanding=data)
    store.complete(pending, Answer("test"))
    state = ConversationStore(store.path).dialogue_state(cid)
    assert state.task_id is not None
    assert state.task_entity("equipment") is None


def test_implicit_service_and_subject_switch_must_create_new_task(tmp_path):
    store = ConversationStore(tmp_path / "service.sqlite3")
    cid = store.new(42, 42)
    first = _evotor_state(store, cid)
    text = "В Saby не вижу входящий УПД"
    after = _persist(store, cid, text, _obs(text, "current", "continue",
        "delivery_document", "diagnose", symptom="не вижу входящий УПД",
        entities=[("service", "Saby", "Saby")]))
    assert after.task_id != first.task_id
    assert after.task_entity("service") == "Saby"
    assert after.task_entity("equipment") is None
    assert after.symptom.quote == "не вижу входящий УПД"


def test_implicit_operation_switch_same_manufacturer_must_create_new_task(tmp_path):
    store = ConversationStore(tmp_path / "operation.sqlite3")
    cid = store.new(42, 42)
    first = _evotor_state(store, cid)
    text = "Как на Эвотор 7.3 распечатать копию чека?"
    after = _persist(store, cid, text, _obs(text, "current", "continue",
        "receipt", "repeat_print", entities=[
            ("manufacturer", "Эвотор", "Эвотор"),
            ("equipment", "Эвотор 7.3", "Эвотор 7.3")]))
    assert after.task_id != first.task_id
    assert after.operation == "repeat_print"
    assert after.symptom is None


def test_declarative_independent_operation_without_question_mark_is_new(tmp_path):
    store = ConversationStore(tmp_path / "declarative-operation.sqlite3")
    cid = store.new(42, 42)
    first = _evotor_state(store, cid)
    text = "Нужно распечатать копию чека на Эвотор 7.3"
    after = _persist(store, cid, text, _obs(text, "current", "continue",
        "receipt", "repeat_print", entities=[
            ("manufacturer", "Эвотор", "Эвотор"),
            ("equipment", "Эвотор 7.3", "Эвотор 7.3")]))
    assert after.task_id != first.task_id
    assert after.symptom is None


def test_diagnostic_check_operation_is_continuation(tmp_path):
    store = ConversationStore(tmp_path / "diagnostic-check.sqlite3")
    cid = store.new(42, 42)
    first = _evotor_state(store, cid)
    text = "Проверю соединение с ОФД"
    after = _persist(store, cid, text, _obs(text, "current", "continue",
        "receipt", "check"))
    assert after.task_id == first.task_id
    assert after.symptom == first.symptom


def test_implicit_subject_switch_without_new_service_must_create_new_task(tmp_path):
    store = ConversationStore(tmp_path / "subject.sqlite3")
    cid = store.new(42, 42)
    first = _evotor_state(store, cid)
    text = "ФН не активируется"
    after = _persist(store, cid, text, _obs(text, "current", "continue",
        "fiscal_drive", "diagnose", symptom="не активируется"))
    assert after.task_id != first.task_id
    assert after.intent == "fiscal_drive"
    assert after.symptom.quote == "не активируется"
    assert after.task_entity("equipment") is None


def test_implicit_service_switch_same_task_family_must_create_new_task(tmp_path):
    store = ConversationStore(tmp_path / "vendor.sqlite3")
    cid = store.new(42, 42)
    first = _evotor_state(store, cid)
    text = "АТОЛ 30Ф не отправляет чеки в ОФД"
    after = _persist(store, cid, text, _obs(text, "current", "continue",
        "receipt", "diagnose", symptom="не отправляет чеки в ОФД",
        entities=[("manufacturer", "АТОЛ", "АТОЛ"),
                  ("equipment", "АТОЛ 30Ф", "АТОЛ 30Ф")]))
    assert after.task_id != first.task_id
    assert after.task_entity("manufacturer") == "АТОЛ"
    assert after.task_entity("equipment") == "АТОЛ 30Ф"


def test_short_model_never_borrows_manufacturer_after_close_or_switch(tmp_path):
    store = ConversationStore(tmp_path / "model.sqlite3")
    cid = store.new(42, 42)
    first = _evotor_state(store, cid)
    close_text = "Спасибо, вопрос решён"
    closed = _persist(store, cid, close_text, _obs(close_text, "current",
        "continue", "unknown", "unknown"))
    assert closed.task_frame.closed
    raw = {"request_type": "information", "relation": "new_task", "intent": "receipt",
           "operation": "diagnose", "object": None, "object_evidence": None,
           "goal": None, "symptom": None,
           "entities": [{"slot": "equipment", "value": "7.3",
                         "evidence": {"quote": "7.3"}}],
           "unknown_facts": [], "specialist_requested": False,
           "specialist_evidence": None, "confidence": 0.9}
    text = "Модель 7.3"
    _, _, _, after_close = validate_response(raw, text, 100, closed)
    assert "equipment" not in after_close.entities
    switched_store = ConversationStore(tmp_path / "switched-model.sqlite3")
    switched_cid = switched_store.new(43, 43)
    switched_first = _evotor_state(switched_store, switched_cid)
    switch = "В Saby не вижу входящий УПД"
    switched = _persist(switched_store, switched_cid, switch, _obs(switch, "current", "new_task",
        "delivery_document", "diagnose", symptom="не вижу входящий УПД",
        entities=[("service", "Saby", "Saby")]))
    assert switched.task_id != switched_first.task_id
    _, _, _, after_switch = validate_response(raw, text, 101, switched)
    assert "equipment" not in after_switch.entities
    different_operation = dict(raw, operation="repeat_print")
    new_question = "Как распечатать копию чека на модели 7.3?"
    _, _, _, unrelated = validate_response(different_operation, new_question, 102, first)
    assert "equipment" not in unrelated.entities
