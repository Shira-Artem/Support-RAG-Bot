from app.dialogue_state import DialogueManager, DialogueState
from app.dialogue_understanding import validate_response
from app.rag import SearchResult
from app.retrieval_pipeline import RetrievalPipeline


class Source:
    def __init__(self, results, articles=None):
        self.results = results
        self.articles = articles or {}

    def search(self, query, top_k=5):
        return self.results[:top_k]

    def article(self, document_id):
        return self.articles.get(document_id, [])


def _state(message):
    return DialogueManager().advance(DialogueState(), message, 1)


def _understood_state(message, operation="check", intent="unknown"):
    payload = {"request_type": "information", "relation": "new_task", "intent": intent,
        "operation": operation, "object": None, "object_evidence": None,
        "goal": {"quote": message}, "symptom": None, "entities": [],
        "unknown_facts": [], "specialist_requested": False,
        "specialist_evidence": None, "confidence": .9}
    _, _, unknown, observation = validate_response(payload, message, 1)
    return DialogueManager().advance(DialogueState(), message, 1,
        observation=observation, unknown_facts=list(unknown))


def test_atol_edo_match_does_not_count_as_employee_access_evidence():
    edo = SearchResult("atol_online/edo/incoming-documents.md",
        "Примите приглашение через Контрагенты в ЭДО.", 0.9,
        metadata={"document_id": "edo-1", "title": "Приглашение АТОЛ Онлайн через ЭДО",
                  "category": "atol_online", "manufacturer": "АТОЛ", "status": "draft"})
    pipeline = RetrievalPipeline(Source([edo]))
    result = pipeline.search(_state("Как изменить права сотрудника в АТОЛ Онлайн?"),
                             "сервис: АТОЛ Онлайн — изменение прав существующего сотрудника")
    assert not result.sufficient
    assert not result.documents
    assert any("task_mismatch:edo!=access" in item.reasons for item in result.rejected)


def test_employee_document_supports_role_and_existing_user_operations():
    text = ("Администратор создаёт учётную запись сотрудника и присваивает заранее созданную роль. "
            "Изменение существующего пользователя выполняется через меню этой записи.")
    hit = SearchResult("aqsi_online/account/add-user.md", text, 0.03,
        metadata={"document_id": "user-1", "title": "Добавление сотрудника в личный кабинет",
                  "category": "account", "manufacturer": "aQsi Online", "status": "approved"})
    source = Source([hit], {"user-1": [hit]})
    pipeline = RetrievalPipeline(source)
    state = _state("Где изменить права уже созданному сотруднику в aQsi Online?")
    result = pipeline.search(state, "сервис: aQsi Online — изменение прав существующего сотрудника")
    assert not result.sufficient
    assert result.evidence_status == "partial"
    assert result.supported_steps
    assert "permission_change_workflow_unverified" in result.missing_evidence
    assert result.documents[0].metadata["status"] == "approved"


def test_subtask_anchor_rejects_same_family_scales_for_scanner_question():
    scanner = SearchResult("aqsi_devices/peripherals/scanner.md",
        "Совместимость зависит от модели сканера. Проверьте USB-C адаптер и считывание DataMatrix.",
        0.7, semantic_score=0.58,
        metadata={"document_id": "scanner", "title": "aQsi: внешний сканер не считывает DataMatrix",
                  "service": "aQsi", "manufacturer": "aQsi", "model": "aQsi (физическая ККТ)",
                  "task_category": "peripheral_setup", "operations": ["configure_peripheral"],
                  "status": "approved"})
    scales = SearchResult("aqsi_devices/peripherals/scales.md",
        "Подключение контролируется через меню весов. Проверьте USB-C адаптер.",
        0.9, semantic_score=None,
        metadata={"document_id": "scales", "title": "aQsi: подключение весов ШТРИХ-СЛИМ 200",
                  "service": "aQsi", "manufacturer": "aQsi", "model": "aQsi (физическая ККТ)",
                  "task_category": "peripheral_setup", "operations": ["configure_peripheral"],
                  "status": "approved"})
    query = "На кассе aQsi не работает сканер штрихкодов. Как проверить подключение?"
    result = RetrievalPipeline(Source([scales, scanner])).search(_understood_state(query, intent="device"), query)
    assert [doc.metadata["document_id"] for doc in result.documents] == ["scanner"]
    assert any(item.document_id == "scales" and "subtask_anchor_uncovered" in item.reasons
               for item in result.rejected)


