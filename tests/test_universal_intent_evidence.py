import asyncio
import json

import pytest

from app.answer_service import AnswerService
from app.dialogue_state import DialogueManager, DialogueState
from app.llm_client import Generation
from app.rag import SearchResult
from app.retrieval_pipeline import RetrievalPipeline
from test_expert import settings


class Source:
    def __init__(self, hits):
        self.hits = hits
        self.search_calls = 0

    def search(self, query, top_k=5):
        self.search_calls += 1
        return self.hits[:top_k]


class NoRetrieval:
    def search_for_state(self, *args, **kwargs):
        raise AssertionError("clarification must happen before retrieval")


def _state(text):
    return DialogueManager().advance(DialogueState(), text, 1)


def _hit(source, text, *, document_id, task, operations, status="approved", **metadata):
    return SearchResult(source, text, .8, metadata={
        "document_id": document_id,
        "title": metadata.pop("title", document_id),
        "service": metadata.pop("service", "АТОЛ Онлайн"),
        "status": status,
        "task_category": task,
        "operations": operations,
        **metadata,
    })


def test_three_incident_intents_are_distinct_and_specific():
    tariff = _state("Можно ли прямо сегодня сменить тариф АТОЛ Онлайн?")
    discrepancy = _state(
        "В УПД 12 упаковок, а привезли 10. Поставщик просит пока подписать как есть."
    )
    correction = _state("Я ошибся в чеке, как его исправить?")

    assert (tariff.intent, tariff.operation, tariff.object) == ("billing", "change", "тариф")
    assert (discrepancy.intent, discrepancy.operation, discrepancy.object) == (
        "delivery_document", "reconcile", "УПД"
    )
    assert (correction.intent, correction.operation, correction.object) == (
        "receipt", "correct", "чек"
    )


@pytest.mark.parametrize("message,expected", [
    ("Как поменять тариф сервиса?", ("billing", "change")),
    ("В накладной 8 мест, получили 7", ("delivery_document", "reconcile")),
    ("В пробитом чеке ошибка, нужно скорректировать", ("receipt", "correct")),
])
def test_analogous_categories_use_the_same_general_vocabulary(message, expected):
    state = _state(message)
    assert (state.intent, state.operation) == expected


def test_tariff_partial_answer_uses_only_the_matching_approved_procedure(monkeypatch, tmp_path):
    change_plan = _hit(
        "atol_online/billing/change-plan.md",
        "Изменение тарифа происходит после окончания действия текущей лицензии. "
        "Для перехода обратитесь в поддержку.",
        document_id="change-plan", task="billing", operations=["manage_billing", "change_plan"],
        section="Переход на другой тариф",
    )
    renewal = _hit(
        "atol_online/billing/renewal-invoice.md",
        "Счета на продление направляются по электронной почте.",
        document_id="renewal", task="billing", operations=["get_renewal_invoice"],
    )
    reports = _hit(
        "atol_online/account/cash-reports.md",
        "После замены ФН отчёты направляются на регистрационную почту.",
        document_id="reports", task="cash_reports", operations=["view_cash_reports"],
    )
    draft = _hit(
        "atol_online/billing/draft.md", "Смените тариф сегодня.",
        document_id="draft", task="billing", operations=["change_plan"], status="draft",
    )
    state = _state("Можно ли прямо сегодня сменить тариф АТОЛ Онлайн?")
    source = Source([draft, renewal, reports, change_plan])
    retrieval = RetrievalPipeline(source).search(state, "сервис: АТОЛ Онлайн — изменение тарифа")

    assert [doc.source for doc in retrieval.documents] == [change_plan.source]
    assert {step["document_id"] for step in retrieval.supported_steps} == {"change-plan"}
    assert len(retrieval.supported_steps) <= 3
    assert any("status_unapproved" in item.reasons for item in retrieval.rejected)
    assert any("operation_mismatch:change" in item.reasons for item in retrieval.rejected)
    assert any("task_mismatch:cash_reports!=billing" in item.reasons for item in retrieval.rejected)

    calls = []
    async def fake_generation(messages, config):
        calls.append(messages)
        return Generation(json.dumps({"scenario": "answer", "response":
            "Изменение тарифа происходит после окончания действия текущей лицензии. "
            "Для перехода обратитесь в поддержку."}, ensure_ascii=False), "stub-model")

    monkeypatch.setattr("app.answer_service.generate", fake_generation)
    rag = type("Rag", (), {"search_for_state": lambda self, *args: retrieval})()
    answer = asyncio.run(AnswerService(rag, settings(tmp_path)).answer(
        "Можно ли прямо сегодня сменить тариф АТОЛ Онлайн?", state=state
    ))
    assert answer.generation_status == "generated" and answer.llm_call_attempted and calls
    assert "после окончания" in answer.text
    assert "счет" not in answer.text.casefold() and "фн" not in answer.text.casefold()
    assert "Переход на другой тариф:" not in answer.text


