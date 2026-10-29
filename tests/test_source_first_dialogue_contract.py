from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.dialogue_state import DialogueManager, DialogueState
from app.dialogue_state import ActiveRoute, Fact, TaskContext
from app.llm_client import Generation
from app.rag import SearchResult
from app.retrieval_pipeline import EvaluatedDocument, Relevance, RetrievalResult
from app.source_first_service import (SourceFirstService, _sections, _source_sections,
                                     _information_evidence_fragments,
                                     _judge_information_relevance,
                                     _parse_information_relevance_judgment,
                                     _partial_information_composition,
                                     _scoped_limitation_matches, _generic_preflight,
                                     _validate_information_composition,
                                     _approved_check_units, _focused_approved_sentence,
                                     _safe_general_knowledge_question,
                                     _comparison_concepts,
                                     _conceptually_answering_sentence,
                                     _read_only_status_fact)
from app.dialogue_understanding import validate_response
from app.response_grounding import content_terms


ROOT = Path(__file__).resolve().parents[1]


def test_scoped_limitation_requires_direct_subject_and_no_procedure():
    state = DialogueState(task_id="task:1", intent="receipt", operation="search", object="чек")
    limitation = {"section": "Ограничения", "text":
        "ФН не подтверждён как прямой фильтр чеков. Отсутствие поля в статье не доказывает отсутствие функции."}
    assert _scoped_limitation_matches(limitation, "Можно найти чек по номеру ФН?", state)
    assert not _scoped_limitation_matches(limitation, "Можно найти чек по номеру ФД?", state)
    assert not _scoped_limitation_matches(limitation, "Как найти чек по номеру фискального документа?", state)
    assert _scoped_limitation_matches(limitation, "Можно найти чек по номеру фискального накопителя?", state)
    unsafe_mixture = {**limitation, "text": limitation["text"] +
        " Откройте настройки кассы и измените порт подключения."}
    assert not _scoped_limitation_matches(unsafe_mixture, "Можно найти чек по номеру ФН?", state)


def test_unlisted_procedure_units_keep_conditions_warnings_and_source_order():
    source_sentences = [
        "Перед печатью убедитесь, что крышка принтера закрыта.",
        "Если на экране показана ошибка, остановитесь и обратитесь к специалисту.",
        "Откройте меню «Диагностика».",
        "Затем выберите «Диагностический отчёт».",
        "Если отчёт не сформирован, не повторяйте продажу и сообщите специалисту.",
    ]
    units = _approved_check_units(" ".join(source_sentences), "source.md", "Порядок проверки")
    assert len(units) == 2
    assert units[0]["line"] == " ".join(source_sentences[:3])
    assert units[1]["line"] == " ".join(source_sentences[3:])
    flattened = " ".join(unit["line"] for unit in units)
    cursor = 0
    for sentence in source_sentences:
        position = flattened.find(sentence, cursor)
        assert position >= cursor
        cursor = position + len(sentence)


def test_unconfirmed_model_limits_partial_answer_to_independent_preflight():
    state = DialogueManager().advance(DialogueState(),
        "У меня Эвотор, чеки не отправляются в ОФД.", 1)
    scope = {"manufacturer": "Эвотор"}
    body = ("1. Выясните модель кассы.\n"
            "2. На модели 7.3 откройте настройки и измените адрес оператора.")
    assert _generic_preflight(body, state, scope) == "1. Выясните модель кассы."
    assert _generic_preflight("1. На модели 7.3 откройте настройки.", state, scope) is None
    assert _generic_preflight("1. Выясните модель и откройте меню настроек.", state, scope) is None


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


