"""Offline replays of the 23.10.2026 SQLite response-grounding incidents."""
import json
from pathlib import Path

import pytest

from app.answer_service import (_coverage_notice_is_relevant, _parse_scenario,
                                _safe_alternative, _validation_issue)
from app.dialogue_state import DialogueManager, DialogueState
from app.rag import SearchResult
from app.response_grounding import (claim_supported, deduplicate_statements, evidence_kind,
                                    evidence_statements, needs_procedure_grounding,
                                    statements_equivalent)


FIXTURE = Path(__file__).parent / "fixtures" / "response_grounding_incidents_2026-10-23.json"


def _cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def _replay(case):
    results = [SearchResult(item["source"], item["text"], .9, metadata=item["metadata"])
               for item in case["results"]]
    context = "\n\n".join(result.text for result in results)
    manager = DialogueManager()
    state = manager.advance(DialogueState(), f"{case['service']}. {case['question']}", case["id"])
    state.operation = case["operation"]
    if case["operation"] in {"add_employee", "change_permissions", "assign_role"}:
        state.intent = "access"
    _, _, raw_answer = _parse_scenario(case["raw"])
    request = f"{case['service']}: {case['question']}"
    issue = ("procedural_details_not_grounded"
             if needs_procedure_grounding(raw_answer, context, state, results)
             else _validation_issue(raw_answer, context, request, case["service"], results=results))
    diagnostics = {}
    final = (_safe_alternative(raw_answer, issue, request, context=context,
                               state=state, results=results, diagnostics=diagnostics)
             if issue else raw_answer)
    return raw_answer, final, diagnostics, context, results


def test_sqlite_baseline_contains_old_validator_outputs_without_generation():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["llm_calls"] == 0
    assert {case["id"] for case in payload["cases"]} == {
        "ofd-receipt-search-182", "aqsi-role-170", "aqsi-add-employee-166", "1c-directbank-184",
    }
    assert all(case["raw"] and case["old_final"] and case["old_validation_reason"]
               for case in payload["cases"])


@pytest.mark.parametrize("case", _cases(), ids=lambda item: item["id"])
def test_offline_replay_keeps_raw_and_compares_new_validator(case):
    raw, final, diagnostics, _, _ = _replay(case)
    assert raw
    assert final
    assert diagnostics.get("removed") or diagnostics == {}
    assert case["old_final"] != final or case["old_validation_reason"] is None


def test_ofd_replay_preserves_confirmed_period_and_filters_but_drops_unknown_button():
    case = next(item for item in _cases() if item["id"] == "ofd-receipt-search-182")
    _, final, _, _, _ = _replay(case)
    assert "Для прошлого месяца выберите календарные границы" in final
    assert "диапазон суммы" in final and "способ оплаты" in final
    assert "Найти" not in final
    assert "Поиск кассы по ФН описан отдельно" not in final


def test_aqsi_replay_keeps_safe_role_actions_without_copying_limitation_prose():
    case = next(item for item in _cases() if item["id"] == "aqsi-role-170")
    _, final, _, _, _ = _replay(case)
    assert "Во вкладке «Роли» задайте название роли." in final
    assert "Выберите доступные инструменты и отметьте режим просмотра либо редактирования." in final
    assert "Смотритель касс" not in final
    assert "Развёрнутые разрешения на рисунке скрыты" not in final
    assert "Конкретная роль и её полномочия" in final


def test_1c_replay_rejects_release_bound_to_directbank_and_keeps_configuration_evidence():
    case = next(item for item in _cases() if item["id"] == "1c-directbank-184")
    _, final, diagnostics, _, _ = _replay(case)
    assert "версия DirectBank 3.0.148" not in final
    assert "С версии 3.0.148 для настроенного обмена через 1С:ДиректБанк" in final
    assert "Банк → Банковские выписки" not in final
    assert any(item["reason"] == "unsupported_technical_claim"
               for item in diagnostics["removed"])


def test_document_limitations_are_not_procedural_steps():
    for case in _cases():
        for item in case["results"]:
            body = item["text"].split("\n", 1)[-1]
            kind = evidence_kind(body, item["metadata"].get("section"), item["metadata"])
            assert kind in {"limitation", "procedure", "interface", "fact"}
        context = "\n\n".join(item["text"] for item in case["results"])
        steps = evidence_statements(
            [SearchResult(item["source"], item["text"], .9, metadata=item["metadata"])
             for item in case["results"]], context)
        for step in steps:
            if step.get("section") in {"Ограничения", "Передать специалисту"}:
                assert step["kind"] == "limitation"