def test_upd_discrepancy_and_ambiguous_receipt_correction_clarify_without_model(monkeypatch, tmp_path):
    async def no_generation(*args, **kwargs):
        raise AssertionError("ambiguous procedures must not call the model")

    monkeypatch.setattr("app.answer_service.generate", no_generation)
    service = AnswerService(NoRetrieval(), settings(tmp_path))
    upd = _state("В УПД 12 упаковок, а привезли 10")
    receipt = _state("Я ошибся в чеке, как его исправить?")

    upd_answer = asyncio.run(service.answer(upd.task.value, state=upd))
    receipt_answer = asyncio.run(service.answer(receipt.task.value, state=receipt))

    assert upd_answer.scenario == "clarify" and "приёмка" in upd_answer.text
    assert receipt_answer.scenario == "clarify" and "Что именно неверно" in receipt_answer.text
    assert not upd_answer.llm_call_attempted and not receipt_answer.llm_call_attempted
    assert upd_answer.rag_chunks == receipt_answer.rag_chunks == 0


def test_specific_receipt_correction_keeps_error_details_in_normal_rag(monkeypatch, tmp_path):
    hit = _hit(
        "atol_online/receipts/correction-ffd-1-2.md",
        "Для ФФД 1.2 способ исправления зависит от ошибки в сумме и статуса чека.",
        document_id="correction-ffd-1-2", task="correction_receipt",
        operations=["correct_receipt"], section="Исправление суммы",
    )
    source = Source([hit])
    pipeline = RetrievalPipeline(source)
    captured = {}

    calls = []
    async def fake_generation(messages, config):
        calls.append(messages)
        return Generation(json.dumps({"scenario": "answer", "response":
            "Для ФФД 1.2 способ исправления зависит от ошибки в сумме и статуса чека."},
            ensure_ascii=False), "stub-model")

    monkeypatch.setattr("app.answer_service.generate", fake_generation)

    def search_for_state(_self, state, query):
        captured["query"] = query
        return pipeline.search(state, query)

    rag = type("Rag", (), {"search_for_state": search_for_state})()
    question = "В чеке АТОЛ Онлайн на ФФД 1.2 неверная сумма, как исправить?"
    state = _state(question)
    answer = asyncio.run(AnswerService(rag, settings(tmp_path)).answer(question, state=state))

    assert source.search_calls == 1
    assert "неверная сумма" in captured["query"].casefold()
    assert "ффд 1.2" in captured["query"].casefold()
    assert answer.scenario != "clarify"
    assert answer.llm_call_attempted and calls


def test_receipt_detail_continues_correction_but_explicit_topic_switch_starts_new_task():
    manager = DialogueManager()
    correction = manager.advance(DialogueState(), "Я ошибся в чеке, как его исправить?", 1)
    awaiting = manager.observe_answer(
        correction, scenario="clarify", reason="receipt_correction_details_missing",
        question="Что именно неверно?", slot="details",
    )
    detailed = manager.advance(awaiting, "Неверная сумма, чек уже выдан", 2)
    switched = manager.advance(awaiting, "Кстати, как сменить тариф АТОЛ Онлайн?", 3)

    assert detailed.task_id == correction.task_id
    assert detailed.transition == "clarification" and detailed.operation == "correct"
    assert [fact.value for fact in detailed.details] == ["Неверная сумма, чек уже выдан"]
    assert switched.task_id == "task:3" and switched.transition == "new_task"
    assert (switched.intent, switched.operation) == ("billing", "change")
    assert not switched.details


def test_concrete_question_with_greeting_runs_normal_rag_and_one_model_call(monkeypatch, tmp_path):
    hit = _hit(
        "platformaofd/ofd/receipt-search.md",
        "В разделе «Чеки» откройте поиск чеков.",
        document_id="receipt-search", task="receipt_search", operations=["search_receipt"],
        service="Платформа ОФД", source_url="https://vendor.example/search",
        source_checked_at="2026-10-22", evidence_coverage={"search": "full"},
    )
    source = Source([hit])
    pipeline = RetrievalPipeline(source)
    calls = {"llm": 0}

    async def generated(*args, **kwargs):
        calls["llm"] += 1
        raw = json.dumps({
            "scenario": "answer", "reason": "source",
            "response": "В разделе «Чеки» откройте поиск чеков.",
        }, ensure_ascii=False)
        return Generation(raw, "fixture-model", 20, 10, 30)

    monkeypatch.setattr("app.answer_service.generate", generated)
    rag = type("Rag", (), {
        "search_for_state": lambda self, state, query: pipeline.search(state, query)
    })()
    question = "Привет, как найти чек в Платформе ОФД?"
    answer = asyncio.run(AnswerService(rag, settings(tmp_path)).answer(question, state=_state(question)))

    assert source.search_calls == 1 and calls["llm"] == 1
    assert answer.scenario == "answer" and answer.validation_status == "passed"
    assert answer.llm_call_attempted
