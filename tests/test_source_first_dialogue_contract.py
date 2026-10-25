from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.dialogue_state import DialogueManager, DialogueState
from app.llm_client import Generation
from app.rag import SearchResult
from app.retrieval_pipeline import EvaluatedDocument, Relevance, RetrievalResult
from app.source_first_service import (SourceFirstService, _sections, _source_sections,
                                     _judge_information_relevance,
                                     _parse_information_relevance_judgment,
                                     _validate_information_composition)
from app.dialogue_understanding import validate_response
from app.response_grounding import content_terms


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
    source = "data/knowledge/atol_online/ofd/what-is-ofd.md"
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
        if "candidate_answer" in data:
            return Generation(json.dumps({
                "verdict": "relevant",
                "answers_current_question": True,
                "supporting_evidence_quote": (
                    "ОФД получает фискальные документы от зарегистрированной ККТ, "
                    "обрабатывает и передаёт их в ФНС в предусмотренном формате.")
            }, ensure_ascii=False), "offline-judge")
        if "candidate_sections" not in data:
            return Generation("ОФД получает и обрабатывает фискальные документы от ККТ, а затем передаёт их в ФНС.",
                              "openai/gpt-oss-20b", 80, 35, 115)
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
    assert "фискальные документы" in answer.text
    assert "Область применения — облачные кассы АТОЛ Онлайн" not in answer.text
    assert "действующий тариф" not in answer.text and "текущую очередь" not in answer.text


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