def test_subtask_action_anchor_prefers_api_test_over_integration_catalog():
    api_test = SearchResult("atol_online/integration/api-test.md",
        "Для тестирования API используйте тестовую среду и проверьте версию API.", 0.7,
        semantic_score=0.55,
        metadata={"document_id": "api-test", "title": "Как тестировать прямую API-интеграцию с АТОЛ Онлайн",
                  "service": "АТОЛ Онлайн", "manufacturer": "АТОЛ", "model": "АТОЛ Онлайн — облачная ККТ",
                  "task_category": "integration", "operations": ["configure_integration"],
                  "status": "approved"})
    catalog = SearchResult("atol_online/integration/catalog.md",
        "Каталог систем совместимых с АТОЛ Онлайн.", 0.9, semantic_score=0.45,
        metadata={"document_id": "catalog", "title": "Совместимость АТОЛ Онлайн с CMS, CRM, эквайрингом и платёжными системами",
                  "service": "АТОЛ Онлайн", "manufacturer": "АТОЛ", "model": "АТОЛ Онлайн — облачная ККТ",
                  "task_category": "integration", "operations": ["configure_integration"],
                  "status": "approved"})
    query = "Как проверить API-интеграцию с АТОЛ Онлайн, если запросы отправляются из нашего сайта, но чеки не появляются?"
    result = RetrievalPipeline(Source([catalog, api_test])).search(_understood_state(query), query)
    assert [doc.metadata["document_id"] for doc in result.documents] == ["api-test"]
    assert any(item.document_id == "catalog" and "subtask_anchor_uncovered" in item.reasons
               for item in result.rejected)


def test_unstated_api_mode_does_not_get_inferred_from_a_catalog_hit():
    api_test = SearchResult("atol_online/integration/api-test.md",
        "For testing API use the test environment and verify the API version.", 0.7,
        metadata={"document_id": "api-test", "title": "How to test direct API integration with ATOL Online",
                  "service": "АТОЛ Онлайн", "manufacturer": "АТОЛ", "model": "АТОЛ Онлайн cloud KKT",
                  "task_category": "integration", "operations": ["configure_integration"],
                  "status": "approved"})
    catalog = SearchResult("atol_online/integration/catalog.md",
        "Catalog of systems compatible with ATOL Online.", 0.9,
        metadata={"document_id": "catalog", "title": "ATOL Online compatibility with CMS, CRM, banks and payment systems",
                  "service": "АТОЛ Онлайн", "manufacturer": "АТОЛ", "model": "АТОЛ Онлайн cloud KKT",
                  "task_category": "integration", "operations": ["configure_integration"],
                  "status": "approved"})
    query = "Как проверить работу интеграции с АТОЛ Онлайн, если запросы отправляются из нашего сайта, но чеки не появляются?"
    result = RetrievalPipeline(Source([catalog, api_test])).search(_understood_state(query), query)
    assert not result.documents
    assert all("subtask_anchor_uncovered" in item.reasons for item in result.rejected)


def test_subtask_gate_rejects_adjacent_archive_sentence_from_partner_cabinet_article():
    query = "В личном кабинете Платформы ОФД касса отображается, но новые чеки не поступают. Что проверить?"
    archive_article = SearchResult("platformaofd/ofd/partner-kkt-diagnostics.md",
        "ККТ отображается в партнёрском кабинете. Отдельный подраздел посвящён архивированию.", .9,
        metadata={"document_id": "partner-kkt", "title": "Платформа ОФД: техническая информация о ККТ в кабинете партнёра",
                  "service": "Платформа ОФД", "task_category": "receipt_transmission",
                  "operations": ["check_transmission"], "status": "approved"})
    transmission_article = SearchResult("platformaofd/ofd/transmission.md",
        "Проверьте ошибки передачи чеков.", .7,
        metadata={"document_id": "transmission", "title": "Платформа ОФД: проверка передачи чеков",
                  "service": "Платформа ОФД", "task_category": "receipt_transmission",
                  "operations": ["check_transmission"], "status": "approved"})
    result = RetrievalPipeline(Source([archive_article, transmission_article])).search(
        _understood_state(query, operation="diagnose", intent="receipt"), query)
    assert [doc.metadata["document_id"] for doc in result.documents] == ["transmission"]
    assert any(item.document_id == "partner-kkt" and "subtask_anchor_uncovered" in item.reasons
               for item in result.rejected)
