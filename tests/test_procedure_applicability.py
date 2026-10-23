from __future__ import annotations

from app.answer_service import _pre_retrieval_clarification
from app.dialogue_state import DialogueManager, DialogueState
from app.procedure_policy import document_applicability, operation_compatibility
from app.rag import SearchResult
from app.retrieval_pipeline import RetrievalPipeline, _state_task_category
from app.response_grounding import _evidence


class Source:
    def __init__(self, hits):
        self.hits = hits

    def search(self, query, top_k=5):
        return self.hits[:top_k]


def state(text):
    return DialogueManager().advance(DialogueState(), text, 1)


def hit(text, **metadata):
    return SearchResult("vendor/specialized-guide.md", text, .9, metadata={
        "document_id": "specialized-guide", "status": "approved", **metadata,
    })


def test_unknown_fiscal_drive_change_requests_target_and_equipment_before_retrieval():
    current = state("Нужно изменить настройки фискального накопителя")
    assert current.intent == "fiscal_drive" and current.operation == "change"
    clarification = _pre_retrieval_clarification(current)
    assert clarification and clarification[1] == "fiscal_drive_change_scope_missing"
    assert "что именно" in clarification[0].casefold()
    assert "модель" in clarification[0].casefold()


def test_safe_fiscal_drive_resource_check_remains_applicable_without_model():
    current = state("Как в Платформе ОФД проверить ресурс ФН?")
    assert current.intent == "fiscal_drive" and current.operation == "check"
    # This is the real approved knowledge article: it describes the resource
    # filter in Platforma OFD cash monitoring, rather than a fabricated
    # cash_list operation attached to an unrelated technical article.
    guide = SearchResult(
        "data/knowledge/platformaofd/ofd/lkk-cash-monitoring.md",
        "Откройте «Кассы» → «Мониторинг». Предустановленные фильтры позволяют отбирать кассы "
        "с почти заполненной памятью ФН. «Ресурс ФН менее 30 дней» определяется признаками "
        "срочной замены или исчерпания ресурса из отчёта закрытия смены.", .9,
        metadata={
            "document_id": "platformaofd-lkk-cash-monitoring",
            "status": "approved", "service": "Платформа ОФД",
            "task_category": "cash_list", "operations": ["list_cash_registers"],
            "_operations_explicit": True,
        },
    )
    assert operation_compatibility(current.operation, guide.metadata, current.task.value,
                                   task_category="cash_list") == "match"
    assert not document_applicability(current, guide.metadata, technical=True)
    result = RetrievalPipeline(Source([guide])).search(current, current.task.value)
    assert result.documents and result.documents[0].metadata["document_id"] == "platformaofd-lkk-cash-monitoring"


def test_explicit_operation_mismatch_is_a_hard_procedure_rejection():
    current = state("Нужно изменить настройки фискального накопителя")
    guide = hit(
        "Для перерегистрации ККТ подготовьте заявление в ФНС.",
        task_category="fiscal_drive", operations=["check_reregistration"],
        _operations_explicit=True,
    )
    assert operation_compatibility(current.operation, guide.metadata, current.task.value,
                                   task_category="fiscal_drive") == "mismatch"
    assert not _evidence([guide], guide.text, current.operation, current.task.value,
                         task_category=current.intent)


def test_specialized_aqsi_procedure_needs_confirmed_applicability():
    generic = state("Как узнать, какой ОФД подключён?")
    guide = hit(
        "В настройках aQsi Online проверьте IP-адрес и порт подключения.",
        manufacturer="aQsi", model="aQsi Online", service="aQsi Online",
        task_category="ofd_connection", operations=["connect_cash_register"],
        _operations_explicit=True,
    )
    missing = document_applicability(generic, guide.metadata, technical=True)
    assert "equipment" in missing
    assert _state_task_category(generic, generic.task.value) == "ofd_connection"
    retrieval = RetrievalPipeline(Source([guide])).search(generic, generic.task.value)
    assert not retrieval.documents
    assert retrieval.insufficiency_reason == "applicability_context_missing"

    confirmed = state("На кассе aQsi Online как узнать, какой ОФД подключён?")
    assert not document_applicability(confirmed, guide.metadata, technical=True)


def test_grounding_cannot_join_action_and_scope_from_separate_evidence_clauses():
    from app.response_grounding import claim_supported

    evidence = ("В таблице приведены IP-адреса и порты операторов ОФД. "
                "В aQsi Online откройте экран сетевых настроек.")
    assert not claim_supported(
        "Откройте экран сетевых настроек и по IP-адресу определите подключённого ОФД.",
        evidence,
    )


def test_grounding_still_accepts_a_single_clause_supported_action():
    from app.response_grounding import claim_supported

    evidence = "Откройте экран сетевых настроек aQsi Online и сверьте IP-адрес с таблицей операторов."
    assert claim_supported(
        "В aQsi Online откройте сетевые настройки и сверьте IP-адрес с таблицей операторов.",
        evidence,
    )
