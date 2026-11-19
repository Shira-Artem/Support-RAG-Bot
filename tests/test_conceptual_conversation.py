import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from app.dialogue_state import DialogueState, Fact
from app.llm_client import Generation
from app.source_first_service import SourceFirstService
from test_source_first_dialogue_contract import settings

ROOT = Path(__file__).resolve().parents[1]


class NoConceptSearch:
    def search_for_state(self, *_args):
        raise AssertionError("An ordinary conceptual explanation does not need retrieval")


@pytest.mark.parametrize("question", [
    "Привет! Я недавно открыл небольшой магазин, вообще не понимаю, как работают онлайн-кассы. Можешь помочь?",
    "А ОФД и фискальный накопитель — это одно и то же?",
    "Хочу понять, что происходит с информацией о продаже после оплаты.",
])
def test_validated_conceptual_information_uses_existing_model_path_without_kb(
        monkeypatch, tmp_path, question):
    state = DialogueState(intent="general", operation="explain", object="касса",
        task=Fact.span(question, 1))
    history = [{"role": "user", "content": question, "semantic_mode": True,
                "understanding": {"request_type": "information"}}]
    calls = []
    async def generated(messages, _settings, *, call_stage):
        calls.append(call_stage)
        assert "retrieval was already checked" not in messages[0]["content"]
        return Generation("Касса сохраняет информацию о продаже и формирует чек; ОФД передаёт сведения дальше.", "fixture")
    monkeypatch.setattr("app.source_first_service.generate", generated)
    service = SourceFirstService(NoConceptSearch(), replace(settings(tmp_path), semantic_composer_enabled=True), ROOT)
    answer = asyncio.run(service.answer(question, state=state, history=history,
        coordinator_decision={"route": "grounded_information"}))
    assert calls == ["general_knowledge"]
    assert answer.scenario == "answer"
    assert "Касса сохраняет" in answer.text and "источника" not in answer.text
    trace = answer.retrieval_diagnostics["general_knowledge_fallback"]
    assert trace["source_basis"] == "model_general_knowledge"
    assert trace["approved_sources_checked_first"] is False


@pytest.mark.parametrize("question", ["Как закрыть архив ФН?", "Как настроить кассу?",
    "Какие налоговые требования действуют сейчас?", "Что такое сервис «Ромашка»?"])
def test_technical_legal_and_named_product_requests_keep_existing_evidence_boundary(
        monkeypatch, tmp_path, question):
    state = DialogueState(intent="general", operation="explain", object="касса", task=Fact.span(question, 1))
    history = [{"role": "user", "content": question, "semantic_mode": True,
                "understanding": {"request_type": "information"}}]
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("General model path must not supply this procedure or legal claim")
    monkeypatch.setattr("app.source_first_service.generate", forbidden)
    service = SourceFirstService(NoConceptSearch(), replace(settings(tmp_path), semantic_composer_enabled=True), ROOT)
    answer = asyncio.run(service.answer(question, state=state, history=history,
        coordinator_decision={"route": "grounded_information"}))
    assert answer.scenario == "escalate"
    assert "general_knowledge_fallback" not in (answer.retrieval_diagnostics or {})


@pytest.mark.parametrize("text,accepted", [
    ("Касса автоматически формирует чек и сохраняет данные о продаже. Это позволяет получать отчёты.", True),
    ("Привет! Касса записывает продажу. Касса формирует чек. Данные сохраняются. Что именно хотите узнать?", True),
    ("Касса записывает продажу. Если возникнут вопросы о том, как подключить кассу, дай знать.", True),
    ("Касса сохраняет сведения о продаже и помогает учитывать требования к учёту.", True),
    ("По закону касса должна отправить данные за минуту.", False),
    ("Чтобы начать, откройте Настройки и нажмите Отправить.", False),
    ("Откройте меню настроек кассы.", False),
    ("Закройте архив ФН и замените накопитель.", False),
    ("Согласно инструкции https://example.org касса сохраняет данные.", False),
])
def test_conceptual_descriptions_are_distinct_from_instructions_and_invented_sources(
        monkeypatch, tmp_path, text, accepted):
    state = DialogueState(intent="general", operation="explain", object="касса")
    async def generated(*_args, **_kwargs):
        return Generation(text, "fixture")
    monkeypatch.setattr("app.source_first_service.generate", generated)
    answer = asyncio.run(SourceFirstService(None, settings(tmp_path), ROOT)._general_knowledge_fallback(
        "Как работает касса?", state, 0, {}, retrieval_checked=False))
    assert (answer.scenario == "answer") is accepted


@pytest.mark.parametrize("value,generic", [
    ("онлайн-кассы", True), ("электронный терминал", True), ("кассовый аппарат", True),
    ("Эвотор 7.3", False), ("Эвотор 6 lite", False), ("aQsi Online", False),
    ("НеизвестнаяМодель", False),
])
def test_generic_device_classes_are_not_confirmed_model_identities(value, generic):
    from app.dialogue_understanding import _generic_equipment_value
    assert _generic_equipment_value(value) is generic


def test_unrequested_legal_claim_is_removed_without_erasing_conceptual_explanation(monkeypatch, tmp_path):
    state = DialogueState(intent="general", operation="explain", object="касса")
    text = ("Касса формирует чек и сохраняет сведения о продаже. "
            "Без ОФД документы не считаются официальными. "
            "Всё, что нужно, — договор с ОФД.")
    async def generated(*_args, **_kwargs):
        return Generation(text, "fixture")
    monkeypatch.setattr("app.source_first_service.generate", generated)
    answer = asyncio.run(SourceFirstService(None, settings(tmp_path), ROOT)._general_knowledge_fallback(
        "Как работает касса?", state, 0, {}, retrieval_checked=False))
    assert answer.scenario == "answer"
    assert answer.text == "Касса формирует чек и сохраняет сведения о продаже."
    assert len(answer.retrieval_diagnostics["general_knowledge_fallback"]["removed_out_of_scope_claims"]) == 2