def test_broad_explanation_request_is_clarified_before_retrieval(tmp_path):
    message = "Привет! Помоги мне разобраться с кассами."
    state = DialogueState(task_id="task:1", intent="general", operation="explain",
                          object="касса")
    answer = asyncio.run(SourceFirstService(NoSearch(), settings(tmp_path), ROOT).answer(
        message, state=state, history=[{"role": "user", "content": message,
                                       "understanding": {"request_type": "information"},
                                       "semantic_mode": True}]))
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

    async def planner(messages, _settings, *, call_stage="generation"):
        import json
        data = json.loads(messages[1]["content"])
        if "candidate_answer" in data:
            fact = next(item for item in data["approved_evidence_fragments"]
                        if "ОФД получает фискальные документы от зарегистрированной ККТ" in item["text"])
            return Generation(json.dumps({
                "verdict": "relevant",
                "answers_current_question": True,
                "supporting_evidence_ids": [fact["id"]]
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


def test_vendor_scoped_procedure_requests_manufacturer_not_ofd_service(monkeypatch, tmp_path):
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
    assert answer.clarification_slot == "manufacturer"
    assert "производител" in answer.text.lower()
    assert "офд" not in answer.text.lower()


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


def test_error_fact_without_confirmed_manufacturer_is_attributed_and_fact_only(tmp_path):
    source = "evotor/fn/fn-234.md"
    doc_id, heading = "evotor-fn-234-360005580254", "Первое различение причины"
    body = (ROOT / "data/knowledge" / source).read_text(encoding="utf-8").split("---", 2)[2].strip()
    text = dict(_sections(body))[heading]
    scope = {"service": "Эвотор", "task_category": "error_diagnosis",
             "operations": ["diagnose_error"], "manufacturer": "Эвотор", "model": None}
    retrieval = _retrieval(source, doc_id, heading, scope, text)
    question = "На кассе появилась ошибка ФН 234. Что она означает и какие безопасные проверки доступны?"
    state = DialogueState(intent="fiscal_drive", operation="diagnose", object="ФН 234",
                          task=Fact(question, 1, question, 0, len(question)))
    answer = asyncio.run(SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT)
                         .answer(question, state=state,
                             coordinator_decision={"route": "technical_action", "current_subgoal": question}))
    assert answer.scenario == "answer"
    assert answer.clarification_slot is None
    assert "Статья производителя связывает код ФН 234" in answer.text
    assert "Область источника: Эвотор" in answer.text
    assert "модель оборудования не подтверждена" in answer.text.lower()
    assert "Проверьте" not in answer.text and "Настройки →" not in answer.text
    gate = answer.retrieval_diagnostics["source_scope_gate"]
    assert gate["attributed_fact_only"] is True
    assert gate["customer_scope_confirmed"] is False


def test_focus_prefers_supported_fn_fact_over_dangerous_safety_warning():
    source = ROOT / "data/knowledge/evotor/fn/fn-234.md"
    body = source.read_text(encoding="utf-8").split("---", 2)[2].strip()
    sections = [{"section": heading, "text": text, "source": "evotor/fn/fn-234.md"}
                for heading, text in _sections(body)]
    question = "На кассе появилась ошибка ФН 234. Что она означает и какие безопасные проверки доступны?"
    match = _focused_approved_sentence(sections, question)
    assert match is not None
    selected, claim = match
    assert selected["section"] == "Первое различение причины"
    assert claim == "Статья производителя связывает код ФН 234 с ресурсом фискального накопителя."
    from app.response_grounding import unsafe_operation_issue
    dangerous_warning = next(sentence for heading, text in _sections(body)
        if heading == "Если ошибка сохранилась" for sentence in
        __import__("app.response_grounding", fromlist=["statements"]).statements(text)
        if "закрытие архива" in sentence)
    assert unsafe_operation_issue(dangerous_warning) == "закрыть архив ФН"


def test_general_knowledge_fallback_is_limited_to_safe_conceptual_explanations(tmp_path, monkeypatch):
    import json

    source = "atol_online/fn/fn-basics.md"
    path = ROOT / "data/knowledge" / source
    body = path.read_text(encoding="utf-8").split("---", 2)[2].strip()
    heading, text = _sections(body)[0]
    scope = {"task_category": "fiscal_drive", "manufacturer": "АТОЛ",
             "model": "АТОЛ Онлайн — облачная ККТ"}
    retrieval = _retrieval(source, "atol-online-11253-fn-basics", heading, scope, text)
    question = "Привет! Объясни, что такое ОФД и зачем он нужен?"
    state = DialogueState(intent="general", operation="explain", object="ОФД",
                          task=Fact(question, 1, question, 0, len(question)))
    assert _safe_general_knowledge_question(question, state)
    assert _safe_general_knowledge_question(
        "Чем отличается фискальный накопитель от оператора фискальных данных?", state)
    assert _safe_general_knowledge_question("Как работает DNS?", state)
    assert _safe_general_knowledge_question("Для чего нужен API?", state)
    assert not _safe_general_knowledge_question("Как закрыть архив ФН?", state)
    assert not _safe_general_knowledge_question("Как исправить ошибку ФН 234?", state)
    assert not _safe_general_knowledge_question("Как настроить кассу?", state)
    assert not _safe_general_knowledge_question("Что требует закон на сегодня об ОФД?", state)

    async def offline_general(messages, _settings, *, call_stage="generation"):
        assert call_stage == "general_knowledge"
        assert "approved" in messages[0]["content"].lower()
        return Generation("ОФД получает фискальные документы от кассы и передаёт их налоговой службе.",
                          "offline-general-fixture", prompt_tokens=20, completion_tokens=18,
                          total_tokens=38)

    monkeypatch.setattr("app.source_first_service.generate", offline_general)
    answer = asyncio.run(SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT).answer(
        question, state=state, coordinator_decision={"route": "grounded_information",
        "current_subgoal": question}))
    assert answer.scenario == "answer"
    assert answer.scenario_reason == "general_knowledge_fallback"
    assert "не по approved-документации" in answer.text
    assert "Источник:" not in answer.text and "http" not in answer.text.lower()
    assert answer.retrieval_diagnostics["general_knowledge_fallback"]["source_basis"] == "model_general_knowledge"


def test_conceptual_evidence_gate_rejects_action_and_requires_both_comparison_sides():
    question = "Чем отличается фискальный накопитель от оператора фискальных данных?"
    pair = _comparison_concepts(question)
    assert pair and pair[0] and pair[1]
    assert not _conceptually_answering_sentence(
        "Фискальный накопитель — модуль ККТ, обеспечивающий запись фискальных документов.", question)
    assert not _conceptually_answering_sentence(
        "Попросите клиента назвать своего оператора ОФД; сопоставьте сервер и порт.", question)
    assert not _conceptually_answering_sentence(
        "Справка различает счёт на лицензию программы сервиса и счёт на облачную ККТ.",
        "В чём разница между локальной программой и облачным сервисом?")
    assert _conceptually_answering_sentence(
        "Фискальный накопитель записывает документы, а оператор фискальных данных передаёт их в ФНС.",
        question)


def test_conceptual_definition_requires_the_named_subject_not_shared_context_words():
    question = "Объясни простыми словами, что такое ОФД и зачем он нужен кассе?"
    wrong = "Один активированный ФН нельзя просто переносить между произвольными кассами."
    relevant = "ОФД получает фискальные документы от ККТ и передаёт их в ФНС."
    assert not _conceptually_answering_sentence(wrong, question)
    assert _conceptually_answering_sentence(relevant, question)
    sections = [{"section": "Факт", "text": wrong},
                {"section": "Факт", "text": relevant}]
    assert _focused_approved_sentence(
        sections, question, conceptual_question=question) == (sections[1], relevant)


def test_definition_prefers_predicate_about_subject_over_incidental_mention():
    question = "Объясни, что такое ОФД и зачем он нужен кассе?"
    incidental = "Для обычных сценариев облачной кассы требуется договор и тариф ОФД."
    defining = "ОФД получает документы от кассы и передаёт их в ФНС."
    sections = [{"section": "Факт", "text": incidental},
                {"section": "Факт", "text": defining}]
    assert not _conceptually_answering_sentence(incidental, question)
    assert _focused_approved_sentence(
        sections, question, conceptual_question=question) == (sections[1], defining)
    assert not _conceptually_answering_sentence(
        "Для прямого API сначала получают доступ к тестовой среде.", "Что такое API?")


def test_status_reading_does_not_confuse_noun_with_send_operation():
    question = "Как проверить статус отправки чека в ФНС?"
    state = DialogueState(intent="receipt", operation="status", object="чек")
    section = {"section": "Результат контроля", "text":
               "В поиске чеков статус отражает результат контроля ФНС. "
               "Подсказка иконки показывает статус."}
    assert _read_only_status_fact(state, question, section)
    assert not _read_only_status_fact(state, "Как повторно отправить чек?", section)


def test_general_knowledge_output_rejects_invented_citations(tmp_path, monkeypatch):
    source = "atol_online/fn/fn-basics.md"
    body = (ROOT / "data/knowledge" / source).read_text(encoding="utf-8").split("---", 2)[2].strip()
    heading, text = _sections(body)[0]
    retrieval = _retrieval(source, "atol-online-11253-fn-basics", heading,
        {"task_category": "fiscal_drive", "manufacturer": "АТОЛ"}, text)
    question = "Что такое ОФД и зачем он нужен?"
    state = DialogueState(intent="general", operation="explain", object="ОФД",
                          task=Fact(question, 1, question, 0, len(question)))

    async def offline_bad_citation(*_args, **_kwargs):
        return Generation("ОФД передаёт документы. Источник: https://example.invalid", "fixture")

    monkeypatch.setattr("app.source_first_service.generate", offline_bad_citation)
    answer = asyncio.run(SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT).answer(
        question, state=state, coordinator_decision={"route": "grounded_information",
        "current_subgoal": question}))
    assert answer.scenario == "escalate"
    assert answer.scenario_reason == "general_knowledge_output_rejected"


