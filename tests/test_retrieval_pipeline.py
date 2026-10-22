from app.dialogue_state import DialogueManager, DialogueState
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
                  "category": "account", "manufacturer": "aQsi Online", "status": "draft"})
    source = Source([hit], {"user-1": [hit]})
    pipeline = RetrievalPipeline(source)
    state = _state("Где изменить права уже созданному сотруднику в aQsi Online?")
    result = pipeline.search(state, "сервис: aQsi Online — изменение прав существующего сотрудника")
    assert not result.sufficient
    assert result.evidence_status == "partial"
    assert result.supported_steps
    assert "permission_change_workflow_unverified" in result.missing_evidence
    assert result.documents[0].metadata["status"] == "draft"