def test_information_followup_gets_grounded_answer_for_current_question(monkeypatch, tmp_path):
    import hashlib
    import json
    from app.llm_client import Generation
    from app.dialogue_understanding import validate_response

    source = "data/knowledge/atol_online/ofd/what-is-ofd.md"
    doc_id = "atol-online-11256-what-is-ofd"
    path = ROOT / source
    body = path.read_text(encoding="utf-8").split("---", 2)[2].strip()
    local_sections = {heading: text for heading, text in _sections(body)}
    scope = {"service": "АТОЛ Онлайн", "task_category": "ofd_connection",
             "operations": ["explain_ofd"], "manufacturer": "АТОЛ",
             "model": "АТОЛ Онлайн — облачная ККТ"}
    candidate_sections = [{"id": f"{doc_id}::{heading}", "document_id": doc_id,
        "section": heading, "text": local_sections[heading],
        "title": "Для чего АТОЛ Онлайн нужен оператор фискальных данных", "source": source,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "scope": scope,
        "qdrant_scope": scope}
        for heading in ("Вопрос пользователя", "Что проверено по инструкции производителя",
                        "Важное ограничение / передача специалисту")]
    monkeypatch.setattr("app.source_first_service._source_sections", lambda *_args: candidate_sections)
    monkeypatch.setattr("app.source_first_service._append_composer_rejection", lambda *_args: None)
    retrieval = _retrieval(source, doc_id, "Вопрос пользователя", scope,
                           local_sections["Вопрос пользователя"])
    first_text = "Что такое ОФД?"
    first_raw = {"request_type": "question", "relation": "new_task", "intent": "information",
        "operation": "lookup", "object": "OFD", "object_evidence": {"quote": "ОФД"},
        "goal": {"quote": first_text}, "symptom": None, "entities": [], "unknown_facts": [],
        "specialist_requested": False, "specialist_evidence": None, "confidence": .9}
    _, _, _, first_observation = validate_response(first_raw, first_text, 1)
    manager = DialogueManager()
    first_state = manager.advance(DialogueState(), first_text, 1, observation=first_observation)
    seen = {"calls": 0, "planner_sections": [], "questions": [], "repair_questions": []}

    async def generate_stub(messages, _settings):
        payload = json.loads(messages[-1]["content"])
        seen["calls"] += 1
        if "candidate_sections" in payload:
            planner_prompt = messages[0]["content"]
            assert "Для чистого general/explain без шагов" in planner_prompt
            assert "техническими действиями" in planner_prompt
            seen["planner_sections"].append([item["section"] for item in payload["candidate_sections"]])
            chosen = next(item for item in payload["candidate_sections"]
                          if item["section"] == "Что проверено по инструкции производителя")
            content = json.dumps({"mode": "select", "section_id": chosen["id"],
                "applicability_confirmed": False, "order_confirmed": False,
                "reason": "general explanation; no customer-specific procedure"})
        elif "rejected_claims" in payload:
            seen["repair_questions"].append(payload["current_question"])
            assert len(payload["rejected_claims"]) == 1
            assert payload["exact_approved_evidence"] == local_sections[
                "Что проверено по инструкции производителя"]
            assert "тариф" not in json.dumps(payload["rejected_claims"], ensure_ascii=False)
            content = ("ОФД — оператор фискальных данных. Он получает фискальные документы от "
                       "зарегистрированной ККТ, обрабатывает и передаёт их в ФНС в предусмотренном формате."
                       if payload["current_question"] == first_text else
                       "ОФД нужен кассе для передачи фискальных документов в ФНС: он получает их от "
                       "зарегистрированной ККТ, обрабатывает и передаёт в предусмотренном формате.")
        elif "candidate_answer" in payload:
            seen.setdefault("relevance_questions", []).append(payload["current_question"])
            assert payload["active_task"]["object"] == "ОФД"
            assert payload["selected_approved_source_title"] == \
                "Для чего АТОЛ Онлайн нужен оператор фискальных данных"
            assert payload["exact_selected_approved_evidence"].find(
                "ОФД получает фискальные документы от зарегистрированной ККТ") >= 0
            content = json.dumps({
                "verdict": "relevant",
                "answers_current_question": True,
                "supporting_evidence_quote": (
                    "ОФД получает фискальные документы от зарегистрированной ККТ, "
                    "обрабатывает и передаёт их в ФНС в предусмотренном формате.")
            }, ensure_ascii=False)
        else:
            question = payload["current_question"]
            seen["questions"].append(question)
            content = ("ОФД – оператор фискальных данных, который получает фискальные документы от "
                       "зарегистрированной ККТ, обрабатывает их и передаёт в ФНС в предусмотренном формате."
                       if question == first_text else
                       "ОФД нужен для того, чтобы получать фискальные документы от зарегистрированной ККТ, "
                       "обрабатывать их и передавать в ФНС в предусмотренном формате.")
        return Generation(content, "test-model", 100, 60, 160)

    monkeypatch.setattr("app.source_first_service.generate", generate_stub)
    service = SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT)
    first_answer = asyncio.run(service.answer(first_text, state=first_state))

    followup = "А зачем он нужен кассе?"
    followup_raw = {"request_type": "information", "relation": "continuation", "intent": "general",
        "operation": "explain", "object": "ОФД", "object_evidence": {"quote": "он"},
        "goal": {"quote": followup}, "symptom": None, "entities": [], "unknown_facts": [],
        "specialist_requested": False, "specialist_evidence": None, "confidence": .9}
    _, _, _, followup_observation = validate_response(followup_raw, followup, 2)
    followup_state = manager.advance(first_state, followup, 2, observation=followup_observation)
    followup_answer = asyncio.run(service.answer(followup, state=followup_state,
        history=[{"role": "user", "content": first_text},
                 {"role": "assistant", "content": first_answer.text}]))

    assert all("Вопрос пользователя" not in sections for sections in seen["planner_sections"])
    assert all("Что проверено по инструкции производителя" in sections
               for sections in seen["planner_sections"])
    assert followup_state.task_id == first_state.task_id and followup_state.object == "ОФД"
    assert first_answer.scenario_reason == "source_first_grounded_information_summary"
    assert followup_answer.scenario_reason == "source_first_grounded_information_summary"
    assert followup_answer.retrieval_diagnostics["planner"]["selection_policy"] == \
        "informational_selected_section_claim_validation"
    assert followup_answer.text != first_answer.text
    assert "нужен кассе для передачи фискальных документов" in followup_answer.text
    assert "тариф" not in followup_answer.text and "очередь передачи" not in followup_answer.text
    assert seen["questions"] == [first_text, followup]
    assert seen["repair_questions"] == [first_text, followup]
    assert seen["relevance_questions"] == [first_text, followup]
    assert seen["calls"] == 8
    for answer in (first_answer, followup_answer):
        diagnostics = answer.retrieval_diagnostics["answer_composer"]
        assert diagnostics["initial_check"]["validation"] == "rejected"
        assert diagnostics["initial_check"]["reason"] == "unsupported_information_claim"
        assert diagnostics["repair"]["attempted"] is True
        assert diagnostics["repair"]["validation"] == "accepted"
        assert diagnostics["relevance_check"]["verdict"] == "relevant"


def test_information_composition_rejects_unsupported_claims_and_procedures():
    source = ROOT / "data/knowledge/atol_online/ofd/what-is-ofd.md"
    body = source.read_text(encoding="utf-8").split("---", 2)[2].strip()
    evidence = dict(_sections(body))["Что проверено по инструкции производителя"]
    grounded = ("ОФД нужен кассе как посредник при передаче фискальных документов в ФНС: "
                "он получает их от ККТ, обрабатывает и передаёт дальше.")
    accepted, reason = _validate_information_composition(
        grounded, evidence, "Что проверено по инструкции производителя")
    assert accepted == grounded and reason == "all_sentences_supported_by_selected_section"

    unsupported, reason = _validate_information_composition(
        "ОФД автоматически продлевает тариф кассы.", evidence,
        "Что проверено по инструкции производителя")
    assert unsupported is None and reason == "unsupported_information_claim"

    procedural, reason = _validate_information_composition(
        "Проверьте статус ККТ в ОФД и текущую очередь передачи.", evidence,
        "Что проверено по инструкции производителя")
    assert procedural is None and reason == "procedural_or_interface_content_in_information_answer"

    repeated, reason = _validate_information_composition(
        "ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает их и передаёт в ФНС.",
        evidence, "Что проверено по инструкции производителя")
    assert repeated and reason == "all_sentences_supported_by_selected_section"