def test_software_integration_scope_does_not_require_hardware_model_or_ofd(tmp_path, monkeypatch):
    import json

    source = "1c/bank/directbank-all-accounts.md"
    doc_id, heading = "batch-20261013-bank-directbank-all-accounts", "Безопасная диагностика"
    body = (ROOT / "data/knowledge" / source).read_text(encoding="utf-8").split("---", 2)[2].strip()
    text = dict(_sections(body))[heading]
    scope = {"service": "1С:Бухгалтерия 8", "task_category": "bank_statement",
             "operations": ["load_bank_statements"], "manufacturer": "1С",
             "model": "1С:Бухгалтерия 8, редакция 3.0"}
    retrieval = _retrieval(source, doc_id, heading, scope, text)
    question = "В 1С перестали загружаться банковские выписки через DirectBank. С чего начать?"
    facts = {slot: [Fact(value, 1, value, 0, len(value))]
             for slot, value in {"software": "1С", "integration": "DirectBank"}.items()}
    task = TaskContext(task_id="bank", topic_start_message_id=1, intent="bank_statement",
        operation="diagnose", object="банковская выписка", entities=facts,
        active_route=ActiveRoute("software", facts["software"][0]),
        task_fact=Fact(question, 1, question, 0, len(question)))

    async def select_diagnostic(messages, _settings, *, call_stage="generation"):
        payload = json.loads(messages[-1]["content"])
        selected = next(item for item in payload["candidate_sections"]
                        if item["section"] == heading)
        return Generation(json.dumps({"mode": "select", "section_id": selected["id"],
            "applicability_confirmed": True, "order_confirmed": True, "reason": "scoped software diagnostic"}),
            "offline-planner")

    monkeypatch.setattr("app.source_first_service.generate", select_diagnostic)
    answer = asyncio.run(SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT)
        .answer(question, state=DialogueState(task_context=task),
                coordinator_decision={"route": "technical_action", "current_subgoal": question}))
    assert answer.scenario == "answer"
    assert answer.clarification_slot is None
    assert "1С:ДиректБанк" in answer.text
    assert "ОФД" not in answer.text
    gate = answer.retrieval_diagnostics["source_scope_gate"]
    assert gate["eligible_source_count"] == 1
    assert gate["inapplicable"] == []


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

    async def generate_stub(messages, _settings, *, call_stage="generation"):
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
            evidence_fragment = next(item for item in payload["approved_evidence_fragments"]
                if "ОФД получает фискальные документы от зарегистрированной ККТ" in item["text"])
            content = json.dumps({
                "verdict": "relevant",
                "answers_current_question": True,
                "supporting_evidence_ids": [evidence_fragment["id"]]
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
    source_path = "data/knowledge/atol_online/ofd/what-is-ofd.md"
    source_sha256 = hashlib.sha256((ROOT / source_path).read_bytes()).hexdigest()

    async def relevant_stub(messages, _settings, *, call_stage="generation"):
        payload = json.loads(messages[-1]["content"])
        seen.update(payload)
        seen["system_prompt"] = messages[0]["content"]
        fragment = next(item for item in payload["approved_evidence_fragments"]
                        if "ОФД получает фискальные документы" in item["text"])
        return Generation(json.dumps({
            "verdict": "relevant",
            "answers_current_question": True,
            "supporting_evidence_ids": [fragment["id"]]
        }, ensure_ascii=False), "offline-judge")

    monkeypatch.setattr("app.source_first_service.generate", relevant_stub)
    accepted, reason, diagnostics, _ = asyncio.run(_judge_information_relevance(
        supported, question, state, title, section, evidence, settings(tmp_path),
        evidence_body=selected_body, evidence_source=source_path,
        evidence_sha256=source_sha256))
    assert accepted and reason == "semantic_relevance_accepted"
    assert diagnostics["supporting_evidence_ids"]
    assert seen["current_question"] == question
    assert seen["active_task"] == state
    assert all("?" not in item["text"] for item in seen["approved_evidence_fragments"])
    assert all(title not in item["text"] and section not in item["text"]
               for item in seen["approved_evidence_fragments"])
    assert "exact_selected_approved_evidence" not in seen
    assert "Одного совпадения слов недостаточно" in seen["system_prompt"]


def test_saved_q1_quote_omitting_the_word_they_is_accepted_by_source_fragment_id(monkeypatch, tmp_path):
    import asyncio
    import hashlib
    import json
    from app.llm_client import Generation

    fixture = json.loads((ROOT / "tests/fixtures/source_first_q1_quote_mismatch_20261025.json")
                         .read_text(encoding="utf-8"))
    assert 'обрабатывает и передаёт в ФНС' in fixture["old_judge_output"]
    assert 'обрабатывает и передаёт их в ФНС' not in fixture["old_judge_output"]
    source_text = (ROOT / fixture["source"]).read_text(encoding="utf-8").split("---", 2)[2].strip()
    section_body = dict(_sections(source_text))[fixture["section"]]
    evidence = "\n".join(("Для чего АТОЛ Онлайн нужен оператор фискальных данных",
                          fixture["section"], section_body))
    fragments = _information_evidence_fragments(
        section_body, fixture["source"], fixture["source_sha256"], fixture["section"])
    exact_fact_id = next(fragment_id for fragment_id, text in fragments.items()
                         if "обрабатывает и передаёт их в ФНС" in text)
    observed = {}

    async def id_judge(messages, _settings, *, call_stage="generation"):
        payload = json.loads(messages[-1]["content"])
        observed.update(payload)
        return Generation(json.dumps({"verdict": "relevant", "answers_current_question": True,
            "supporting_evidence_ids": [exact_fact_id]}, ensure_ascii=False), "offline-id-judge")

    monkeypatch.setattr("app.source_first_service.generate", id_judge)
    accepted, reason, diagnostics, _ = asyncio.run(_judge_information_relevance(
        fixture["candidate_answer"], fixture["question"], {"object": "ОФД", "operation": "explain"},
        "Для чего АТОЛ Онлайн нужен оператор фискальных данных", fixture["section"], evidence,
        settings(tmp_path), evidence_body=section_body, evidence_source=fixture["source"],
        evidence_sha256=fixture["source_sha256"]))
    assert accepted and reason == "semantic_relevance_accepted"
    assert diagnostics["supporting_evidence_ids"] == [exact_fact_id]
    assert exact_fact_id in {item["id"] for item in observed["approved_evidence_fragments"]}


def test_evidence_fragment_builder_excludes_title_question_and_section_heading():
    import hashlib
    source = ROOT / "data/knowledge/atol_online/ofd/what-is-ofd.md"
    body = source.read_text(encoding="utf-8").split("---", 2)[2].strip()
    section = "Что проверено по инструкции производителя"
    fragments = _information_evidence_fragments(
        dict(_sections(body))[section], "data/knowledge/atol_online/ofd/what-is-ofd.md",
        hashlib.sha256(source.read_bytes()).hexdigest(), section)
    assert fragments
    assert all(not text.endswith("?") for text in fragments.values())
    assert all("Что проверено по инструкции производителя" not in text for text in fragments.values())
    assert all("Для чего АТОЛ Онлайн нужен оператор фискальных данных" not in text
               for text in fragments.values())


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
         "supporting_evidence_ids": []},
        {"verdict": "irrelevant", "answers_current_question": False,
         "supporting_evidence_ids": []},
    )

    import hashlib
    source_path = "data/knowledge/atol_online/ofd/what-is-ofd.md"
    source_sha256 = hashlib.sha256((ROOT / source_path).read_bytes()).hexdigest()
    for candidate, judgment in zip(candidates, judgments):
        grounded, _ = _validate_information_composition(candidate, evidence, section)
        assert grounded == candidate  # Same article alone does not make it responsive.

        async def judge_stub(messages, _settings, judgment=judgment):
            return Generation(json.dumps(judgment, ensure_ascii=False), "offline-judge")

        monkeypatch.setattr("app.source_first_service.generate", judge_stub)
        accepted, reason, diagnostics, _ = asyncio.run(_judge_information_relevance(
            candidate, question, {"object": "ОФД", "operation": "explain"},
            title, section, evidence, settings(tmp_path), evidence_body=selected_body,
            evidence_source=source_path, evidence_sha256=source_sha256))
        assert not accepted
        assert reason == "answer_does_not_address_current_question_semantically"
        assert diagnostics["verdict"] == "irrelevant"


