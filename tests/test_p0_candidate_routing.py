from app.dialogue_state import DialogueManager, DialogueState
from app.rag import SearchResult
from app.retrieval_pipeline import RetrievalPipeline, _state_task_category, normalize_operation


class Source:
    def __init__(self, hits):
        self.hits = hits

    def search(self, query, top_k=5):
        return self.hits[:top_k]


def _state(text):
    return DialogueManager().advance(DialogueState(), text, "test")


def _hit(document_id, text, *, service="Платформа ОФД", task="cash_list",
         operations=("list_cash_registers",), score=0.95, model=None,
         manufacturer=None, ofd=None):
    return SearchResult(
        f"{document_id}.md", text, score, 0.82, 50.0,
         {"document_id": document_id, "service": service, "task_category": task,
         "operations": list(operations), "status": "approved", "model": model,
          "manufacturer": manufacturer, "ofd": ofd},
    )


def test_task_family_uses_current_subject_when_reducer_operation_is_coarse():
    state = _state("У Эвотор 7.2 что означают индикаторы и почему терминал быстро выключается?")
    assert _state_task_category(state, state.task.value) == "model_features"


def test_bank_intermediary_is_not_global_alias_for_listing_statements():
    query = "В 1С как импортировать выписку другого банка через банк-посредник?"
    assert normalize_operation("list", "bank_statement", query) == \
        "import_bank_statements_via_intermediary"
    assert normalize_operation("list", "bank_statement", "Как посмотреть список выписок?") == \
        "list_bank_statements"


def test_candidate_task_and_operation_beat_high_rank_adjacent_document():
    query = "Как подключить кассу к Платформе ОФД по данным регистрации?"
    state = _state(query)
    wrong = _hit("cash-monitoring", "Мониторинг и список касс в кабинете.", score=0.99,
                 ofd="Платформа ОФД")
    right = _hit("connect-cash-register", "Подключите кассу к Платформе ОФД.",
                  task="ofd_connection", operations=("connect_cash_register",), score=0.35,
                  ofd="Платформа ОФД")

    result = RetrievalPipeline(Source([wrong, right])).search(state, query)

    assert [doc.metadata["document_id"] for doc in result.documents] == ["connect-cash-register"]
    rejected = {item.document_id: item.reasons for item in result.rejected}
    assert any(reason.startswith("task_mismatch:") for reason in rejected["cash-monitoring"])


def test_explicit_candidate_action_disambiguates_unknown_operation():
    query = "Как архивировать кассу в Платформе ОФД?"
    state = _state(query)
    archive = _hit("archive-cash", "Архивируйте кассу из её карточки.",
                   task="ofd_connection", operations=("archive_cash_register",),
                   score=0.35, ofd="Платформа ОФД")
    connect = _hit("connect-cash", "Подключите кассу к кабинету.",
                   task="ofd_connection", operations=("connect_cash_register",),
                   score=0.99, ofd="Платформа ОФД")
    result = RetrievalPipeline(Source([connect, archive])).search(state, query)
    assert [doc.metadata["document_id"] for doc in result.documents] == ["archive-cash"]
    assert result.context and result.sufficient
    assert any("operation_mismatch:query_action" in item.reasons
               for item in result.rejected if item.document_id == "connect-cash")


def test_fns_indicator_candidate_is_not_treated_as_fiscal_drive_instruction():
    query = "Что означает запрет от ФНС и где посмотреть детализацию нарушений в Платформе ОФД?"
    state = _state(query)
    assert _state_task_category(state, query) == "fns_monitoring"
    hit = _hit("fns-indicators", "Запрет от ФНС показывает кассы с запретом передачи.",
                task="fns_monitoring", operations=("inspect_fns_indicators",), score=0.4,
                ofd="Платформа ОФД")
    result = RetrievalPipeline(Source([hit])).search(state, query)
    assert result.documents and result.sufficient


def test_explicit_model_mismatch_stays_rejected_after_candidate_routing():
    query = "Что умеет Эвотор 7.2?"
    state = _state(query)
    hit = _hit("other-model", "Характеристики модели и индикаторы.", service="Эвотор",
                task="model_features", operations=("check_model_features",),
                model="Эвотор 6", manufacturer="Эвотор", score=0.99)
    result = RetrievalPipeline(Source([hit])).search(state, query)
    assert not result.documents
    assert any("equipment_mismatch_or_unlabeled" in reason
               for item in result.rejected for reason in item.reasons)