def test_semantic_relevance_replays_saved_composer_answer_with_current_task_and_source(monkeypatch, tmp_path):
    import asyncio
    import hashlib
    import json
    from app.llm_client import Generation

    source = ROOT / "data/knowledge/atol_online/ofd/what-is-ofd.md"
    body = source.read_text(encoding="utf-8").split("---", 2)[2].strip()
    section = "Что проверено по инструкции производителя"
    selected_body = dict(_sections(body))[section]
    title = "Для чего АТОЛ Онлайн нужен оператор фискальных данных"
    evidence = "\n".join((title, section, selected_body))
    question = "А зачем он нужен кассе?"
    saved_composer_output = (
        "ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает их и "
        "передаёт в ФНС в предусмотренном формате.")
    supported, before_semantic_gate = _validate_information_composition(
        saved_composer_output, evidence, section)
    assert supported == saved_composer_output
    assert before_semantic_gate == "all_sentences_supported_by_selected_section"
    assert not (content_terms(question) & content_terms(saved_composer_output))

    state = {"intent": "general", "operation": "explain", "object": "ОФД",
             "task": {"value": "Что такое ОФД?"},
             "goals": [{"value": question}]}
    seen = {}

    async def relevant_stub(messages, _settings):
        payload = json.loads(messages[-1]["content"])
        seen.update(payload)
        seen["system_prompt"] = messages[0]["content"]
        return Generation(json.dumps({
            "verdict": "relevant",
            "answers_current_question": True,
            "supporting_evidence_quote": (
                "ОФД получает фискальные документы от зарегистрированной ККТ, "
                "обрабатывает и передаёт их в ФНС в предусмотренном формате.")
        }, ensure_ascii=False), "offline-judge")

    monkeypatch.setattr("app.source_first_service.generate", relevant_stub)
    accepted, reason, diagnostics, _ = asyncio.run(_judge_information_relevance(
        supported, question, state, title, section, evidence, settings(tmp_path)))
    assert accepted and reason == "semantic_relevance_accepted"
    assert diagnostics["quote_present_in_selected_approved_evidence"] is True
    assert seen["current_question"] == question
    assert seen["active_task"] == state
    assert seen["exact_selected_approved_evidence"] == evidence
    assert "Одного совпадения слов недостаточно" in seen["system_prompt"]


def test_semantic_relevance_rejects_definition_and_other_fact_from_same_article(monkeypatch, tmp_path):
    import asyncio
    import json
    from app.llm_client import Generation

    source = ROOT / "data/knowledge/atol_online/ofd/what-is-ofd.md"
    body = source.read_text(encoding="utf-8").split("---", 2)[2].strip()
    section = "Что проверено по инструкции производителя"
    selected_body = dict(_sections(body))[section]
    title = "Для чего АТОЛ Онлайн нужен оператор фискальных данных"
    evidence = "\n".join((title, section, selected_body))
    question = "А зачем он нужен кассе?"
    candidates = (
        "ОФД — оператор фискальных данных.",
        "Для обычных сценариев облачной кассы требуется корректно оформленный договор и действующий тариф ОФД.",
    )
    judgments = (
        {"verdict": "irrelevant", "answers_current_question": False,
         "supporting_evidence_quote": ""},
        {"verdict": "irrelevant", "answers_current_question": False,
         "supporting_evidence_quote": ""},
    )
    for candidate, judgment in zip(candidates, judgments):
        grounded, _ = _validate_information_composition(candidate, evidence, section)
        assert grounded == candidate  # Same article alone does not make it responsive.

        async def judge_stub(messages, _settings, judgment=judgment):
            return Generation(json.dumps(judgment, ensure_ascii=False), "offline-judge")

        monkeypatch.setattr("app.source_first_service.generate", judge_stub)
        accepted, reason, diagnostics, _ = asyncio.run(_judge_information_relevance(
            candidate, question, {"object": "ОФД", "operation": "explain"},
            title, section, evidence, settings(tmp_path)))
        assert not accepted
        assert reason == "answer_does_not_address_current_question_semantically"
        assert diagnostics["verdict"] == "irrelevant"