def test_relevance_judgment_rejects_unknown_ids_and_text_quotes(monkeypatch):
    import json
    source = "ОФД получает документы от ККТ и передает их в ФНС."
    accepted, reason, _ = _parse_information_relevance_judgment(json.dumps({
        "verdict": "relevant", "answers_current_question": True,
        "supporting_evidence_ids": ["title-only-or-unknown-id"]
    }, ensure_ascii=False), {"valid-id": source})
    assert not accepted and reason == "relevance_evidence_id_not_in_selected_approved_source"
    quote_only, quote_reason, _ = _parse_information_relevance_judgment(json.dumps({
        "verdict": "relevant", "answers_current_question": True,
        "supporting_evidence_quote": "ОФД возвращает кассе комиссию"
    }, ensure_ascii=False), {"valid-id": source})
    assert not quote_only and quote_reason == "relevance_judgment_invalid_schema"
    uncertain, uncertain_reason, _ = _parse_information_relevance_judgment(json.dumps({
        "verdict": "uncertain", "answers_current_question": False,
        "supporting_evidence_ids": ["valid-id"]
    }, ensure_ascii=False), {"valid-id": source})
    assert not uncertain and uncertain_reason == "answer_does_not_address_current_question_semantically"
    invalid, invalid_reason, _ = _parse_information_relevance_judgment(json.dumps({
        "verdict": "maybe", "answers_current_question": True,
        "supporting_evidence_ids": ["valid-id"]
    }, ensure_ascii=False), {"valid-id": source})
    assert not invalid and invalid_reason == "relevance_judgment_invalid_schema"

    grounded, reason = _validate_information_composition(
        "ОФД автоматически возвращает комиссию кассе.", source, "Что проверено")
    assert grounded is None and reason == "unsupported_information_claim"
    procedural, reason = _validate_information_composition(
        "Проверьте статус ККТ в ОФД и текущую очередь передачи.",
        "При отсутствии чеков в налоговой стоит отдельно проверить статус ККТ в ОФД "
        "и текущую очередь передачи.", "Что проверить")
    assert procedural is None and reason == "procedural_or_interface_content_in_information_answer"

    unsafe_partial, reason, _ = _partial_information_composition(
        "ОФД получает документы от ККТ. Проверьте, что очередь передачи пуста.",
        source, "Что проверено")
    assert unsafe_partial is None
    assert reason in {"instruction_in_information_answer",
                      "procedural_or_interface_content_in_information_answer"}


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

    async def generate_stub(messages, _settings, *, call_stage="generation"):
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


