"""Offline regression for vNext candidate-to-context boundaries."""
from types import SimpleNamespace

import pytest

from app.retrieval import Retriever
from experiments.vnext.stage3_retrieval import (
    MAX_CONTEXT_CHARS, ReadOnlyStage3, scope_compatible, title_topic_match,
)


def point(identifier, document, title, service, text, *, status="approved", model=None):
    return SimpleNamespace(id=identifier, score=0.85, payload={
        "document_id": document, "title": title, "service": service,
        "model": model, "status": status, "text": text,
        "section": "Порядок", "chunk_index": 1, "operations": ["example"],
    })


POINTS = [
    point("receipt", "platformaofd-lkk-receipt-search", "Платформа ОФД: поиск чеков и фильтры",
          "Платформа ОФД", "Поиск чеков по ФД в личном кабинете Платформы ОФД."),
    point("receipt-draft", "draft-receipt", "Платформа ОФД: поиск чеков и фильтры",
          "Платформа ОФД", "Черновик: неподтвержденный маршрут поиска чека по ФД.", status="draft"),
    point("registration", "registration", "Платформа ОФД: регистрация ККТ в ФНС",
          "Платформа ОФД", "Порядок регистрации и замены фискального накопителя."),
    point("atol-receipt", "atol-receipt", "АТОЛ Онлайн: поиск чеков и фильтры",
          "АТОЛ Онлайн", "Найдите чек по ФД в АТОЛ Онлайн."),
    point("aqsi-user", "aqsi-online-account-add-user", "aQsi Online: добавление сотрудника в кабинет",
          "aQsi Online", "Добавить сотрудника и назначить роль в aQsi Online."),
    point("aqsi-refund", "aqsi-refund", "aQsi Online: полный возврат чека",
          "aQsi Online", "Фискальная процедура полного возврата чека."),
    point("bank", "batch-20261013-bank-directbank-all-accounts",
          "Загрузка выписок по нескольким счетам через 1С:ДиректБанк",
          "1С:Бухгалтерия 8", "Безопасная диагностика: проверить получение банковских выписок."),
    point("tax", "tax", "Документы ЕНС в 1С", "1С:Бухгалтерия 8",
          "Налоговые операции и документы ЕНС."),
]


class MemoryStore:
    def __init__(self):
        self.last_dense = []

    def all_points(self):
        return POINTS

    def semantic(self, query, limit, query_filter=None):
        self.last_dense = [p for p in POINTS if p.payload["status"] == "approved"][:limit]
        return self.last_dense


@pytest.fixture
def stage3():
    result = object.__new__(ReadOnlyStage3)
    result.store = MemoryStore()
    result.retriever = Retriever(result.store, demo=False)
    result.receipt = {"points": len(POINTS), "approved_points": len(POINTS) - 1}
    return result


@pytest.mark.parametrize(("question", "expected", "foreign"), [
    ("Где искать чек по ФД в Платформе ОФД?", "platformaofd-lkk-receipt-search", "registration"),
    ("Нужно создать пользователя в aQsi Online", "aqsi-online-account-add-user", "aqsi-refund"),
    ("В 1С не загружаются банковские выписки; как проверить?",
     "batch-20261013-bank-directbank-all-accounts", "tax"),
])
def test_paraphrased_task_reaches_only_relevant_approved_context(stage3, question, expected, foreign):
    context, trace = stage3.search_with_trace(question, [question], query_origin="raw_user_question")
    assert expected in trace["context_document_ids"]
    assert foreign not in trace["context_document_ids"]
    assert "draft-receipt" not in trace["context_document_ids"]
    assert all(fragment["status"] == "approved" for fragment in context)
    assert trace["context_chars"] <= MAX_CONTEXT_CHARS
    assert trace["search_query"] == question
    assert trace["query_origin"] == "raw_user_question"
    assert all(row["reason"] for row in trace["candidates"])


def test_scope_and_title_rejections_are_after_candidate_retrieval(stage3):
    query = "Как найти чек по ФД в Платформе ОФД?"
    _, trace = stage3.search_with_trace(query, [query])
    decisions = {c["document_id"]: c["reason"] for c in trace["candidates"]}
    assert decisions["atol-receipt"] == "service_unconfirmed_or_other"
    assert decisions["registration"] == "title_topic_mismatch"
    assert decisions["platformaofd-lkk-receipt-search"] == "selected"


def test_model_mismatch_is_conservative():
    candidate = {"service": "АТОЛ", "model": "АТОЛ 30Ф", "title": "Поиск чека"}
    assert scope_compatible(candidate, ["Чек на АТОЛ 55Ф"])[0] is False
    assert title_topic_match(candidate, ["Как найти чек?"])[0] is True


def test_graph_records_effective_query_context_and_claim_without_network(stage3):
    from experiments.vnext.cli import build_graph

    class StubGroq:
        def json(self, prompt):
            if "current_user_message" in prompt:
                return {"new_topic": True, "route": "search",
                        "search_query": "поиск чека ФД Платформа ОФД",
                        "fact_quotes": [], "reason": "stub"}, 1, 1
            candidate = prompt["candidate_approved_fragments"][0]
            quote = candidate["text"]
            return {"applicability": [{"id": candidate["id"], "status": "usable",
                                       "reason": "source matches task"}],
                    "claims": [{"id": candidate["id"], "text": quote, "quote": quote}],
                    "reason": "stub"}, 1, 1

    graph = build_graph(stage3, StubGroq())
    question = "Где искать чек по ФД в Платформе ОФД?"
    state = graph.invoke({"scenario_id": "offline_stub", "user_text": question,
                          "messages": [{"role": "user", "content": question}]},
                         {"configurable": {"thread_id": "offline_stub"}})
    trace = state["retrieval_trace"]
    assert state["task_id"] == "offline_stub:1"
    assert trace["input_question"] == question
    assert trace["search_query"] == "поиск чека ФД Платформа ОФД"
    assert trace["query_origin"] == "llm_generated"  # generated by local stub only
    assert trace["context"] == state["candidates"]
    assert state["response_trace"]["claims"][0]["accepted"] is True
    assert state["response_trace"]["final_answer"] == state["answer"]
