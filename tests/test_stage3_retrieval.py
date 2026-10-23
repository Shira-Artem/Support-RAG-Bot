from pathlib import Path
from types import SimpleNamespace

from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueManager, DialogueState
from app.knowledge import Chunker, DocumentLoader
from app.rag import SearchResult
from app.rag_query import build_rag_query
from app.retrieval_pipeline import (RetrievalPipeline, normalize_metadata,
                                    normalize_operation, _matches_entity)


def _state(message):
    return DialogueManager().advance(DialogueState(), message, 1)


def test_chunk_metadata_preserves_source_order_and_semantic_links(tmp_path: Path):
    path = tmp_path / "guide.md"
    path.write_text("""---
document_id: ordered-guide
status: approved
verified_at: 2026-10-22
---
# Инструкция

## Вопрос пользователя
Как выполнить операцию?

## Что проверено по инструкции
1. Выполните основной шаг.

## Важное ограничение
Не продолжайте без проверки результата.
""", encoding="utf-8")
    chunks = Chunker().split(DocumentLoader(tmp_path).load(path))

    assert [chunk.metadata["chunk_index"] for chunk in chunks] == list(range(len(chunks)))
    assert [chunk.metadata["section_index"] for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].metadata["next_chunk_id"] == chunks[1].id
    assert chunks[1].metadata["previous_chunk_id"] == chunks[0].id
    assert chunks[1].metadata["relation_to_previous"] == "answers_question"
    assert chunks[2].metadata["relation_to_previous"] == "warning_for_procedure"


def test_adapter_reconstructs_article_by_chunk_index_not_section_or_uuid():
    payloads = [
        {"chunk_id": "c2", "chunk_index": 2, "section_index": 2,
         "document_id": "doc", "source": "guide.md", "status": "approved", "text": "warning"},
        {"chunk_id": "c0", "chunk_index": 0, "section_index": 0,
         "document_id": "doc", "source": "guide.md", "status": "approved", "text": "question"},
        {"chunk_id": "c1", "chunk_index": 1, "section_index": 1,
         "document_id": "doc", "source": "guide.md", "status": "approved", "text": "answer"},
    ]
    points = [SimpleNamespace(id=index, payload=payload) for index, payload in enumerate(payloads)]

    class Store:
        def all_points(self):
            return points

    class Retriever:
        store = Store()

        @staticmethod
        def _allowed(payload, filters):
            return payload["status"] == "approved"

    article = RetrieverRAGAdapter(Retriever()).article("doc")
    assert [item.metadata["chunk_index"] for item in article] == [0, 1, 2]


def test_all_chunks_are_evaluated_before_document_deduplication():
    metadata = {"document_id": "users", "source": "users.md", "status": "approved",
                "service": "aQsi Online", "task_category": "access"}
    weak = SearchResult("users.md", "Общие сведения о личном кабинете.", .9,
                        metadata={**metadata, "chunk_id": "weak"})
    strong = SearchResult("users.md", "Назначьте сотруднику заранее созданную роль.", .8,
                          metadata={**metadata, "chunk_id": "strong"})

    class Source:
        def search(self, query, top_k=5):
            return [weak, strong]

    state = _state("Как назначить роль сотруднику в aQsi Online?")
    result = RetrievalPipeline(Source()).search(
        state, "сервис: aQsi Online — назначение роли сотруднику"
    )
    assert result.documents and result.documents[0].text == strong.text
    assert result.candidates[0].document_id == "users"


def test_task_aware_operation_normalization_is_shared_by_state_and_documents():
    assert normalize_operation("change", "billing") == "change_plan"
    assert normalize_operation("reconcile", "document_discrepancy") == "record_discrepancy"
    assert normalize_operation("check", "marking") == "check_marking_code"
    correction = normalize_metadata({
        "source": "compliance/correction.md", "status": "approved",
        "task_category": "kkt_rules", "operations": ["correct_receipt"],
    })
    transmission = normalize_metadata({
        "source": "ofd/check.md", "status": "approved",
        "task_category": "ofd_connection", "operations": ["check_transmission"],
    })
    assert correction["task_category"] == "correction_receipt"
    assert transmission["task_category"] == "receipt_transmission"
    assert not _matches_entity("aQsi Online", "aQsi")
    assert not _matches_entity("АТОЛ Онлайн", "АТОЛ")
    assert _matches_entity("1С", "1С:Бухгалтерия 8")


def test_generic_operations_use_task_context_and_do_not_become_global_aliases():
    assert normalize_operation("check", "integration") == "integration_connect"
    assert normalize_operation("check", "error_diagnosis") == "diagnose_error"
    assert normalize_operation("check", "receipt_search") == "search_receipt"
    assert normalize_operation("check") == "check"
    assert normalize_operation("change_permissions", "billing", "как оплатить долг") == "pay_debt"
    assert normalize_operation("change_permissions", "access", "как оплатить долг") == "change_permissions"


def test_query_keeps_current_request_details_but_drops_superseded_incident_values():
    manager = DialogueManager()
    state = manager.advance(DialogueState(), "Эвотор ФН 235: почему не передаёт чеки в ОФД?", 1)
    first = build_rag_query(state)
    assert all(term in first for term in ("Эвотор", "235", "ОФД", "переда"))

    updated = manager.advance(state, "Теперь код ошибки ФН 3979.", 2)
    second = build_rag_query(updated)
    assert "3979" in second and "235" not in second


def test_receipt_journal_check_does_not_mix_ofd_transmission_operation():
    journal = SearchResult(
        "atol_online/receipts/journal.md", "В журнале доступен поиск чека по параметрам.", .7,
        metadata={"document_id": "journal", "source": "atol_online/receipts/journal.md",
                  "status": "approved", "service": "АТОЛ Онлайн",
                  "task_category": "receipt_search", "operations": ["search_receipt"]},
    )
    transmission = SearchResult(
        "atol_online/ofd/check.md", "Проверьте связь кассы с ОФД.", .8,
        metadata={"document_id": "transmission", "source": "atol_online/ofd/check.md",
                  "status": "approved", "service": "АТОЛ Онлайн",
                  "task_category": "ofd_connection", "operations": ["check_transmission"]},
    )

    class Source:
        def search(self, query, top_k=5):
            return [transmission, journal]

    state = _state("В журнале АТОЛ Онлайн не нахожу чек за вчера. Какие данные проверить?")
    result = RetrievalPipeline(Source()).search(
        state, "сервис: АТОЛ Онлайн — проверка чека в журнале"
    )
    assert {doc.metadata["document_id"] for doc in result.documents} == {"journal"}
    assert any(item.document_id == "transmission" for item in result.rejected)