def _run_saved_partial_q2(monkeypatch, tmp_path, *, judge_verdict="relevant", repair_output=None):
    import hashlib
    import json
    from app.dialogue_understanding import validate_response

    fixture_path = ROOT / "tests/fixtures/source_first_q2_partial_20261025.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    source = "data/knowledge/atol_online/ofd/what-is-ofd.md"
    doc_id = "atol-online-11256-what-is-ofd"
    path = ROOT / source
    body = path.read_text(encoding="utf-8").split("---", 2)[2].strip()
    sections = {heading: text for heading, text in _sections(body)}
    scope = {"service": "АТОЛ Онлайн", "task_category": "ofd_connection",
             "operations": ["explain_ofd"], "manufacturer": "АТОЛ",
             "model": "АТОЛ Онлайн — облачная ККТ"}
    candidates = [{"id": f"{doc_id}::{heading}", "document_id": doc_id,
        "section": heading, "text": text,
        "title": "Для чего АТОЛ Онлайн нужен оператор фискальных данных", "source": source,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "scope": scope, "qdrant_scope": scope}
        for heading, text in sections.items()]
    monkeypatch.setattr("app.source_first_service._source_sections", lambda *_args: candidates)
    monkeypatch.setattr("app.source_first_service._append_composer_rejection", lambda *_args: None)
    retrieval = _retrieval(source, doc_id, "Вопрос пользователя", scope,
                           sections["Вопрос пользователя"])
    first_question = "Что такое ОФД?"
    question = fixture["question"]
    manager = DialogueManager()
    first_raw = {"request_type": "information", "relation": "new_task", "intent": "general",
        "operation": "explain", "object": "ОФД", "object_evidence": {"quote": "ОФД"},
        "goal": {"quote": first_question}, "symptom": None, "entities": [], "unknown_facts": [],
        "specialist_requested": False, "specialist_evidence": None, "confidence": .9}
    _, _, _, first_observation = validate_response(first_raw, first_question, 1)
    first_state = manager.advance(DialogueState(), first_question, 1, observation=first_observation)
    followup_raw = {"request_type": "information", "relation": "continuation", "intent": "general",
        "operation": "explain", "object": "ОФД", "object_evidence": {"quote": "он"},
        "goal": {"quote": question}, "symptom": None, "entities": [], "unknown_facts": [],
        "specialist_requested": False, "specialist_evidence": None, "confidence": .9}
    _, _, _, followup_observation = validate_response(followup_raw, question, 2)
    state = manager.advance(first_state, question, 2, observation=followup_observation)
    seen = {"calls": [], "judge_payloads": []}
    output_repair = fixture["repair_output"] if repair_output is None else repair_output

    async def generate_stub(messages, _settings, *, call_stage="generation"):
        payload = json.loads(messages[-1]["content"])
        if "candidate_sections" in payload:
            chosen = next(item for item in payload["candidate_sections"]
                          if item["section"] == "Что проверено по инструкции производителя")
            stage = "planner"
            content = json.dumps({"mode": "select", "section_id": chosen["id"],
                "applicability_confirmed": True, "order_confirmed": False,
                "reason": "general explanation"})
        elif "rejected_claims" in payload:
            stage = "repair"
            content = output_repair
        elif "candidate_answer" in payload:
            stage = "semantic_judge"
            seen["judge_payloads"].append(payload)
            if judge_verdict == "relevant":
                evidence_fragment = next(item for item in payload["approved_evidence_fragments"]
                    if "ОФД получает фискальные документы от зарегистрированной ККТ" in item["text"])
                content = json.dumps({"verdict": "relevant", "answers_current_question": True,
                    "supporting_evidence_ids": [evidence_fragment["id"]]}, ensure_ascii=False)
            else:
                content = json.dumps({"verdict": judge_verdict, "answers_current_question": False,
                    "supporting_evidence_ids": []}, ensure_ascii=False)
        else:
            stage = "composer"
            content = fixture["composer_output"]
        seen["calls"].append(stage)
        return Generation(content, "offline-replay", 0, 0, 0)

    monkeypatch.setattr("app.source_first_service.generate", generate_stub)
    answer = asyncio.run(SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT)
        .answer(question, state=state, history=[{"role": "user", "content": first_question},
                                               {"role": "assistant", "content": "ОФД передаёт документы."}]))
    return answer, seen, fixture


