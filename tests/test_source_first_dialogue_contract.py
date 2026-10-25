from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.dialogue_state import DialogueManager, DialogueState
from app.llm_client import Generation
from app.rag import SearchResult
from app.retrieval_pipeline import EvaluatedDocument, Relevance, RetrievalResult
from app.source_first_service import SourceFirstService, _sections, _source_sections
from app.dialogue_understanding import validate_response


ROOT = Path(__file__).resolve().parents[1]


def settings(tmp_path):
    return Settings(telegram_bot_token="", openrouter_api_key="", openrouter_model="model",
                    app_name="test", app_url="http://localhost", show_sources=True,
                    docs_dir=tmp_path, llm_provider="groq", groq_api_key="test",
                    groq_model="openai/gpt-oss-20b", rag_engine="source_first")


class NoSearch:
    def search_for_state(self, *_args):
        raise AssertionError("incomplete task must be clarified before retrieval")


class BrokenQdrant:
    def search_for_state(self, *_args):
        raise ConnectionError("simulated read failure")


def _retrieval(source, doc_id, section, scope, text):
    metadata = {"source": source, "document_id": doc_id, "section": section,
                "status": "approved", **scope}
    hit = SearchResult(source, text, .9, .8, 1.0, metadata)
    selected = EvaluatedDocument(source, doc_id, "approved", metadata, {},
                                 Relevance("service", "task", .9), selected=True)
    return RetrievalResult("query", [selected], [], [hit], True, None, text,
                           evidence_status="source_confirmed")


class OneResult:
    def __init__(self, retrieval):
        self.retriever = SimpleNamespace(store=SimpleNamespace(collection="test"))
        self.retrieval = retrieval

    def search_for_state(self, _state, _query):
        return self.retrieval


def test_incomplete_topic_with_domain_word_is_clarified_without_escalation(tmp_path):
    message = "Привет! Помоги с ОФД"
    state = DialogueManager().advance(DialogueState(), message, 1)
    answer = asyncio.run(SourceFirstService(NoSearch(), settings(tmp_path), ROOT).answer(message, state=state))
    assert answer.scenario == "clarify"
    assert answer.scenario_reason == "dialogue_state_task_incomplete"
    assert answer.clarification_slot == "task"


def test_independent_underspecified_paraphrase_is_clarified(tmp_path):
    message = "Подскажите по кассе"
    state = DialogueManager().advance(DialogueState(), message, 1)
    answer = asyncio.run(SourceFirstService(NoSearch(), settings(tmp_path), ROOT).answer(message, state=state))
    assert answer.scenario == "clarify"
    assert answer.scenario_reason == "dialogue_state_task_incomplete"


def test_repeated_unresolved_task_clarification_stops_loop(tmp_path):
    message = "Помоги с ОФД"
    state = DialogueManager().advance(DialogueState(), message, 1)
    history = [
        {"role": "assistant", "scenario": "clarify", "scenario_reason": "dialogue_state_task_incomplete"},
        {"role": "assistant", "scenario": "clarify", "scenario_reason": "dialogue_state_task_incomplete"},
        {"role": "user", "text": message},
    ]
    answer = asyncio.run(SourceFirstService(NoSearch(), settings(tmp_path), ROOT)
                         .answer(message, state=state, history=history))
    assert answer.scenario == "escalate"
    assert answer.scenario_reason == "dialogue_task_remains_undefined"


def test_qdrant_failure_fails_closed_without_calling_planner(monkeypatch, tmp_path):
    async def unexpected_planner(*_args):
        raise AssertionError("LLM must not run when retrieval failed")

    monkeypatch.setattr("app.source_first_service.generate", unexpected_planner)
    message = "Проверьте передачу чеков в aQsi Online"
    state = DialogueManager().advance(DialogueState(), message, 1)
    answer = asyncio.run(SourceFirstService(BrokenQdrant(), settings(tmp_path), ROOT)
                         .answer(message, state=state))
    assert answer.scenario == "escalate"
    assert answer.scenario_reason == "retrieval_error"
    assert answer.generation_status == "error"


