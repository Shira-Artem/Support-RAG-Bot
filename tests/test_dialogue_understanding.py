from dataclasses import replace
import asyncio
from pathlib import Path

import pytest

from app.config import get_settings
from app.conversation_store import ConversationStore
from app.dialogue_state import DialogueManager, DialogueState, ExpectedClarification
from app.dialogue_understanding import (Understanding, UnderstandingError, response_schema,
    understand_message, understanding_to_dict, validate_response)
from app.source_first_service import SourceFirstService


def payload(text, *, kind="diagnosis", relation="new_task", intent="receipt", operation="diagnose",
            obj="чек", entities=(), unknown=(), specialist=False, specialist_quote=None,
            intent_quote=None, operation_quote=None, object_quote=None, relation_quote=None,
            goal=None, symptom=None, unknown_quote=None):
    return {"request_type": kind, "relation": relation, "intent": intent, "operation": operation,
        "object": obj, "object_evidence": {"quote": object_quote or text} if obj is not None else None,
        "goal": {"quote": goal} if goal else None,
        "symptom": {"quote": symptom} if symptom else None,
        "entities": [{"slot": slot, "value": value, "evidence": {"quote": quote}}
                     for slot, value, quote in entities],
        "unknown_facts": [{"slot": slot, "evidence": {"quote": unknown_quote or text}}
                          for slot in unknown], "specialist_requested": specialist,
        "specialist_evidence": {"quote": specialist_quote} if specialist_quote else None,
        "confidence": .91}


def classify(text, **kwargs):
    return validate_response(payload(text, **kwargs), text, 77)


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
    assert not obs.entities and obs.intent == "general" and obs.operation == "explain"


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


def test_common_semantic_label_aliases_are_canonicalized_locally():
    text = "Что такое ОФД?"
    data = payload(text, kind="information_request", intent="definition", operation="explanation",
        obj="ОФД", object_quote="ОФД", relation="new_topic")
    kind, _, _, obs = validate_response(data, text, 77)
    assert kind == "information" and obs.intent == "general" and obs.operation == "explain"
    assert obs.relation == "new_task" and obs.object is None
    assert {item["field"]: item["reason"] for item in obs.validation_diagnostics}["request_type"] == "normalized_turn_type_alias"


def test_schema_has_semantic_labels_without_evidence_properties():
    fields = response_schema()["schema"]["properties"]
    assert "intent_evidence" not in fields
    assert "operation_evidence" not in fields
    assert "relation_evidence" not in fields
    assert fields["unknown_facts"]["items"]["properties"]["evidence"]["type"] == "object"
    assert "enum" not in fields["object"]
    assert "enum" not in fields["intent"]
    assert response_schema()["strict"] is True


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
