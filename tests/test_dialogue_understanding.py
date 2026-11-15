from dataclasses import replace
import asyncio
from pathlib import Path

import pytest

from app.config import get_settings
from app.conversation_store import ConversationStore
from app.dialogue_state import DialogueManager, DialogueState, ExpectedClarification, Fact
from app.dialogue_understanding import (Understanding, UnderstandingError, response_schema,
    _state_summary, understand_message, understanding_to_dict, validate_response)
from app.source_first_service import SourceFirstService


def test_understanding_429_is_bounded_and_provider_body_is_not_persisted(monkeypatch, tmp_path):
    import app.dialogue_understanding as module
    import httpx
    from types import SimpleNamespace
    from app.groq_rate_limit import GroqRateLimiter

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        def __init__(self, *_args, **_kwargs): pass
        async def post(self, *_args, **_kwargs):
            return httpx.Response(429, json={"error": {"message": "SENSITIVE_PROVIDER_ECHO"}},
                headers={"retry-after": "3"}, request=httpx.Request("POST", "https://api.groq.com"))

    monkeypatch.setattr(module.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(module, "groq_rate_limiter", GroqRateLimiter(minimum_interval=0, maximum_wait=0))
    monkeypatch.setattr("app.groq_rate_limit._TRACE", tmp_path / "quota.jsonl")
    monkeypatch.setattr(module, "_append_local_trace", lambda **data: captured.append(data))
    captured = []
    settings = SimpleNamespace(llm_provider="groq", groq_api_key="test-key",
        groq_model="openai/gpt-oss-20b", groq_reasoning_effort="medium")
    with pytest.raises(UnderstandingError) as raised:
        asyncio.run(module.understand_message("Что такое ОФД?", "current", [], DialogueState(), settings))
    assert raised.value.http_status == 429
    assert raised.value.retry_after_seconds == 3
    assert "SENSITIVE_PROVIDER_ECHO" not in str(captured)


@pytest.mark.parametrize(('failures', 'expected_calls'), [(1, 2), (2, 2)])
def test_understanding_retries_only_one_invalid_provider_json(monkeypatch, failures, expected_calls):
    import json
    import httpx
    from types import SimpleNamespace
    import app.dialogue_understanding as module
    from app.groq_rate_limit import GroqRateLimiter

    text = 'Что такое ОФД?'
    valid = payload(text, kind='information', intent='general', operation='explain',
                    obj='понятие', object_quote='ОФД', goal=text)
    calls, traces = [], []

    class FakeClient:
        def __init__(self, *_args, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def post(self, *_args, **kwargs):
            calls.append(kwargs['json'])
            if len(calls) <= failures:
                return httpx.Response(400, json={'error': {'code': 'json_validate_failed',
                    'failed_generation': 'SENSITIVE_PROVIDER_ECHO'}},
                    request=httpx.Request('POST', 'https://api.groq.com'))
            return httpx.Response(200, json={'model': 'test', 'usage': {},
                'choices': [{'message': {'content': json.dumps(valid, ensure_ascii=False)}}]},
                request=httpx.Request('POST', 'https://api.groq.com'))

    monkeypatch.setattr(module.httpx, 'AsyncClient', FakeClient)
    monkeypatch.setattr(module, 'groq_rate_limiter', GroqRateLimiter(minimum_interval=0, maximum_wait=0))
    monkeypatch.setattr(module, '_append_local_trace', lambda **record: traces.append(record))
    settings = SimpleNamespace(llm_provider='groq', groq_api_key='test-key',
                               groq_model='test', groq_reasoning_effort='medium')
    if failures == 1:
        result = asyncio.run(module.understand_message(text, 1, [], DialogueState(), settings))
        assert result.request_type == 'information'
    else:
        with pytest.raises(UnderstandingError) as raised:
            asyncio.run(module.understand_message(text, 1, [], DialogueState(), settings))
        assert raised.value.http_status == 400
    assert len(calls) == expected_calls
    assert len(calls[1]['messages']) == len(calls[0]['messages']) + 1
    assert 'SENSITIVE_PROVIDER_ECHO' not in str(traces)


@pytest.mark.parametrize("fault,code", [("timeout", "transport_error"), ("invalid_json", "invalid_json")])
def test_understanding_fault_keeps_only_typed_diagnostics(monkeypatch, tmp_path, fault, code):
    import app.dialogue_understanding as module
    import httpx
    from types import SimpleNamespace
    from app.groq_rate_limit import GroqRateLimiter

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        def __init__(self, *_args, **_kwargs): pass
        async def post(self, *_args, **_kwargs):
            if fault == "timeout":
                raise httpx.ReadTimeout("SENSITIVE_PROVIDER_ECHO")
            return httpx.Response(200, json={"model": "openai/gpt-oss-20b",
                "choices": [{"message": {"content": "SENSITIVE_PROVIDER_ECHO"}}]},
                request=httpx.Request("POST", "https://api.groq.com"))

    captured = []
    monkeypatch.setattr(module.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(module, "groq_rate_limiter", GroqRateLimiter(minimum_interval=0, maximum_wait=0))
    monkeypatch.setattr(module, "_append_local_trace", lambda **data: captured.append(data))
    settings = SimpleNamespace(llm_provider="groq", groq_api_key="test-key",
        groq_model="openai/gpt-oss-20b", groq_reasoning_effort="medium")
    with pytest.raises(UnderstandingError) as raised:
        asyncio.run(module.understand_message("Что такое ОФД?", "current", [], DialogueState(), settings))
    assert raised.value.code == code
    assert "SENSITIVE_PROVIDER_ECHO" not in str(captured)
    assert "SENSITIVE_PROVIDER_ECHO" not in str(raised.value.structured_response)


def payload(text, *, kind="diagnosis", relation="new_task", intent="receipt", operation="diagnose",
            obj="чек", entities=(), unknown=(), specialist=False, specialist_quote=None,
            intent_quote=None, operation_quote=None, object_quote=None, relation_quote=None,
            goal=None, symptom=None, unknown_quote=None, error_codes=()):
    return {"request_type": kind, "relation": relation, "intent": intent, "operation": operation,
        "object": obj, "object_evidence": {"quote": object_quote or text} if obj is not None else None,
        "goal": {"quote": goal} if goal else None,
        "symptom": {"quote": symptom} if symptom else None,
        "error_codes": [{"quote": quote} for quote in error_codes],
        "entities": [{"slot": slot, "value": value, "evidence": {"quote": quote}}
                     for slot, value, quote in entities],
        "unknown_facts": [{"slot": slot, "evidence": {"quote": unknown_quote or text}}
                          for slot in unknown], "specialist_requested": specialist,
        "specialist_evidence": {"quote": specialist_quote} if specialist_quote else None,
        "confidence": .91}


def classify(text, **kwargs):
    return validate_response(payload(text, **kwargs), text, 77)


@pytest.mark.parametrize('noun', ['накопителя', 'чека', 'отчёта', 'терминала'])
def test_generic_task_object_is_not_a_model_when_provider_mistypes_it(noun):
    text = f'Вопрос о работе {noun}.'
    data = payload(text, obj=None, entities=[('equipment', noun, noun)])
    _, _, _, observation = validate_response(data, text, 77)
    assert not observation.entities.get('equipment')


def test_greeting_is_typed_and_does_not_create_task():
    text = "Здравствуйте!"
    kind, specialist, _, obs = classify(text, kind="greeting", intent="unknown", operation="unknown", obj=None,
        intent_quote=None, operation_quote=None, object_quote=None, relation="unknown", relation_quote=None)
    assert kind == "greeting" and not specialist
    record = Understanding(kind, specialist, (), obs, {}, "test", 1)
    store = ConversationStore(Path(__import__("tempfile").mktemp(suffix=".sqlite3")))
    cid = store.new(1, 2)
    store.begin(cid, text, semantic_mode=True, understanding=understanding_to_dict(record))
    assert store.dialogue_state(cid).task_id is None


def test_information_is_explain_and_separates_ofd_from_manufacturer():
    text = "Что такое ОФД?"
    data = payload(text, kind="information", intent="general", operation="explain", obj="понятие",
        intent_quote=text, operation_quote=text, object_quote="ОФД", relation="new_task", relation_quote=text,
        goal=text)
    kind, _, _, obs = validate_response(data, text, 77)
    state = DialogueManager().advance(DialogueState(), text, 77, observation=obs)
    assert kind == "information" and state.intent == "general" and state.operation == "explain"
    assert state.entity("manufacturer") is None and state.entity("ofd") is None


def test_confirmed_error_code_exact_span_flows_through_state_and_sqlite(tmp_path):
    text = "Касса Эвотор пишет ошибку ФН 234, чек не печатается."
    raw = payload(text, kind="diagnosis", intent="fiscal_drive", operation="diagnose",
                  obj="ФН", object_quote="ФН", relation="new_task",
                  error_codes=["ошибку ФН 234"])
    _, _, _, observation = validate_response(raw, text, "m-1")
    assert [(fact.value, fact.quote, fact.message_id) for fact in observation.error_codes] == [
        ("234", "234", "m-1")]
    manager = DialogueManager()
    state = manager.advance(DialogueState(), text, "m-1", observation=observation)
    assert [fact.value for fact in state.error_codes] == ["234"]
    restored = DialogueState.from_dict(state.to_dict())
    assert [(fact.value, fact.message_id) for fact in restored.error_codes] == [("234", "m-1")]

    store = ConversationStore(tmp_path / "error-code.sqlite3")
    cid = store.new(1, 2)
    record = Understanding("diagnosis", False, (), observation, {}, "test", 1)
    store.begin(cid, text, semantic_mode=True, understanding=understanding_to_dict(record))
    persisted = store.dialogue_state(cid)
    reopened = ConversationStore(tmp_path / "error-code.sqlite3")
    assert [(fact.value, fact.message_id) for fact in reopened.dialogue_state(cid).error_codes] == [
        ("234", persisted.error_codes[0].message_id)]


def test_frozen_d04_t01_t02_preserve_fn234_across_followup_turns():
    manager = DialogueManager()
    first = "На моей кассе Эвотор появилась ошибка ФН 234. Обязательно менять накопитель?"
    _, _, _, first_obs = validate_response(payload(first, kind="diagnosis", intent="device",
        operation="diagnose", obj="касса", object_quote="кассе", relation="new_task",
        entities=[("manufacturer", "Эвотор", "Эвотор")], symptom="ошибка ФН 234",
        goal="Обязательно менять накопитель?"), first, "D04-T01")
    state = manager.advance(DialogueState(), first, "D04-T01", observation=first_obs)
    assert [fact.value for fact in state.error_codes] == ["234"]

    followup = "кассе Эвотор появилась ошибка ФН 234"
    _, _, _, followup_obs = validate_response(payload(followup, kind="diagnosis", relation="continue",
        intent="device", operation="diagnose", obj="касса", object_quote="кассе",
        entities=[("manufacturer", "Эвотор", "Эвотор")], symptom="ошибка ФН 234"),
        followup, "D04-T02", state)
    state = manager.advance(state, followup, "D04-T02", observation=followup_obs)
    assert [(fact.value, fact.message_id) for fact in state.error_codes] == [
        ("234", "D04-T02")]


@pytest.mark.parametrize(("text", "quotes", "expected"), [
    ("Касса показывает ошибку ФН 231, а не 234", ["ФН 231", "не 234"], ["231"]),
    ("Не ФН 231, а ФН 234 — касса пишет именно его", ["Не ФН 231, а ФН 234"], ["234"]),
    ("Нет, я ошибся: не ФН 231, а 234", ["не ФН 231"], ["234"]),
    ("Бот ранее написал «ФН 231», но касса код не показывает", ["ФН 231"], []),
    ("Версия ПО 3.234; модель 7.3", ["3.234", "7.3"], []),
])
def test_only_positive_client_incident_codes_become_facts(text, quotes, expected):
    raw = payload(text, kind="diagnosis", intent="device", operation="diagnose",
                  obj=None, relation="new_task", error_codes=quotes)
    _, _, _, observation = validate_response(raw, text, 9)
    assert [fact.value for fact in observation.error_codes] == expected


def test_standalone_error_definition_does_not_confirm_an_incident_code():
    text = "Что означает ФН 231?"
    raw = payload(text, kind="information", intent="general", operation="explain",
                  obj="понятие", object_quote="ФН 231", relation="new_task",
                  goal=text, error_codes=["ФН 231"])
    _, _, _, observation = validate_response(raw, text, 4)
    assert observation.error_codes == []

    incident_question = "Касса показывает ФН 234, что означает этот код?"
    raw = payload(incident_question, kind="information", intent="general", operation="explain",
        obj="понятие", object_quote="ФН 234", relation="new_task", goal=incident_question,
        error_codes=[])
    _, _, _, incident_observation = validate_response(raw, incident_question, 5)
    assert [fact.value for fact in incident_observation.error_codes] == ["234"]


def test_corrected_and_multiple_codes_keep_exact_client_spans_on_active_task():
    manager = DialogueManager()
    first = "Касса показывает ошибку ФН 231."
    _, _, _, first_obs = validate_response(payload(first, kind="diagnosis", intent="fiscal_drive",
        operation="diagnose", obj="ФН", object_quote="ФН", error_codes=["ФН 231"]), first, 1)
    state = manager.advance(DialogueState(), first, 1, observation=first_obs)
    corrected = "Не ФН 231, а ФН 234 — касса пишет именно его."
    _, _, _, corrected_obs = validate_response(payload(corrected, kind="diagnosis", relation="continue",
        intent="fiscal_drive", operation="diagnose", obj="ФН", object_quote="ФН",
        error_codes=["Не ФН 231, а ФН 234"]), corrected, 2, state)
    state = manager.advance(state, corrected, 2, observation=corrected_obs)
    assert [(fact.value, fact.message_id) for fact in state.error_codes] == [("234", 2)]
    assert any(fact.value == "231" for fact in state.active_task.superseded_facts)

    multiple = "Касса попеременно показывает ошибку ФН 234 и код ошибки 235."
    _, _, _, multiple_obs = validate_response(payload(multiple, kind="diagnosis", relation="continue",
        intent="fiscal_drive", operation="diagnose", obj="ФН", object_quote="ФН",
        error_codes=["ФН 234 и код ошибки 235"]), multiple, 3, state)
    state = manager.advance(state, multiple, 3, observation=multiple_obs)
    assert [fact.value for fact in state.error_codes] == ["234", "235"]
    assert all(fact.message_id == 3 for fact in state.error_codes)


def test_old_sqlite_state_with_only_error_field_still_loads(tmp_path):
    import json
    old = DialogueState(task_id="task:old", intent="fiscal_drive", operation="diagnose",
        error=Fact("234", 7, "234", 12, 15)).to_dict()
    old["task_context"].pop("error_codes", None)
    restored = DialogueState.from_dict(old)
    assert [(fact.value, fact.message_id) for fact in restored.error_codes] == [("234", 7)]
    store = ConversationStore(tmp_path / "legacy-error.sqlite3")
    cid = store.new(3, 4)
    store.dialogue_state(cid)
    with store.connect() as db:
        db.execute("UPDATE dialogue_states_v2 SET state_json=?,processed_message_id=0 WHERE conversation_id=?",
                   (json.dumps(old, ensure_ascii=False), cid))
    assert [(fact.value, fact.message_id) for fact in store.dialogue_state(cid).error_codes] == [
        ("234", 7)]


def test_confirmed_codes_do_not_follow_a_new_task_or_cash_register():
    manager = DialogueManager()
    first = "На кассе Эвотор появилась ошибка ФН 234."
    _, _, _, observation = validate_response(payload(first, intent="device", operation="diagnose",
        obj="касса", object_quote="кассе", entities=[("manufacturer", "Эвотор", "Эвотор")],
        symptom="ошибка ФН 234", error_codes=["ФН 234"]), first, 1)
    state = manager.advance(DialogueState(), first, 1, observation=observation)
    changed_cash = "Теперь касса АТОЛ 30Ф пишет ошибку, код не успел прочитать."
    _, _, _, observation = validate_response(payload(changed_cash, intent="device", operation="diagnose",
        obj="касса", object_quote="касса", relation="new_task",
        entities=[("manufacturer", "АТОЛ", "АТОЛ")], symptom="пишет ошибку"), changed_cash, 2, state)
    state = manager.advance(state, changed_cash, 2, observation=observation)
    assert state.error_codes == []

    new_task = "В Диадоке не отображается входящий УПД."
    _, _, _, observation = validate_response(payload(new_task, kind="diagnosis", intent="integration",
        operation="diagnose", obj="УПД", object_quote="УПД", relation="new_task",
        entities=[("service", "Диадок", "Диадок")], symptom="не отображается"), new_task, 3, state)
    state = manager.advance(state, new_task, 3, observation=observation)
    assert state.task_context.topic_start_message_id == 3
    assert state.error_codes == []


@pytest.mark.parametrize(("text", "canonical"), [
    ("В Saby не могу найти входящий документ.", "Saby"),
    ("В СБИС не отображается входящий УПД.", "Saby"),
    ("В Диадоке не вижу отправленный УПД.", "Диадок"),
    ("В БИФИТ Касса не работает терминал.", "БИФИТ Касса"),
    ("В БИФИТ не работает терминал.", "БИФИТ"),
])
def test_understanding_recovers_registered_route_when_model_omits_entity(text, canonical):
    raw = payload(text, kind="diagnosis", intent="unknown", operation="diagnose", obj=None,
                  relation="new_task", entities=())
    _, _, _, observation = validate_response(raw, text, 77)
    state = DialogueManager().advance(DialogueState(), text, 77, observation=observation)
    assert [fact.value for fact in observation.entities["service"]] == [canonical]
    assert state.routing_slot == "service" and state.routing_service == canonical


def test_transliterated_model_name_is_recovered_from_known_brand_alias():
    text = "АТОЛ 30Ф не передаёт чеки"
    raw = payload(text, entities=[("Atol 30F", "Atol 30F", "АТОЛ 30Ф")])
    _, _, _, observation = validate_response(raw, text, 77)
    equipment = observation.entities.get("equipment", [])
    assert len(equipment) == 1
    assert equipment[0].value == "АТОЛ 30Ф"
    assert equipment[0].quote == "АТОЛ 30Ф"


def test_explanation_operation_supplies_generic_intent_when_model_omits_it():
    text = "Что такое ОФД?"
    raw = payload(text, kind="information", intent="unknown", operation="explain",
                  obj="ОФД", object_quote="ОФД", relation="new_task")
    kind, _, _, observation = validate_response(raw, text, 77)
    assert kind == "information"
    assert observation.intent == "general" and observation.operation == "explain"
    assert any(item.get("reason") == "general_intent_from_explanation_operation"
               for item in observation.validation_diagnostics)


def test_followup_cannot_clear_pending_scope_question_without_answer():
    previous = DialogueState(task_id="task:1", intent="receipt", operation="diagnose",
        expected=ExpectedClarification("service", "Какой оператор?", 2, "source_scope_context_missing"))
    text = "Интернет работает, что ещё проверить?"
    raw = payload(text, kind="information", intent="unknown", operation="diagnose", obj=None,
        relation="answer_to_clarification", goal="что ещё проверить?")
    _, _, _, observation = validate_response(raw, text, 77)
    state = DialogueManager().advance(previous, text, 77, observation=observation)
    assert state.transition == "continue_task"
    assert state.expected == previous.expected
    assert any(f.value == "что ещё проверить?" for f in state.goals)


def test_definition_wording_overrides_lookup_label_without_object_specific_rules():
    examples = (
        ("Что такое ОФД?", "ОФД"),
        ("Что такое ФН?", "ФН"),
        ("Объясни, что такое ККТ", "ККТ"),
    )
    for text, subject in examples:
        raw = payload(text, kind="question", intent="information", operation="lookup",
                      obj="понятие", object_quote=subject, relation="new_task")
        kind, _, _, observation = validate_response(raw, text, 77)
        state = DialogueManager().advance(DialogueState(), text, 77, observation=observation)
        assert kind == "information"
        assert observation.intent == "general" and observation.operation == "explain"
        assert state.operation == "explain"
        assert any(item.get("reason") == "explicit_conceptual_information_request"
                   for item in observation.validation_diagnostics)


def test_definition_wording_overrides_conflicting_domain_intent():
    text = "Что такое ОФД?"
    raw = payload(text, kind="information", intent="fiscal_drive", operation="explain",
        obj="ОФД", object_quote="ОФД", relation="new_task")
    kind, _, _, observation = validate_response(raw, text, 77)
    assert kind == "information"
    assert observation.intent == "general" and observation.operation == "explain"
    assert observation.object == "ОФД"
    assert any(item.get("reason") == "conceptual_question_is_general_information"
               for item in observation.validation_diagnostics)


def test_comparison_purpose_and_principle_questions_normalize_to_general_explain():
    examples = (
        "Чем отличается фискальный накопитель от оператора фискальных данных?",
        "В чём разница между локальной программой и облачным сервисом?",
        "Для чего нужен API?",
        "Как работает DNS?",
        "Объясни принцип работы базы данных.",
    )
    for text in examples:
        raw = payload(text, kind="information", intent="unknown", operation="lookup",
                      obj="понятие", object_quote=None, relation="new_task", goal=text)
        kind, _, _, observation = validate_response(raw, text, 79)
        state = DialogueManager().advance(DialogueState(), text, 79, observation=observation)
        assert kind == "information"
        assert observation.intent == "general" and observation.operation == "explain"
        assert state.intent == "general" and state.operation == "explain"


def test_technical_error_explanation_is_not_reclassified_as_general_concept():
    text = "Объясни, как исправить ошибку ФН 234"
    raw = payload(text, kind="information", intent="unknown", operation="lookup",
                  obj="понятие", object_quote=None, relation="new_task", goal=text)
    kind, _, _, observation = validate_response(raw, text, 80)
    assert kind == "information"
    assert observation.operation == "diagnose"
    assert observation.intent != "general"

    # Deterministic replay of the saved live provider fields: raw `lookup`
    # was normalized to `search` before this generic phrasing rule resolves it.
    text = "Что такое ОФД?"
    saved_replay = payload(text, kind="question", intent="information", operation="lookup",
        obj="OFD", object_quote="ОФД", relation="new_task")
    kind, _, _, observation = validate_response(saved_replay, text, "smoke-1")
    state = DialogueManager().advance(DialogueState(), text, "smoke-1", observation=observation)
    assert kind == "information" and observation.operation == state.operation == "explain"


def test_explicit_receipt_lookup_stays_search_when_concept_rule_is_present():
    text = "Как найти чек по ФД?"
    raw = payload(text, kind="question", intent="information", operation="lookup",
                  obj="receipt", object_quote="чек", relation="new_task", goal=text)
    kind, _, _, observation = validate_response(raw, text, 78)
    state = DialogueManager().advance(DialogueState(), text, 78, observation=observation)
    assert kind == "information"
    assert observation.intent == "receipt" and observation.operation == "search"
    assert state.intent == "receipt" and state.operation == "search"


def test_unique_registered_object_is_grounded_when_model_omits_it():
    text = "Привет! Объясни простыми словами, что такое ОФД?"
    data = payload(text, kind="information", intent="general", operation="explain",
        obj=None, goal="что такое ОФД", relation="new_task")
    kind, _, _, obs = validate_response(data, text, 77)
    state = DialogueManager().advance(DialogueState(), text, 77, observation=obs)
    assert kind == "information" and obs.object == "ОФД"
    assert obs.object_evidence.quote == "ОФД"
    assert state.object == "ОФД"
    assert any(d.get("reason") == "unique_registered_object_alias_from_current_message"
               for d in obs.validation_diagnostics)


def test_semantic_intent_needs_no_quote_but_concrete_claims_do():
    for text in ("Что такое ОФД?", "Объясните простыми словами, что такое оператор фискальных данных?"):
        data = payload(text, kind="information", intent="general", operation="explain", obj="понятие",
            object_quote="ОФД" if "ОФД" in text else "оператор фискальных данных")
        kind, _, _, obs = validate_response(data, text, 77)
        assert kind == "information" and obs.intent == "general" and obs.intent_evidence is None
    unsupported_fact = payload("Что такое ОФД?", kind="information", intent="general", operation="explain",
        obj="понятие", object_quote="ОФД", entities=[("ofd", "Такском", "ОФД")])
    kind, _, _, obs = validate_response(unsupported_fact, "Что такое ОФД?", 77)
    assert kind == "information" and obs.intent == "general" and obs.operation == "explain"
    assert not obs.entities
    assert any(item["field"] == "entities[0]" and item["status"] == "rejected"
               for item in obs.validation_diagnostics)


def test_diagnosis_and_explicit_entity_are_evidence_bound():
    text = "Эвотор. Интернет не работает, не отправляются чеки."
    data = payload(text, entities=[("manufacturer", "Эвотор", "Эвотор")], symptom="не отправляются чеки",
        operation_quote="не отправляются чеки", goal="не отправляются чеки")
    kind, _, _, obs = validate_response(data, text, 77)
    state = DialogueManager().advance(DialogueState(), text, 77, observation=obs)
    assert kind == "diagnosis" and state.entity("manufacturer") == "Эвотор"
    assert state.symptom.quote == "не отправляются чеки"


def test_clarification_answer_adds_detail_without_replaying_lexical_analyzer():
    prior = DialogueState(task_id="task:1", intent="receipt", operation="diagnose", expected=
        ExpectedClarification("manufacturer", "Какой производитель кассы?", 2, "missing_manufacturer"))
    text = "Эвотор. Интернет работает."
    data = payload(text, relation="answer_to_clarification", intent="unknown", operation="unknown", obj=None,
        intent_quote=None, operation_quote=None, object_quote=None, relation_quote="Эвотор",
        entities=[("manufacturer", "Эвотор", "Эвотор")], unknown=[])
    _, _, _, obs = validate_response(data, text, 77)
    # A deliberately unusable lexical analyzer proves semantic replay does not call it.
    class NeverLexical:
        def analyze(self, *_args): raise AssertionError("lexical analyzer must not run")
    state = DialogueManager(NeverLexical()).advance(prior, text, 77, observation=obs)
    assert state.operation == "diagnose" and state.expected is None
    assert state.entity("manufacturer") == "Эвотор" and state.transition == "clarification"


def test_new_topic_gets_new_task_context_and_drops_old_parameters():
    prior = DialogueState(task_id="task:1", intent="receipt", operation="diagnose",
        parameters=[])
    prior.parameters.append(__import__("app.dialogue_state", fromlist=["Fact"]).Fact.span("за вчера", 1))
    text = "Теперь другой вопрос: как добавить сотрудника?"
    data = payload(text, kind="instruction", intent="access", operation="add_employee", obj="сотрудник",
        relation="new_task", entities=(), goal="добавить сотрудника",
        intent_quote="добавить сотрудника", operation_quote="добавить", object_quote="сотрудника")
    _, _, _, obs = validate_response(data, text, 78)
    state = DialogueManager().advance(prior, text, 78, observation=obs)
    assert state.task_id == "task:78" and state.operation == "add_employee"
    assert not state.parameters and state.topic_start_message_id == 78


def test_unknown_model_is_persisted_and_not_invented():
    text = "Не знаю модель кассы."
    data = payload(text, kind="feedback", relation="answer_to_clarification", intent="unknown",
        operation="unknown", obj=None, intent_quote=None, operation_quote=None, object_quote=None,
        relation_quote="модель кассы", unknown=["equipment"], goal=None)
    _, _, unknown, obs = validate_response(data, text, 77)
    prior = DialogueState(task_id="task:1", intent="receipt", operation="diagnose",
                          expected=ExpectedClarification("equipment", "Какая модель?"))
    state = DialogueManager().advance(prior, text, 77, observation=obs, unknown_facts=list(unknown))
    assert state.task_context.unknown_facts == ["equipment"]
    assert state.task_context.unknown_facts == list(obs.unknown_facts)
    assert not state.task_entities.get("equipment")
    assert state.expected is None


def test_unknown_fact_requires_a_quote_from_the_current_message():
    text = "Не знаю модель кассы."
    data = payload(text, kind="feedback", relation="answer_to_clarification", intent="unknown",
        operation="unknown", obj=None, unknown=["equipment"], unknown_quote="модель сервера")
    _, _, unknown, obs = validate_response(data, text, 77)
    assert not unknown and not obs.unknown_facts
    assert any(item["field"] == "unknown_facts[0]" and item["status"] == "rejected"
               for item in obs.validation_diagnostics)


def test_direct_specialist_request_is_explicit_and_not_operator_ofd():
    text = "Позови специалиста, пожалуйста."
    data = payload(text, kind="escalation", intent="unknown", operation="unknown", obj=None,
        intent_quote=None, operation_quote=None, object_quote=None, relation="continue", relation_quote="Позови",
        specialist=True, specialist_quote="Позови специалиста")
    kind, requested, _, _ = validate_response(data, text, 77)
    assert kind == "escalation" and requested
    negated = payload("ОФД уже известен, специалист не нужен", kind="escalation", intent="unknown",
        operation="unknown", obj=None, intent_quote=None, operation_quote=None, object_quote=None,
        relation="unknown", relation_quote=None, specialist=True,
        specialist_quote="специалист не нужен")
    _, requested, _, obs = validate_response(negated, "ОФД уже известен, специалист не нужен", 77)
    assert not requested and any(item["field"] == "specialist_requested"
                                 and item["status"] == "rejected"
                                 for item in obs.validation_diagnostics)


def test_unquoted_or_cross_slot_facts_fail_closed():
    text = "Платформа ОФД."
    data = payload(text, kind="information", intent="general", operation="explain", obj="понятие",
        intent_quote=text, operation_quote=text, object_quote="ОФД", relation="new_task", relation_quote=text,
        entities=[("manufacturer", "Эвотор", "Платформа ОФД")])
    _, _, _, obs = validate_response(data, text, 77)
    assert "manufacturer" not in obs.entities and obs.entities["ofd"][0].value == "Платформа ОФД"
    assert obs.intent == "general" and obs.operation == "explain"


def test_valid_fields_survive_one_bad_entity_and_alias_is_normalized_from_source():
    text = "В aQsi Online не отправляются чеки, касса Эвотор."
    data = payload(text, entities=[("service", "aQsi", "aQsi Online"),
        ("manufacturer", "АТОЛ", "касса Эвотор")], symptom="не отправляются чеки",
        operation="transmit", intent="receipt", obj="чек", object_quote="чеки")
    _, _, _, obs = validate_response(data, text, 77)
    assert obs.entities["service"][0].value == "aQsi Online"
    assert obs.entities["manufacturer"][0].value == "Эвотор"
    assert any(d["reason"] == "normalized_to_known_alias_from_source" for d in obs.validation_diagnostics)


def test_negated_entity_and_overlapping_cross_slot_alias_are_not_saved():
    text = "Не используем Эвотор, работаем в АТОЛ Онлайн."
    data = payload(text, entities=[("manufacturer", "Эвотор", "Эвотор"),
        ("manufacturer", "АТОЛ", "АТОЛ Онлайн"),
        ("service", "АТОЛ", "АТОЛ Онлайн")])
    _, _, _, obs = validate_response(data, text, 77)
    assert "manufacturer" not in obs.entities
    assert obs.entities["service"][0].value == "АТОЛ Онлайн"
    reasons = [item["reason"] for item in obs.validation_diagnostics if item["status"] == "rejected"]
    assert "entity_mention_is_negated_or_uncertain" in reasons
    assert "entity_not_supported_by_source_alias" in reasons
    symptom_text = "Не отправляются чеки на кассе Эвотор."
    symptom_data = payload(symptom_text, entities=[("manufacturer", "Эвотор", "Эвотор")],
                           symptom=symptom_text)
    _, _, _, symptom_obs = validate_response(symptom_data, symptom_text, 78)
    assert symptom_obs.entities["manufacturer"][0].value == "Эвотор"


def test_one_invalid_semantic_field_becomes_unknown_for_safe_clarification():
    text = "Как передать чек?"
    data = payload(text, kind="instruction", intent="receipt", operation="not_a_real_operation",
        obj="чек", object_quote="чек")
    _, _, _, obs = validate_response(data, text, 77)
    assert obs.intent == "receipt" and obs.operation == "unknown"
    assert any(d["field"] == "operation" and d["status"] == "rejected"
               for d in obs.validation_diagnostics)
    state = DialogueManager().advance(DialogueState(), text, 77, observation=obs)
    assert state.operation == "unknown" or state.analysis_required


def test_unknown_operation_on_grounded_information_question_uses_read_only_search():
    text = "Как найти чек по ФД?"
    data = payload(text, kind="information", intent="information_request",
        operation="unrecognized_lookup_label", obj="receipt", object_quote="чек", goal=text)
    kind, _, _, obs = validate_response(data, text, 77)
    assert kind == "information" and obs.intent == "receipt" and obs.operation == "search"
    assert any(d.get("reason") == "safe_information_lookup_from_grounded_goal"
               for d in obs.validation_diagnostics)
    assert any(d.get("reason") == "unique_task_family_from_grounded_direct_object"
               for d in obs.validation_diagnostics)
    state = DialogueManager().advance(DialogueState(), text, 77, observation=obs)
    assert state.operation == "search" and state.expected is None


def test_common_semantic_label_aliases_are_canonicalized_locally():
    text = "Что такое ОФД?"
    data = payload(text, kind="information_request", intent="definition", operation="explanation",
        obj="ОФД", object_quote="ОФД", relation="new_topic")
    kind, _, _, obs = validate_response(data, text, 77)
    assert kind == "information" and obs.intent == "general" and obs.operation == "explain"
    assert obs.relation == "new_task" and obs.object == "ОФД"
    assert {item["field"]: item["reason"] for item in obs.validation_diagnostics}["request_type"] == "normalized_turn_type_alias"


def test_saved_explanation_labels_preserve_continuation_and_task_state(tmp_path):
    from app.answer_service import Answer
    store = ConversationStore(tmp_path / "saved_explanations.sqlite3")
    cid = store.new(11, 12)
    first = "Привет! Объясни простыми словами, что такое ОФД?"
    first_data = payload(first, kind="explanation", intent="explain", operation="explain",
        obj="ОФД", object_quote="ОФД", goal="что такое ОФД", relation="new_task")
    kind, specialist, unknown, obs = validate_response(first_data, first, "current")
    assert kind == "information" and obs.intent == "general" and obs.operation == "explain"
    mid = store.begin(cid, first, semantic_mode=True, understanding=understanding_to_dict(
        Understanding(kind, specialist, unknown, obs, {}, "test", 1)))
    task_id = store.dialogue_state(cid).task_id
    store.complete(mid, Answer("Definition source answer", scenario="answer"))

    second = "А зачем он вообще нужен кассе?"
    second_data = payload(second, kind="explain_operation", intent="explain_operation",
        operation="explain_operation", obj="ОФД", object_quote="он", goal=second,
        relation="continuation")
    kind, specialist, unknown, obs = validate_response(second_data, second, "current")
    mid = store.begin(cid, second, semantic_mode=True, understanding=understanding_to_dict(
        Understanding(kind, specialist, unknown, obs, {}, "test", 1)))
    state = store.dialogue_state(cid)
    assert kind == "information" and state.task_id == task_id
    assert state.operation == "explain" and state.goals[-1].quote == second
    store.complete(mid, Answer("Continuation source answer", scenario="answer"))

    # Repeating the first request is a new task, not a continuation forced by stale context.
    kind, _, _, repeated = validate_response(first_data, first, 900)
    state = DialogueManager().advance(state, first, 900, observation=repeated)
    assert state.task_id == "task:900" and state.transition == "new_task"


def test_saved_receipt_lookup_labels_and_omitted_platform_alias_reach_typed_state(tmp_path):
    text = "Как найти чек по номеру ФД в Платформе ОФД?"
    raw = payload(text, kind="information", intent="information_request", operation="find_receipt",
        obj="receipt", object_quote="чек", goal=text, relation="new_task")
    kind, specialist, unknown, obs = validate_response(raw, text, "current")
    assert kind == "information" and obs.intent == "receipt" and obs.operation == "search"
    assert obs.object == "чек" and obs.object_evidence.quote == "чек"
    assert obs.entities["ofd"][0].value == "Платформа ОФД"
    assert any(d.get("reason") == "exact_known_alias_found_in_current_message"
               and d.get("value") == "Платформа ОФД" for d in obs.validation_diagnostics)
    store = ConversationStore(tmp_path / "receipt_lookup.sqlite3")
    cid = store.new(21, 22)
    store.begin(cid, text, semantic_mode=True, understanding=understanding_to_dict(
        Understanding(kind, specialist, unknown, obs, {}, "test", 1)))
    state = store.dialogue_state(cid)
    assert state.task_id and state.intent == "receipt" and state.operation == "search"
    assert state.entity("ofd") == "Платформа ОФД"
    assert state.expected is None


def test_search_target_is_grounded_before_parameter_without_accepting_parameter_as_object():
    text = "Как найти чек по номеру ФД в Платформе ОФД?"
    raw = payload(text, kind="information", intent="general", operation="search",
        obj="receipt", object_quote=None, goal=text, relation="new_task")
    raw["object_evidence"] = None
    kind, _, _, obs = validate_response(raw, text, 31)
    assert kind == "information" and obs.operation == "search"
    assert obs.object == "чек" and obs.object_evidence.quote == "чек"
    assert obs.intent == "receipt"
    assert any(item["reason"] == "registered_search_target_grounded_before_parameter"
               for item in obs.validation_diagnostics)


def test_common_question_information_and_lookup_labels_normalize_to_safe_search():
    text = "Как найти чек по номеру ФД в Платформе ОФД?"
    raw = payload(text, kind="question", intent="information", operation="lookup",
        obj="чек", object_quote="чек", goal=text,
        entities=[("ofd", "Платформа ОФД", "Платформе ОФД")])
    kind, _, _, obs = validate_response(raw, text, 32)
    assert kind == "information"
    assert obs.intent == "receipt" and obs.operation == "search" and obs.object == "чек"
    assert obs.entities["ofd"][0].value == "Платформа ОФД"


def test_reference_pronoun_does_not_ground_a_new_object_claim():
    first = "Объясни, что такое ОФД?"
    first_raw = payload(first, kind="information", intent="general", operation="explain",
        obj="ОФД", object_quote="ОФД", goal=first)
    _, _, _, first_obs = validate_response(first_raw, first, 10)
    prior = DialogueManager().advance(DialogueState(), first, 10, observation=first_obs)
    assert prior.object == "ОФД"

    followup = "А зачем он вообще нужен кассе?"
    followup_raw = payload(followup, kind="information", relation="continuation",
        intent="general", operation="explain", obj="ОФД", object_quote="он", goal=followup)
    _, _, _, followup_obs = validate_response(followup_raw, followup, 11)
    assert followup_obs.object is None
    state = DialogueManager().advance(prior, followup, 11, observation=followup_obs)
    assert state.object == "ОФД" and state.task_id == prior.task_id
    assert any(d.get("reason") == "object_value_not_grounded_by_evidence"
               for d in followup_obs.validation_diagnostics)


def test_saved_operator_clarification_preserves_diagnosis_and_applies_exact_known_alias(tmp_path):
    from app.answer_service import Answer
    first = "На кассе Эвотор перестали отправляться чеки в ОФД. Помоги разобраться."
    raw_first = payload(first, kind="diagnosis", intent="request_help", operation="diagnosis",
        obj="Эвотор", object_quote="Эвотор", goal="Помоги разобраться",
        symptom="перестали отправляться чеки в ОФД", relation="new_task")
    kind, specialist, unknown, obs = validate_response(raw_first, first, "current")
    assert obs.operation == "diagnose" and obs.entities["manufacturer"][0].value == "Эвотор"
    store = ConversationStore(tmp_path / "operator_clarification.sqlite3")
    cid = store.new(31, 32)
    mid = store.begin(cid, first, semantic_mode=True, understanding=understanding_to_dict(
        Understanding(kind, specialist, unknown, obs, {}, "test", 1)))
    store.complete(mid, Answer("Какой оператор?", scenario="clarify",
        scenario_reason="source_scope_context_missing", clarification_slot="service"))
    prior = store.dialogue_state(cid)
    assert prior.operation == "diagnose" and prior.expected.slot == "service"

    answer = "Оператор у меня Платформа ОФД."
    raw_answer = payload(answer, kind="information", relation="clarification_answer",
        intent="provide_info", operation="diagnose", obj=None, goal=None,
        entities=[("service", "Платформа ОФД", "Платформа ОФД")])
    kind, specialist, unknown, obs = validate_response(raw_answer, answer, "current")
    assert kind == "information" and obs.relation == "answer_to_clarification"
    assert obs.entities["ofd"][0].value == "Платформа ОФД"
    mid = store.begin(cid, answer, semantic_mode=True, understanding=understanding_to_dict(
        Understanding(kind, specialist, unknown, obs, {}, "test", 1)))
    state = store.dialogue_state(cid)
    assert state.operation == "diagnose" and state.entity("ofd") == "Платформа ОФД"
    assert state.expected is None and not state.analysis_required
    assert state.relation == "answer_to_clarification" and state.transition == "clarification"


def test_schema_has_semantic_labels_without_evidence_properties():
    fields = response_schema()["schema"]["properties"]
    assert "intent_evidence" not in fields
    assert "operation_evidence" not in fields
    assert "relation_evidence" not in fields
    assert fields["unknown_facts"]["items"]["properties"]["evidence"]["type"] == "object"
    assert "enum" not in fields["object"]
    assert "enum" not in fields["intent"]
    assert response_schema()["strict"] is True


def test_prior_symptom_summary_is_distinct_from_current_turn_output():
    text = "Касса не отправляет чеки."
    state = DialogueState(task_id="task:1", intent="receipt", operation="diagnose")
    state.symptom = Fact.span(text, "prior", text.index("не отправляет чеки"),
                              text.index("не отправляет чеки") + len("не отправляет чеки"))
    before = state.to_dict()
    active = _state_summary(state)["active_task"]
    assert "symptom" not in active
    assert active["prior_symptom_facts"] == [
        {"value": "не отправляет чеки", "source_message_id": "prior"}]
    assert state.to_dict() == before
    assert response_schema()["schema"]["properties"]["symptom"]["type"] == ["object", "null"]


def test_current_turn_symptom_is_null_or_exact_current_message_quote():
    question = "А зачем он нужен кассе?"
    absent = payload(question, kind="information", relation="continuation", intent="general",
                     operation="explain", obj=None, symptom=None)
    _, _, _, observation = validate_response(absent, question, "current")
    assert observation.symptom is None

    message = "Касса не отправляет чеки."
    present = payload(message, kind="diagnosis", intent="receipt", operation="diagnose",
                      obj=None, symptom="не отправляет чеки")
    _, _, _, observation = validate_response(present, message, "current")
    assert observation.symptom.quote == "не отправляет чеки"
    assert observation.symptom.message_id == "current"

    unsupported = payload(message, kind="diagnosis", intent="receipt", operation="diagnose",
                          obj=None, symptom="нет связи с интернетом")
    _, _, _, observation = validate_response(unsupported, message, "current")
    assert observation.symptom is None
    assert any(item["field"] == "symptom" and item["status"] == "rejected"
               for item in observation.validation_diagnostics)


@pytest.mark.parametrize(("request_type", "intent", "operation", "expected_kind", "expected_operation"), [
    ("request", "troubleshooting", "lookup", "diagnosis", "diagnose"),
    ("diagnostic_request", "error_explanation", "lookup", "diagnosis", "diagnose"),
])
def test_semantic_aliases_are_normalized_with_context(
        request_type, intent, operation, expected_kind, expected_operation):
    text = "Подскажите, что означает ошибка 234?"
    raw = payload(text, kind=request_type, intent=intent, operation=operation,
                  obj="ошибка", goal="ошибка 234", symptom="ошибка 234")
    kind, _, _, obs = validate_response(raw, text, "alias")
    assert kind == expected_kind
    assert obs.operation == expected_operation
    assert obs.goals and obs.goals[0].quote == "ошибка 234"


def test_explicit_receipt_lookup_stays_search():
    text = "Найдите чек по номеру ФН в личном кабинете."
    raw = payload(text, kind="question", intent="ask", operation="lookup", obj="чек",
                  goal="Найдите чек по номеру ФН в личном кабинете")
    kind, _, _, obs = validate_response(raw, text, "lookup")
    assert kind == "information" and obs.operation == "search"
    raw["intent"] = "troubleshooting"
    kind, _, _, obs = validate_response(raw, text, "lookup")
    assert kind == "information" and obs.operation == "search"


def test_lookup_is_not_globally_mapped_to_search_and_still_requires_exact_grounding():
    text = "Не могу войти, потому что пароль не принимается."
    raw = payload(text, kind="request", intent="troubleshooting", operation="lookup",
                  obj=None, goal="пароль не принимается", symptom="пароль не принимается")
    kind, _, _, obs = validate_response(raw, text, "lookup")
    assert kind == "diagnosis" and obs.operation == "diagnose"
    raw["symptom"] = {"quote": "сайт заблокирован"}
    _, _, _, obs = validate_response(raw, text, "lookup")
    assert obs.symptom is None
    assert any(d["field"] == "symptom" and d["status"] == "rejected"
               for d in obs.validation_diagnostics)


def test_tspiot_is_retyped_as_component_from_exact_span_not_ofd_or_service():
    text = "На Эвотор 7.3 модуль ТС ПИоТ не запускается."
    raw = payload(text, kind="diagnostic_request", intent="troubleshooting",
        operation="diagnosis", obj="касса", object_quote="Эвотор 7.3",
        goal="модуль ТС ПИоТ не запускается", symptom="не запускается",
        entities=[("manufacturer", "Эвотор", "Эвотор"),
                  ("system", "ТС ПИоТ", "ТС ПИоТ")])
    kind, _, _, obs = validate_response(raw, text, "tspiot")
    assert kind == "diagnosis"
    assert obs.entities["manufacturer"][0].value == "Эвотор"
    assert obs.entities["component"][0].value.casefold() == "ТС ПИоТ".casefold()
    assert "ofd" not in obs.entities and "service" not in obs.entities
    assert any(d["field"] == "entities[1]" and d["reason"] == "retyped_from_exact_source_alias"
               for d in obs.validation_diagnostics)


def test_unrelated_rejected_intent_does_not_drop_exact_symptom_or_clear_unmet_expected():
    text = "Интернет проверен, но чеки всё ещё не передаются."
    state = DialogueState(task_id="task:prior", intent="receipt", operation="diagnose")
    state.expected = ExpectedClarification("details", "Что уже проверили?", "assistant")
    raw = payload(text, kind="question", relation="continue", intent="some_unsupported_intent",
        operation="some_unsupported_operation", obj=None, goal="чеки всё ещё не передаются",
        symptom="чеки всё ещё не передаются")
    _, _, _, obs = validate_response(raw, text, "followup")
    updated = DialogueManager().advance(state, text, "followup", observation=obs)
    assert obs.symptom is not None
    assert updated.symptom and updated.symptom.quote == "чеки всё ещё не передаются"
    assert updated.task_id == "task:prior"
    assert updated.expected is None
    assert any(f.value.startswith("Интернет проверен") for f in updated.details)


def test_contradiction_keeps_expected_clarification_and_prior_symptom():
    text = "Нет, это не Эвотор; речь о другой кассе."
    state = DialogueState(task_id="task:prior", intent="receipt", operation="diagnose")
    state.expected = ExpectedClarification("equipment", "Какая модель кассы?", "assistant")
    state.symptom = Fact.span("Чеки не передаются.", "prior", 0, len("Чеки не передаются."))
    raw = payload(text, relation="contradiction", intent="unknown", operation="unknown", obj=None,
                  entities=[("manufacturer", "Эвотор", "Эвотор")])
    _, _, _, obs = validate_response(raw, text, "contradiction")
    updated = DialogueManager().advance(state, text, "contradiction", observation=obs)
    assert updated.relation == "contradiction"
    assert updated.expected is not None and updated.expected.slot == "equipment"
    assert updated.symptom and updated.symptom.message_id == "prior"


def test_tspiot_negation_does_not_create_component_entity():
    text = "Мы не используем ТС ПИоТ; касса Эвотор не печатает чек."
    raw = payload(text, entities=[("component", "ТС ПИоТ", "ТС ПИоТ"),
                                  ("manufacturer", "Эвотор", "Эвотор")])
    _, _, _, obs = validate_response(raw, text, "negative")
    assert "component" not in obs.entities
    assert obs.entities["manufacturer"][0].value == "Эвотор"
    assert any(d["field"] == "entities[0]" and d["reason"] == "entity_mention_is_negated_or_uncertain"
               for d in obs.validation_diagnostics)


def test_explicit_manufacturer_model_pair_survives_wrong_object_and_entity_slots():
    text = "После настройки на Эвотор 7.3 чек не передается в ОФД."
    raw = payload(text, relation="new_task", intent="request_help", operation="troubleshooting",
        obj="Эвотор 7.3", object_quote="Эвотор 7.3",
        goal="чек не передается в ОФД", symptom="не передается",
        entities=[("destination", "ОФД", "ОФД")])
    _, _, _, obs = validate_response(raw, text, "model")
    assert obs.entities["manufacturer"][0].value == "Эвотор"
    assert obs.entities["equipment"][0].value == "Эвотор 7.3"
    fact = obs.entities["equipment"][0]
    assert text[fact.start:fact.end] == fact.quote == "Эвотор 7.3"
    assert any(d["field"] == "entities.equipment"
               and d["reason"] == "exact_known_manufacturer_model_span"
               for d in obs.validation_diagnostics)


def test_known_software_misclassified_as_equipment_keeps_confirmed_model_and_task():
    opening = "На Эвотор 7.3 чеки не передаются в ОФД."
    opening_raw = payload(opening, kind="diagnosis", relation="new_task", intent="receipt",
        operation="diagnose", obj="чек", object_quote="чеки",
        entities=[("manufacturer", "Эвотор", "Эвотор"),
                  ("equipment", "Эвотор 7.3", "Эвотор 7.3")])
    kind, specialist, unknown, observation = validate_response(opening_raw, opening, "opening")
    state = DialogueManager().advance(DialogueState(), opening, "opening",
        observation=observation, unknown_facts=list(unknown))

    followup = "EoU работает. Интернет работает. Адрес, порт и ИНН ОФД совпадают."
    raw = payload(followup, kind="instruction", relation="continue", intent="receipt",
        operation="request_specialist", obj=None,
        entities=[("equipment", "EoU", "EoU")])
    _, specialist, unknown, observation = validate_response(raw, followup, "followup", state)

    assert not specialist
    assert observation.operation == "unknown"
    assert "equipment" not in observation.entities
    assert observation.entities["component"][0].value == "EoU"
    assert any(item["field"] == "entities[0]"
               and item["reason"] == "retyped_from_exact_source_alias"
               for item in observation.validation_diagnostics)
    assert any(item["field"] == "operation_resolution"
               and item["reason"] == "specialist_request_uses_explicit_flag_not_task_operation"
               for item in observation.validation_diagnostics)

    updated = DialogueManager().advance(state, followup, "followup",
        observation=observation, unknown_facts=list(unknown))
    assert updated.task_id == state.task_id
    assert updated.task_entity("equipment") == "Эвотор 7.3"
    assert updated.task_entity("component") == "EoU"
    assert updated.operation == "diagnose"


def test_explicit_specialist_request_does_not_enter_task_operation_vocabulary():
    text = "Позови специалиста, пожалуйста."
    raw = payload(text, kind="escalation", relation="new_task", intent="unknown",
        operation="request_specialist", obj=None, specialist=True, specialist_quote=text)
    kind, specialist, unknown, observation = validate_response(raw, text, "handoff")

    assert kind == "escalation" and specialist
    assert observation.operation == "unknown"
    updated = DialogueManager().advance(DialogueState(), text, "handoff",
        observation=observation, unknown_facts=list(unknown))
    assert updated.operation == "unknown"


def test_explain_label_on_terse_followup_preserves_active_source_check_task():
    text = "Что делать дальше?"
    state = DialogueState(task_id="task:1", intent="receipt", operation="diagnose")
    state.task_context.procedure_id = "approved-procedure"
    state.task_context.shown_units = [{"unit_id": "check-1", "label": "Проверьте очередь."}]
    state.task_context.checks = [{"unit_id": "check-1", "status": "asked"}]
    raw = payload(text, kind="instruction", relation="continue", intent="receipt",
        operation="explain", obj=None, goal=text)

    _, _, unknown, observation = validate_response(raw, text, "followup", state)

    assert observation.operation == "unknown"
    assert any(item["field"] == "operation_resolution"
               and item["reason"] == "followup_question_preserves_active_check_task"
               for item in observation.validation_diagnostics)
    updated = DialogueManager().advance(state, text, "followup",
        observation=observation, unknown_facts=list(unknown))
    assert updated.task_id == "task:1"
    assert updated.operation == "diagnose"
    assert updated.task_context.shown_units == state.task_context.shown_units


@pytest.mark.parametrize("prefix", ["Мы не используем", "Возможно, это"])
def test_model_pair_extraction_rejects_negated_or_uncertain_mentions(prefix):
    text = f"{prefix} Эвотор 7.3."
    raw = payload(text, kind="diagnosis", relation="new_task", intent="device",
                  operation="diagnose", obj=None)
    _, _, _, obs = validate_response(raw, text, "model-negative")
    assert "equipment" not in obs.entities


def test_understanding_is_applied_once_from_sqlite_event(tmp_path):
    text = "Эвотор не передает чеки"
    data = payload(text, entities=[("manufacturer", "Эвотор", "Эвотор")], symptom="не передает чеки",
        operation_quote="не передает чеки", goal="не передает чеки")
    kind, specialist, unknown, obs = validate_response(data, text, "current")
    understanding = Understanding(kind, specialist, unknown, obs,
        {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}, "openai/gpt-oss-20b", 42)
    store = ConversationStore(tmp_path / "test.sqlite3")
    cid = store.new(123, 456)
    mid = store.begin(cid, text, semantic_mode=True, understanding=understanding_to_dict(understanding))
    first = store.dialogue_state(cid)
    second = store.dialogue_state(cid)
    assert first.revision == second.revision == 1
    assert first.entity("manufacturer") == "Эвотор"
    rows = store.history(cid)
    assert rows[-1]["semantic_mode"] and rows[-1]["understanding"]["request_type"] == "diagnosis"
    assert mid > 0


def test_greeting_and_specialist_do_not_call_retrieval():
    class NoSearchRag:
        retriever = None
        def search_for_state(self, *_args): raise AssertionError("retrieval must not run")
    settings = get_settings()
    service = SourceFirstService(NoSearchRag(), settings, Path(__file__).resolve().parents[1])
    async def run():
      for text, kind, specialist, scenario in (
        ("Привет", "greeting", False, "answer"),
        ("Позови специалиста", "escalation", True, "escalate"),
      ):
        summary = {"request_type": kind, "specialist_requested": specialist,
                   "unknown_facts": [], "tokens": {}, "model": settings.groq_model, "duration_ms": 2}
        history = [{"role": "user", "content": text, "semantic_mode": True,
                    "understanding": summary}]
        answer = await service.answer(text, state=DialogueState(), history=history)
        assert answer.scenario == scenario
        if specialist:
            assert "доставка сотруднику" in answer.text
    asyncio.run(run())


def test_information_turn_reaches_retrieval_instead_of_diagnostic_gate(tmp_path):
    text = "Что такое ОФД?"
    raw = payload(text, kind="information", intent="general", operation="explain", obj="понятие",
        intent_quote=text, operation_quote=text, object_quote="ОФД", relation="new_task", relation_quote=text,
        goal=text)
    kind, specialist, unknown, obs = validate_response(raw, text, "current")
    record = Understanding(kind, specialist, unknown, obs, {}, "test", 1)
    store = ConversationStore(tmp_path / "information.sqlite3")
    cid = store.new(7, 8)
    store.begin(cid, text, semantic_mode=True, understanding=understanding_to_dict(record))
    state, history = store.dialogue_state(cid), store.history(cid)

    class SearchCalledRag:
        retriever = None
        calls = 0
        def search_for_state(self, *_args):
            self.calls += 1
            raise RuntimeError("read-only integration probe")
    rag = SearchCalledRag()
    answer = asyncio.run(SourceFirstService(rag, get_settings(),
        Path(__file__).resolve().parents[1]).answer(text, state=state, history=history))
    assert state.intent == "general" and state.operation == "explain"
    assert rag.calls == 1 and answer.generation_error["stage"] == "qdrant_search"


def test_unknown_model_does_not_trigger_same_scope_question_again():
    from types import SimpleNamespace
    class RejectedRetrieval:
        def diagnostics(self): return {"selected": []}
        documents = []
        sufficient = False
        evidence_status = "insufficient"
        insufficiency_reason = "applicability_model_unconfirmed"
        rejected = [SimpleNamespace(reasons=["applicability_model_unconfirmed"])]
    class Rag:
        retriever = None
        def search_for_state(self, *_args): return RejectedRetrieval()
    state = DialogueState(task_id="task:model", intent="fiscal_drive", operation="check")
    state.task_context.unknown_facts = ["equipment"]
    text = "Не знаю точную модель кассы."
    history = [{"role":"user", "content":text, "semantic_mode":True,
        "understanding":{"request_type":"diagnosis", "specialist_requested":False,
        "unknown_facts":["equipment"], "tokens":{}, "model":"test", "duration_ms":1,
        "observation":{"symptom":None,"goals":[],"entities":{}}}}]
    answer = asyncio.run(SourceFirstService(Rag(), get_settings(),
        Path(__file__).resolve().parents[1]).answer(text, state=state, history=history))
    assert answer.scenario == "escalate"
    assert answer.scenario_reason == "insufficient_applicable_evidence"


def test_corrupt_persisted_semantics_fail_closed_without_lexical_fallback(tmp_path):
    import json
    from datetime import datetime, timezone
    class NeverLexical:
        def analyze(self, *_args): raise AssertionError("must not reinterpret failed semantic event")
    store = ConversationStore(tmp_path / "corrupt.sqlite3", manager=DialogueManager(NeverLexical()))
    cid = store.new(3, 4)
    with store.connect() as db:
        db.execute("INSERT INTO messages(conversation_id,role,content,created_at,diagnostics_json) "
                   "VALUES(?,?,?,?,?)", (cid, "user", "Позови специалиста", datetime.now(timezone.utc).isoformat(),
                   json.dumps({"semantic_mode": True, "understanding": {"observation": {"entities": {}}}})))
    state = store.dialogue_state(cid)
    assert state.task_id is None
    assert store.history(cid)[-1]["understanding_error"]["type"] == "persisted_semantic_validation"