def test_high_risk_action_is_escalated_before_retrieval_or_planner(monkeypatch, tmp_path):
    async def unexpected_planner(*_args):
        raise AssertionError("LLM must not run for a blocked high-risk action")

    monkeypatch.setattr("app.source_first_service.generate", unexpected_planner)
    message = "Закройте архив ФН"
    state = DialogueManager().advance(DialogueState(), message, 1)
    answer = asyncio.run(SourceFirstService(NoSearch(), settings(tmp_path), ROOT)
                         .answer(message, state=state))
    assert answer.scenario == "escalate"
    assert answer.scenario_reason == "unsafe_operation"


def test_approved_source_integrity_accepts_v12b_metadata_projection():
    path = ROOT / "data/knowledge/atol_online/ofd/what-is-ofd.md"
    doc_id = "atol-online-11256-what-is-ofd"
    content = "Что такое ОФД и почему без него касса не передаёт чеки в ФНС?"
    # V1.2-B collection retains the reviewed operation and raw category from
    # approved front matter, so the normalized local and indexed scopes agree.
    metadata = {"source": "atol_online/ofd/what-is-ofd.md", "document_id": doc_id,
                "section": "Вопрос пользователя", "status": "approved",
                "service": "АТОЛ Онлайн", "task_category": "ofd_connection",
                "operations": ["explain_ofd"], "manufacturer": "АТОЛ",
                "model": "АТОЛ Онлайн — облачная ККТ"}
    retrieval = _retrieval("atol_online/ofd/what-is-ofd.md", doc_id,
                           "Вопрос пользователя", {k: v for k, v in metadata.items()
                                                   if k not in {"source", "document_id", "section"}}, content)
    rag = SimpleNamespace()
    sections = _source_sections(rag, retrieval, ROOT)
    assert len(sections) == 1
    assert sections[0]["document_id"] == doc_id
    assert sections[0]["scope"]["task_category"] == "ofd_connection"


def test_stage2_stale_operation_fails_closed_against_approved_front_matter():
    source = "atol_online/ofd/what-is-ofd.md"
    doc_id, heading = "atol-online-11256-what-is-ofd", "Вопрос пользователя"
    metadata = {"service": "АТОЛ Онлайн", "task_category": "receipt_transmission",
                "operations": ["check_transmission"], "manufacturer": "АТОЛ",
                "model": "АТОЛ Онлайн — облачная ККТ"}
    retrieval = _retrieval(source, doc_id, heading, metadata,
                           "Что такое ОФД и почему без него касса не передаёт чеки в ФНС?")
    assert _source_sections(SimpleNamespace(), retrieval, ROOT) == []


def test_selected_document_exposes_its_exact_retrieved_information_sections():
    source = "atol_online/ofd/what-is-ofd.md"
    doc_id = "atol-online-11256-what-is-ofd"
    raw = (ROOT / "data/knowledge" / source).read_text(encoding="utf-8").split("---", 2)[2].strip()
    chunks = _sections(raw)
    metadata = {"source": source, "document_id": doc_id, "status": "approved",
                "service": "АТОЛ Онлайн", "task_category": "ofd_connection",
                "operations": ["explain_ofd"], "manufacturer": "АТОЛ",
                "model": "АТОЛ Онлайн — облачная ККТ"}
    hits = [SearchResult(source, body, .9 if heading == "Вопрос пользователя" else 0,
                         metadata={**metadata, "section": heading}) for heading, body in chunks]
    selected = EvaluatedDocument(source, doc_id, "approved", {**metadata, "section": "Вопрос пользователя"}, {},
                                 Relevance("service", "task", .9), selected=True)
    retrieval = RetrievalResult("query", [selected], [], hits, True, None, "", evidence_status="source_confirmed")
    verified = _source_sections(SimpleNamespace(), retrieval, ROOT)
    assert [item["section"] for item in verified] == [heading for heading, _ in chunks]
    assert "получает фискальные документы" in verified[1]["text"]


