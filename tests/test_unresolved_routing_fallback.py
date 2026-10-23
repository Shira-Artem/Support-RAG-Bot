from app.dialogue_state import ActiveRoute, DialogueState, Fact, TaskContext
from app.rag import SearchResult
from app.retrieval_pipeline import RetrievalPipeline


class Source:
    def __init__(self, hits):
        self.hits = hits

    def search(self, query, top_k=5):
        return self.hits[:top_k]


def _state(query, *, service, operation="check", equipment=None):
    facts = {"service": [Fact.span(service, 1)]}
    if equipment:
        facts["equipment"] = [Fact.span(equipment, 1)]
    route = ActiveRoute("service", facts["service"][0])
    return DialogueState(task_context=TaskContext(
        task_id="task:test", intent="unknown", operation=operation,
        entities=facts, active_route=route, task_fact=Fact.span(query, 1),
    ))


def _hit(text, *, service="aQsi Online", model=None, status="approved",
         semantic=0.70, lexical=20.0, document_id="doc"):
    return SearchResult(
        f"{document_id}.md", text, 0.04, semantic, lexical,
        {"document_id": document_id, "title": f"{service}: {document_id}",
         "service": service, "model": model,
         "status": status, "task_category": "account_settings",
         "operations": ["edit_profile"]},
    )


def test_unresolved_task_uses_one_coherent_confirmed_article():
    query = "Где в профиле aQsi Online изменить номер телефона?"
    result = RetrievalPipeline(Source([_hit(
        "В профиле доступны имя, email и телефон.", document_id="profile"),
        _hit("Общие сведения о тарифе и договоре.", document_id="billing", semantic=0.55),
    ])).search(_state(query, service="aQsi Online", operation="change"), query)

    assert [item.metadata["document_id"] for item in result.documents] == ["profile"]
    assert result.evidence_status == "partial"
    assert result.sufficient


def test_unresolved_task_does_not_use_raw_rank_without_content_signal():
    query = "Где посмотреть настройки профиля aQsi Online?"
    result = RetrievalPipeline(Source([_hit(
        "Общая информация о сервисе без настроек профиля.", document_id="generic",
        semantic=0.31, lexical=99.0),
    ])).search(_state(query, service="aQsi Online"), query)

    assert not result.documents
    assert not result.sufficient


def test_unresolved_task_without_a_candidate_stays_without_context():
    query = "Где изменить телефон в профиле aQsi Online?"
    result = RetrievalPipeline(Source([])).search(
        _state(query, service="aQsi Online", operation="change"), query)

    assert not result.documents
    assert result.insufficiency_reason == "no_candidates"


def test_unresolved_task_keeps_service_and_model_boundaries():
    query = "Где проверить состояние Эвотор 6?"
    result = RetrievalPipeline(Source([_hit(
        "Проверьте состояние устройства в настройках.", service="Эвотор",
        model="Эвотор 7", document_id="wrong-model"),
    ])).search(_state(query, service="Эвотор", equipment="Эвотор 6"), query)

    assert not result.documents


def test_unresolved_task_does_not_mix_foreign_service_or_draft():
    query = "Где изменить телефон в профиле aQsi Online?"
    state = _state(query, service="aQsi Online", operation="change")
    foreign = _hit("В профиле доступны имя и телефон.", service="АТОЛ Онлайн",
                   document_id="foreign")
    draft = _hit("В профиле доступны имя и телефон.", status="draft",
                 document_id="draft")
    result = RetrievalPipeline(Source([foreign, draft])).search(state, query)

    assert not result.documents
    reasons = {reason for item in result.rejected for reason in item.reasons}
    assert "service_mismatch_or_unlabeled" in reasons
    assert "status_unapproved" in reasons


def test_unresolved_task_clarifies_when_two_articles_are_equally_relevant():
    query = "Как изменить профиль пользователя в aQsi Online?"
    state = _state(query, service="aQsi Online", operation="change")
    first = _hit("В профиле измените имя и телефон.", document_id="profile-a",
                 semantic=0.70, lexical=20.0)
    second = _hit("В профиле измените email и телефон.", document_id="profile-b",
                  semantic=0.70, lexical=20.0)
    result = RetrievalPipeline(Source([first, second])).search(state, query)

    assert not result.documents
    assert result.insufficiency_reason == "unresolved_task_ambiguous"


def test_specific_operation_mismatch_is_not_relabelled_as_unresolved_fallback():
    query = "Как вернуть оплату пользователю?"
    state = _state(query, service="aQsi Online", operation="return")
    result = RetrievalPipeline(Source([_hit(
        "Назначьте пользователю заранее созданную роль.", document_id="roles"),
    ])).search(state, query)

    assert not result.documents


def test_unresolved_task_does_not_bypass_dangerous_fiscal_gate():
    query = "Как закрыть архив ФН?"
    result = RetrievalPipeline(Source([_hit(
        "Закройте архив ФН в настройках устройства.", service="aQsi Online",
        document_id="dangerous", semantic=0.90, lexical=50.0),
    ])).search(_state(query, service="aQsi Online"), query)

    assert not result.sufficient
    assert result.evidence_status == "unsafe"
    assert result.insufficiency_reason.startswith("unsafe_operation:")
