from __future__ import annotations

import csv
from pathlib import Path

from app.dialogue_state import DialogueManager, DialogueState
from app.knowledge import Chunker, DocumentLoader
from app.rag_query import build_rag_query
from app.rag import SearchResult
from app.retrieval_pipeline import RetrievalPipeline, _state_task_category


ROOT = Path(__file__).parents[1]


class Source:
    def __init__(self, results, articles=None):
        self.results = results
        self.articles = articles or {}

    def search(self, query, top_k=5):
        return self.results[:top_k]

    def article(self, document_id):
        return self.articles.get(document_id, [])


def _state(*messages):
    manager, state = DialogueManager(), DialogueState()
    for index, message in enumerate(messages, 1):
        state = manager.advance(state, message, index)
    return state


def _loaded_hit(relative_path, *, approved=False):
    loader = DocumentLoader(ROOT / "data/knowledge")
    document = loader.load(loader.root / relative_path)
    chunks = Chunker().split(document)
    # The fixture exercises both status branches regardless of a document's
    # current editorial approval in the knowledge base.
    metadata = {**chunks[0].metadata, "status": "approved" if approved else "draft"}
    # A SearchResult is the local retrieval boundary under test; no index is written.
    return SearchResult(document.source, "\n\n".join(page for _, page in document.pages), .04,
                        metadata=metadata), chunks


def test_directbank_routes_as_bank_statements_and_keeps_1c_scope():
    hit, chunks = _loaded_hit("1c/bank/directbank-all-accounts.md", approved=True)
    state = _state("1С:ДиректБанк, как загрузить выписки по всем счетам?",
                   "А где посмотреть список выписок?")
    query = "ПО: 1С — просмотр списка банковских выписок"
    assert state.intent == "bank_statement" and state.operation == "list"
    assert _state_task_category(state, query) == "bank_statement"
    result = RetrievalPipeline(Source([hit], {hit.metadata["document_id"]: chunks_to_results(chunks, hit)})).search(state, query)
    assert result.documents and {doc.metadata["document_id"] for doc in result.documents} == {"batch-20261013-bank-directbank-all-accounts"}
    assert not result.rejected


def chunks_to_results(chunks, parent):
    return [SearchResult(parent.source, chunk.text, .03, metadata={**chunk.metadata, "status": "approved"})
            for chunk in chunks]


def test_integration_1c_search_is_scoped_to_selected_cloud_service():
    aqsi, aqsi_chunks = _loaded_hit("aqsi_online/integration/1c-setup.md", approved=True)
    atol, _ = _loaded_hit("atol_online/integration/integration-1c-versions.md", approved=True)
    physical_aqsi = SearchResult("aqsi/aqsi-error-115.md",
        "Для физической кассы aQsi проверьте только указанный код ошибки.", .03,
        metadata={"document_id": "physical-aqsi-integration-control", "title": "aQsi physical",
                  "service": "aQsi", "manufacturer": "aQsi", "task_category": "integration",
                  "status": "approved"})
    state = _state("aQsi Online, как подключить к 1С:УНФ?")
    query = "сервис: aQsi Online — ПО: 1С — подключить aQsi Online к 1С:УНФ"
    results = [aqsi, atol, physical_aqsi]
    articles = {
        aqsi.metadata["document_id"]: chunks_to_results(aqsi_chunks, aqsi),
    }
    result = RetrievalPipeline(Source(results, articles)).search(state, query)
    assert result.documents and {doc.metadata["document_id"] for doc in result.documents} == {"aqsi-online-integration-1c-setup"}
    assert any("service_mismatch_or_unlabeled" in item.reasons for item in result.rejected)
    assert any(item.document_id == "physical-aqsi-integration-control"
               and "service_mismatch_or_unlabeled" in item.reasons for item in result.rejected)


def test_generic_bifit_route_does_not_authorize_bifit_kassa_product_evidence():
    state = _state("Здравствуйте. Нам нужно протестировать в программе БИФИТ систему общепит со столами.")
    query = build_rag_query(state)
    hit = SearchResult("drafts/bifit-kassa-tables.md", "Настройка столов в БИФИТ Касса.", .9,
        metadata={"document_id": "bifit-kassa-tables", "title": "Столы БИФИТ Касса",
                  "service": "БИФИТ Касса", "task_category": "settings", "status": "approved"})
    result = RetrievalPipeline(Source([hit])).search(state, query)
    assert state.routing_service == "БИФИТ" and state.routing_slot == "service"
    assert not result.documents and not result.sufficient
    assert "service_mismatch_or_unlabeled" in result.rejected[0].reasons