def test_definition_uses_scoped_material_with_explicit_attribution(monkeypatch, tmp_path):
    path = "atol_online/ofd/what-is-ofd.md"
    doc_id, heading = "atol-online-11256-what-is-ofd", "Вопрос пользователя"
    content = "Что такое ОФД и почему без него касса не передаёт чеки в ФНС?"
    scope = {"service": "АТОЛ Онлайн", "task_category": "ofd_connection",
             "operations": ["explain_ofd"], "manufacturer": "АТОЛ",
             "model": "АТОЛ Онлайн — облачная ККТ"}
    raw = (ROOT / "data/knowledge" / path).read_text(encoding="utf-8").split("---", 2)[2].strip()
    hits = [SearchResult(path, body, .9 if title == heading else 0,
                         metadata={"source": path, "document_id": doc_id, "section": title,
                                   "status": "approved", **scope})
            for title, body in _sections(raw)]
    selected_candidate = EvaluatedDocument(path, doc_id, "approved",
        {"source": path, "document_id": doc_id, "section": heading, "status": "approved", **scope}, {},
        Relevance("service", "task", .9), selected=True)
    retrieval = RetrievalResult("query", [selected_candidate], [], hits, True, None, "",
                                evidence_status="source_confirmed")

    async def planner(messages, _settings):
        import json
        data = json.loads(messages[1]["content"])
        candidate = next(x for x in data["candidate_sections"]
                         if x["section"] == "Что проверено по инструкции производителя")
        return Generation('{"mode":"select","section_id":"' + candidate["id"] +
                          '","applicability_confirmed":true,"order_confirmed":true,"reason":"definition"}',
                          "openai/gpt-oss-20b")

    monkeypatch.setattr("app.source_first_service.generate", planner)
    message = "Что такое ОФД?"
    state = DialogueManager().advance(DialogueState(), message, 1)
    answer = asyncio.run(SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT)
                         .answer(message, state=state))
    assert answer.scenario == "answer"
    assert "По документации для области" in answer.text
    assert "АТОЛ Онлайн" in answer.text
    assert "получает фискальные документы" in answer.text
    assert "Область применения — облачные кассы АТОЛ Онлайн" in answer.text


def test_vendor_scoped_procedure_requests_service_before_planner(monkeypatch, tmp_path):
    path = "evotor/ofd/ofd-subscription.md"
    doc_id, heading = "evotor-ofd-subscription-8865646794770", "Возможная причина"
    content = "Одна из причин отсутствия передачи — завершившийся оплаченный период обслуживания оператора."
    scope = {"service": "Эвотор", "task_category": "receipt_transmission",
             "operations": ["check_transmission"], "manufacturer": "Эвотор", "model": None}
    retrieval = _retrieval(path, doc_id, heading, scope, content)

    async def unexpected_planner(*_args):
        raise AssertionError("planner must not convert unknown service into confirmed applicability")

    monkeypatch.setattr("app.source_first_service.generate", unexpected_planner)
    message = "ОФД как проверить срок"
    state = DialogueManager().advance(DialogueState(), message, 1)
    answer = asyncio.run(SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT)
                         .answer(message, state=state))
    assert answer.scenario == "clarify"
    assert answer.scenario_reason == "source_scope_context_missing"
    assert answer.clarification_slot == "service"
    assert "какой сервис" in answer.text.lower() or "какой сервис" in answer.text.lower()


def test_rejected_entity_cannot_satisfy_vendor_scope_gate(monkeypatch, tmp_path):
    path = "evotor/ofd/ofd-subscription.md"
    doc_id, heading = "evotor-ofd-subscription-8865646794770", "Возможная причина"
    content = "Проверьте срок обслуживания оператора по инструкции Эвотор."
    scope = {"service": "Эвотор", "task_category": "receipt_transmission",
             "operations": ["check_transmission"], "manufacturer": "Эвотор", "model": None}
    retrieval = _retrieval(path, doc_id, heading, scope, content)
    text = "Не передаются чеки."
    output = {"request_type": "diagnosis", "relation": "new_task", "intent": "receipt",
        "operation": "transmit", "object": "чек", "object_evidence": {"quote": "чеки"},
        "goal": None, "symptom": {"quote": "Не передаются чеки"},
        "entities": [{"slot": "manufacturer", "value": "Эвотор",
                      "evidence": {"quote": "чеки"}}], "unknown_facts": [],
        "specialist_requested": False, "specialist_evidence": None, "confidence": .9}
    _, _, _, observation = validate_response(output, text, 1)
    assert not observation.entities

    async def unexpected_planner(*_args):
        raise AssertionError("unknown service must be clarified before planning")
    monkeypatch.setattr("app.source_first_service.generate", unexpected_planner)
    answer = asyncio.run(SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT)
                         .answer(text, state=DialogueManager().advance(
                             DialogueState(), text, 1, observation=observation)))
    assert answer.scenario == "clarify"
    assert answer.scenario_reason == "source_scope_context_missing"
    assert answer.clarification_slot in {"service", "manufacturer"}