@pytest.mark.parametrize("case_id,claim", [
    ("ofd-receipt-search-182", "ФН можно использовать как прямой фильтр чеков."),
    ("aqsi-role-170", "Назначьте роль «Смотритель касс», она даст доступ к отчётам."),
    ("1c-directbank-184", "В DirectBank версии 3.0.148 доступна загрузка выписок."),
])
def test_negative_replays_keep_unconfirmed_entity_relations_blocked(case_id, claim):
    case = next(item for item in _cases() if item["id"] == case_id)
    results = [SearchResult(item["source"], item["text"], .9, metadata=item["metadata"])
               for item in case["results"]]
    context = "\n\n".join(result.text for result in results)
    assert _validation_issue(claim, context, case["question"], case["service"], results=results)


def test_permission_label_from_limitation_cannot_validate_an_action():
    results = [
        SearchResult(
            "service/roles.md",
            "Создайте роль во вкладке «Роли». Выберите доступные инструменты и отметьте режим просмотра.",
            .9,
            metadata={"section": "Создать роль", "operations": ["create_role"]},
        ),
        SearchResult(
            "service/roles.md",
            "Ограничения\nНельзя обещать права на конкретный отчёт по одному названию раздела.",
            .9,
            metadata={"section": "Ограничения", "chunk_role": "warning",
                      "operations": ["create_role"]},
        ),
    ]
    context = "\n\n".join(result.text for result in results)
    claim = "Отметьте режим просмотра для раздела «Отчёты»."
    assert not claim_supported(claim, context, evidence_results=results)
    assert _validation_issue(
        claim, context, "Нужен только просмотр касс и отчётов.", "aQsi Online",
        results=results,
    )


def test_interface_mode_does_not_prove_configuration_mode_or_wrong_product_release():
    result = SearchResult(
        "1c/bank/directbank.md",
        "С версии 3.0.148 для настроенного обмена через 1С:ДиректБанк доступна загрузка выписки. "
        "Откройте список «Банковские выписки»: в простом интерфейсе «Деньги → Банк», "
        "в полном — «Банк и касса → Банк».",
        .9,
        metadata={"section": "Безопасная диагностика", "version": "3.0.148",
                  "software": "1С:Бухгалтерия", "service": "1С:ДиректБанк"},
    )
    context = result.text
    assert not claim_supported(
        "В версии DirectBank 3.0.148 доступна загрузка выписки.",
        context, evidence_results=[result],
    )
    assert not claim_supported("Используйте полную конфигурацию.", context,
                               evidence_results=[result])
    assert claim_supported(
        "Откройте список «Банковские выписки»: в полном — «Банк и касса → Банк».",
        context, evidence_results=[result],
    )


def test_semantic_duplicate_is_removed_but_independent_step_and_limit_remain():
    route = "Откройте раздел «Чеки» → «Поиск чеков»."
    paraphrase = "Перейдите в раздел «Чеки» → «Поиск чеков»."
    filter_step = "В дополнительных условиях задайте диапазон суммы и выберите способ оплаты."
    route_with_input = "Под ролью администратора откройте раздел «Чеки» → «Поиск чеков», введите номер ФД и подтвердите."
    assert statements_equivalent(route, paraphrase)
    assert not statements_equivalent(route, filter_step)
    assert not statements_equivalent(route, route_with_input)
    assert not statements_equivalent(
        "С версии 3.0.148 доступна загрузка выписки.",
        "В настройках взаимодействия с банком указаны все нужные счета.",
    )
    assert deduplicate_statements([route, paraphrase, filter_step]) == [route, filter_step]

    state = DialogueState(operation="search")
    notice = "Полная последовательность действий здесь не подтверждена."
    assert _coverage_notice_is_relevant(
        notice, "Не удалось подтвердить точный ответ.", state=state,
        request="Где найти чек?", context="", results=(),
    )


def test_unique_confirmed_action_is_not_lost_with_one_unconfirmed_button():
    case = next(item for item in _cases() if item["id"] == "ofd-receipt-search-182")
    _, final, _, _, _ = _replay(case)
    assert "диапазон суммы" in final and "способ оплаты" in final
    assert "Найти" not in final


def test_source_replacement_keeps_unique_input_without_repeating_the_route():
    source = (
        "Под ролью администратора откройте «Настройки → Обслуживание кассы → "
        "Дополнительные операции → Печать документа по номеру», введите номер ФД и подтвердите."
    )
    result = SearchResult(
        "evotor/cash/receipt-copy.md", source, .9,
        metadata={"section": "Действие на кассе", "operations": ["repeat_print"]},
    )
    state = DialogueState(intent="receipt", operation="repeat_print")
    answer = (
        "На кассе откройте «Настройки → Обслуживание кассы → Дополнительные операции → "
        "Печать документа по номеру». Введите сохранённый номер ФД и подтвердите."
    )
    repaired = _safe_alternative(
        answer, "unsupported_instruction", "Эвотор 6: повторно распечатать чек",
        context=source, state=state, results=[result],
    )
    assert repaired.count("Печать документа по номеру") == 1
    assert "введите номер фд" in repaired.lower() and "подтвердите" in repaired.lower()