def test_saved_q2_partially_accepts_only_grounded_claim_after_semantic_judge(monkeypatch, tmp_path):
    answer, seen, fixture = _run_saved_partial_q2(monkeypatch, tmp_path)

    assert fixture["artifact"] == ".local/ofd-full-live-e2e-rate-controlled-20261025.json"
    assert seen["calls"] == ["planner", "composer", "repair", "semantic_judge"]
    assert len(seen["judge_payloads"]) == 1
    partial = seen["judge_payloads"][0]["candidate_answer"]
    assert partial == "ОФД получает фискальные документы от ККТ, обрабатывает их и передаёт в ФНС в предусмотренном формате."
    assert answer.scenario == "answer"
    assert "ОФД получает фискальные документы" in answer.text
    assert "договор" not in answer.text and "тариф" not in answer.text
    diagnostics = answer.retrieval_diagnostics["answer_composer"]
    assert diagnostics["repair"]["validation"] == "partial"
    assert diagnostics["repair"]["partial_acceptance"]["validation"] == "accepted"
    assert diagnostics["relevance_check"]["verdict"] == "relevant"
    assert diagnostics["repair"]["partial_acceptance"]["discarded_claims"] == [
        {"text": "Для облачной кассы требуется корректно оформленный договор и действующий тариф ОФД.",
         "reason": "unsupported_information_claim"}]