def test_unknown_operation_does_not_reject_exact_approved_evotor_instruction():
    hit, chunks = _loaded_hit("evotor/cash/evotor-6-receipt-copy.md", approved=True)
    state = _state("Эвотор 6, как распечатать копию чека по ФД 123?")
    state.operation = "unknown"
    query = "оборудование: Эвотор 6 — производитель: Эвотор — распечатать копию чека по ФД 123"
    assert _state_task_category(state, query) == "receipt_print"
    result = RetrievalPipeline(Source([hit], {hit.metadata["document_id"]: chunks_to_results(chunks, hit)})).search(state, query)
    assert result.documents and {doc.metadata["document_id"] for doc in result.documents} == {"evotor-6-receipt-copy-360005002514"}
    assert all("operation_unconfirmed" not in item.reasons for item in result.rejected)


def test_strong_service_matched_document_can_survive_missing_task_and_operation_tags():
    hit = SearchResult(
        "legacy/evotor-copy.md",
        "На Эвотор 6 откройте печать копии чека по номеру ФД. Выберите документ и распечатайте копию.",
        .04,
        metadata={"document_id": "legacy-evotor-copy", "title": "Эвотор 6: копия чека по ФД",
                  "manufacturer": "Эвотор", "model": "Эвотор 6", "status": "approved"},
    )
    state = _state("Эвотор 6, как распечатать копию чека по ФД 123?")
    query = "оборудование: Эвотор 6 — производитель: Эвотор — копия чека по ФД"
    result = RetrievalPipeline(Source([hit])).search(state, query)
    assert _state_task_category(state, query) == "receipt_print"
    assert result.documents and result.documents[0].metadata["document_id"] == "legacy-evotor-copy"


def test_draft_documents_never_enter_answer_context_even_when_relevant():
    hit, _ = _loaded_hit("evotor/cash/evotor-6-receipt-copy.md", approved=False)
    state = _state("Эвотор 6, как распечатать копию чека по ФД 123?")
    result = RetrievalPipeline(Source([hit])).search(state, "Эвотор 6 копия чека печать документа по номеру")
    assert not result.documents and not result.sufficient
    assert "status_unapproved" in result.rejected[0].reasons


def test_full_audit_csv_covers_every_knowledge_markdown_document():
    audit = ROOT / "docs/rag-quality-v2/metadata-audit.csv"
    with audit.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(list((ROOT / "data/knowledge").rglob("*.md"))) == 269
    assert all(row["document_id"] and row["source_path"] and row["current_status"] for row in rows)
    assert any(row["document_id"] == "aqsi-online-integration-1c-setup" for row in rows)


def test_chunker_preserves_explicit_software_and_routing_metadata():
    hit, _ = _loaded_hit("aqsi_online/integration/1c-setup.md", approved=False)
    assert hit.metadata["service"] == "aQsi Online"
    assert hit.metadata["software"] == "1С:УНФ"
    assert hit.metadata["task_category"] == "integration"


def test_neighboring_check_routes_remain_distinct_after_bplus_fixes():
    cabinet = DialogueManager().advance(DialogueState(),
        "В личном кабинете Платформа ОФД нужно найти чек за вчера", 1)
    assert _state_task_category(cabinet,
        "оператор: Платформа ОФД — поиск чека за вчера") == "receipt_search"

    transmission = DialogueManager().advance(DialogueState(),
        "На Эвотор 7.3 чек печатается, но не передается в ОФД", 2)
    assert _state_task_category(transmission,
        "производитель: Эвотор — диагностика: чек не передается в кабинет ОФД") == "receipt_transmission"

    cash_register = DialogueManager().advance(DialogueState(),
        "Касса не включается и не печатает чеки", 3)
    assert _state_task_category(cash_register,
        "диагностика кассы не включается и не печатает") == "error_diagnosis"

    information = DialogueState(intent="general", operation="explain")
    assert _state_task_category(information,
        "Что происходит с чеком после регистрации продажи в ОФД?") is None