def test_relevance_judgment_quote_must_be_in_selected_source_and_existing_gates_still_block(monkeypatch):
    import json
    source = "ОФД получает документы от ККТ и передает их в ФНС."
    accepted, reason, _ = _parse_information_relevance_judgment(json.dumps({
        "verdict": "relevant", "answers_current_question": True,
        "supporting_evidence_quote": "ОФД возвращает кассе комиссию"
    }, ensure_ascii=False), source)
    assert not accepted and reason == "relevance_quote_not_in_selected_approved_evidence"

    grounded, reason = _validate_information_composition(
        "ОФД автоматически возвращает комиссию кассе.", source, "Что проверено")
    assert grounded is None and reason == "unsupported_information_claim"
    procedural, reason = _validate_information_composition(
        "Проверьте статус ККТ в ОФД и текущую очередь передачи.",
        "При отсутствии чеков в налоговой стоит отдельно проверить статус ККТ в ОФД "
        "и текущую очередь передачи.", "Что проверить")
    assert procedural is None and reason == "procedural_or_interface_content_in_information_answer"


def test_information_composer_repair_rejects_fabricated_claim(monkeypatch, tmp_path):
    import hashlib
    import json
    from app.llm_client import Generation
    from app.dialogue_understanding import validate_response

    source = "data/knowledge/atol_online/ofd/what-is-ofd.md"
    doc_id = "atol-online-11256-what-is-ofd"
    path = ROOT / source
    body = path.read_text(encoding="utf-8").split("---", 2)[2].strip()
    sections = {heading: text for heading, text in _sections(body)}
    scope = {"service": "АТОЛ Онлайн", "task_category": "ofd_connection",
             "operations": ["explain_ofd"], "manufacturer": "АТОЛ",
             "model": "АТОЛ Онлайн — облачная ККТ"}
    candidates = [{"id": f"{doc_id}::{heading}", "document_id": doc_id,
        "section": heading, "text": sections[heading],
        "title": "Для чего АТОЛ Онлайн нужен оператор фискальных данных", "source": source,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "scope": scope, "qdrant_scope": scope}
        for heading in ("Вопрос пользователя", "Что проверено по инструкции производителя",
                        "Важное ограничение / передача специалисту")]
    monkeypatch.setattr("app.source_first_service._source_sections", lambda *_args: candidates)
    monkeypatch.setattr("app.source_first_service._append_composer_rejection", lambda *_args: None)
    retrieval = _retrieval(source, doc_id, "Вопрос пользователя", scope,
                           sections["Вопрос пользователя"])
    question = "А зачем он нужен кассе?"
    raw = {"request_type": "information", "relation": "new_task", "intent": "general",
        "operation": "explain", "object": "ОФД", "object_evidence": {"quote": "ОФД"},
        "goal": {"quote": question}, "symptom": None, "entities": [], "unknown_facts": [],
        "specialist_requested": False, "specialist_evidence": None, "confidence": .9}
    _, _, _, observation = validate_response(raw, question, 1)
    state = DialogueManager().advance(DialogueState(), question, 1, observation=observation)

    async def generate_stub(messages, _settings):
        payload = json.loads(messages[-1]["content"])
        if "candidate_sections" in payload:
            chosen = next(item for item in payload["candidate_sections"]
                          if item["section"] == "Что проверено по инструкции производителя")
            content = json.dumps({"mode": "select", "section_id": chosen["id"],
                "applicability_confirmed": False, "order_confirmed": False,
                "reason": "general explanation"})
        elif "rejected_claims" in payload:
            assert payload["rejected_claims"]
            assert payload["exact_approved_evidence"] == sections[
                "Что проверено по инструкции производителя"]
            content = "ОФД автоматически возвращает комиссию по тарифу."
        else:
            content = ("ОФД нужен для того, чтобы получать фискальные документы от зарегистрированной ККТ, "
                       "обрабатывать их и передавать в ФНС в предусмотренном формате.")
        return Generation(content, "test-model", 10, 10, 20)

    monkeypatch.setattr("app.source_first_service.generate", generate_stub)
    answer = asyncio.run(SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT)
                         .answer(question, state=state))
    assert answer.scenario == "escalate"
    assert answer.scenario_reason == "information_composition_unverified"
    diagnostics = answer.retrieval_diagnostics["answer_composer"]
    assert diagnostics["initial_check"]["reason"] == "unsupported_information_claim"
    assert diagnostics["repair"]["attempted"] is True
    assert diagnostics["repair"]["validation"] == "rejected"
    assert diagnostics["repair"]["reason"] == "unsupported_information_claim"
    assert "автоматически возвращает комиссию" not in answer.text