def test_partial_answer_does_not_detach_a_mandatory_condition():
    evidence = ("ОФД передаёт документы в ФНС только при наличии действующего договора. "
                "Договор определяет условия передачи данных.")
    candidate = ("ОФД передаёт документы в ФНС только при наличии действующего договора. "
                 "Для этого подходят любые кассы.")
    partial, reason, _ = _partial_information_composition(
        candidate, evidence, "Проверенные сведения")
    assert partial is None
    assert reason == "partial_answer_may_drop_cross_sentence_condition"


def test_partial_answer_is_rejected_when_semantic_judge_says_irrelevant(monkeypatch, tmp_path):
    answer, seen, _ = _run_saved_partial_q2(monkeypatch, tmp_path, judge_verdict="irrelevant")
    assert len(seen["judge_payloads"]) == 1
    assert "ОФД получает фискальные документы" in seen["judge_payloads"][0]["candidate_answer"]
    assert answer.scenario == "escalate"
    assert answer.scenario_reason == "information_composition_unverified"
    assert answer.retrieval_diagnostics["answer_composer"]["relevance_check"]["verdict"] == "irrelevant"


def test_fully_fabricated_repair_has_no_partial_answer_or_semantic_judge(monkeypatch, tmp_path):
    answer, seen, _ = _run_saved_partial_q2(monkeypatch, tmp_path, repair_output=(
        "ОФД автоматически возвращает комиссию. ОФД начисляет кешбэк за каждую операцию."))
    assert answer.scenario == "escalate"
    assert answer.scenario_reason == "information_composition_unverified"
    assert seen["judge_payloads"] == []
    partial = answer.retrieval_diagnostics["answer_composer"]["repair"]["partial_acceptance"]
    assert partial["validation"] == "rejected"
    assert partial["reason"] == "partial_answer_requires_supported_and_unsupported_claims"
