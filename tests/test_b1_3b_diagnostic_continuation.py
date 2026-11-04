"""B1.3b continuation contracts through bot.handle_message and SQLite reopens."""

from __future__ import annotations

import json

import pytest

from app.dialogue_state import (ActiveRoute, DialogueManager, DialogueState, Fact,
                                SessionContext, TaskContext)
from app.source_first_service import (_matching_verified_source_units, _merge_source_components,
                                      _planner_task_snapshot)
from test_telegram_pilot_sqlite_replay import ROOT, _run_replay


COMPOUND_SOURCE = "evotor/ofd/evotor-7-3-ofd-connection.md"


def test_planner_snapshot_preserves_scope_and_check_outcomes_without_full_state_history():
    source = "data/knowledge/evotor/ofd/evotor-7-3-ofd-connection.md"
    model = Fact.span("Эвотор 7.3", 1)
    session = SessionContext(
        entities={"manufacturer": [Fact.span("Эвотор", 1)]},
        active_route=ActiveRoute("manufacturer", Fact.span("Эвотор", 1)))
    long_label = ("В диагностическом отчёте проверьте состояние приложения EoU, "
                  "доступ в интернет, адрес и порт ОФД. " * 20)
    task = TaskContext(
        task_id="task:1", intent="receipt", request_type="information",
        operation="diagnose", object="ФН 235",
        entities={"equipment": [model], "component": [Fact.span("EoU", 4)]},
        symptom=Fact.span("Чеки не передаются оператору", 1),
        goals=[Fact.span("Что делать дальше?", 6)],
        procedure_id="verified-procedure-1", relation="continue",
        shown_units=[{"unit_id": "unit-a", "label": long_label, "source": source,
            "section": "Что проверить сначала", "source_verified": True,
            "model_value": "Эвотор 7.3", "source_order": {"sha256": "x" * 64,
            "context": "y" * 64}}],
        eligible_units=[{"unit_id": "unit-b", "label": long_label, "source": source,
            "section": "Что проверить сначала", "source_verified": True,
            "model_value": "Эвотор 7.3", "components": [{"component_id": "component-a",
            "label": "проверьте состояние приложения EoU"}]}],
        checks=[{"unit_id": "unit-a", "label": long_label, "status": "failed",
            "observations": [{"status": "failed", "quote": "Очередь не уменьшается",
                "message_id": 5, "start": 0, "end": 23}],
            "component_results": [{"component_id": "component-a", "status": "unknown",
                "observations": [{"status": "unknown", "quote": "EoU ещё не проверял",
                    "message_id": 5, "start": 0, "end": 20}]}]},
            {"unit_id": "legacy-unit", "label": "Проверка завершена.",
             "status": "passed", "result_span": {"quote": "Проверка завершена"},
             "observations": []}])
    state = DialogueState(session=session, task_context=task)

    compact = _planner_task_snapshot(state)

    assert compact["entities"]["equipment"] == ["Эвотор 7.3"]
    assert compact["symptom"] == "Чеки не передаются оператору"
    assert compact["shown_units"][0]["unit_id"] == "unit-a"
    assert compact["eligible_units"][0]["components"][0]["component_id"] == "component-a"
    assert compact["checks"][0]["status"] == "failed"
    assert compact["checks"][0]["observations"] == [
        {"status": "failed", "quote": "Очередь не уменьшается"}]
    assert compact["checks"][0]["component_results"][0]["observations"] == [
        {"status": "unknown", "quote": "EoU ещё не проверял"}]
    assert compact["checks"][1]["observations"] == [
        {"status": "passed", "quote": "Проверка завершена"}]
    assert "source_order" not in compact["shown_units"][0]
    assert "message_id" not in compact["checks"][0]["observations"][0]
    assert len(json.dumps(compact, ensure_ascii=False)) < len(
        json.dumps(state.to_dict()["task_context"], ensure_ascii=False)) * 0.6


def _continuation_raw(text: str, *, intent: str = "receipt") -> dict:
    return {
        "request_type": "information",
        "relation": "continue",
        "intent": intent,
        "operation": "diagnose",
        "object": None,
        "object_evidence": None,
        "goal": {"quote": text} if "?" in text else None,
        "symptom": None,
        "entities": [],
        "unknown_facts": [],
        "specialist_requested": False,
        "specialist_evidence": None,
        "confidence": 0.9,
    }


def _compound_dialogue():
    base = json.loads((ROOT / "tests/fixtures/live_compound_check_20261029.json")
                      .read_text(encoding="utf-8"))
    first = base[0]
    result_template = base[1]["provider_raw"]
    def result_case(case_id: str, text: str):
        raw = {**result_template, "goal": {"quote": text} if "?" in text else None}
        return {"id": case_id, "text": text, "provider_raw": raw}
    return [first,
        result_case("report_printed", "Диагностический отчёт напечатал."),
        result_case("internet_passed", "Интернет работает."),
        result_case("queue_failed", "Очередь неотправленных документов не уменьшается."),
        result_case("remaining_settings_passed",
                    "EoU работает. Адрес, порт и ИНН ОФД совпадают с настройками оператора.")]


def _evotor_prefix_and_result(text: str) -> list[dict]:
    opening = json.loads((ROOT / "tests/fixtures/live_compound_check_20261029.json")
                         .read_text(encoding="utf-8"))[0]
    report = {"id": "report_printed", "text": "Диагностический отчёт напечатал.",
              "provider_raw": _continuation_raw("Диагностический отчёт напечатал.")}
    result = {"id": "condition_result", "text": text,
              "provider_raw": _continuation_raw(text)}
    return [opening, report, result]


def _legacy_composite_progress_state():
    source = f"data/knowledge/{COMPOUND_SOURCE}"
    section = "Что проверить сначала"
    unit_id = "legacy-composite"
    label = ("Проверьте состояние приложения EoU, доступ в интернет, адрес и порт ОФД. "
             "Сопоставьте адрес, порт и ИНН ОФД с настройками оператора. "
             "Посмотрите, уменьшается ли очередь неотправленных документов.")
    components = [
        {"component_id": "eou-network-ofd", "label":
         "Проверьте состояние приложения EoU, доступ в интернет, адрес и порт ОФД."},
        {"component_id": "compare-ofd", "label":
         "Сопоставьте адрес, порт и ИНН ОФД с актуальными настройками своего оператора."},
        {"component_id": "queue", "label":
         "Посмотрите, уменьшается ли очередь неотправленных документов."},
    ]
    shown = {"unit_id": unit_id, "label": label, "source": source,
             "section": section, "source_verified": True,
             "components": components}
    eligible = {key: value for key, value in shown.items() if key != "components"}
    check = {"task_id": "task:1", "unit_id": unit_id, "label": label,
             "source": source, "section": section, "source_verified": True,
             "status": "asked", "asked_message_id": 1,
             "components": [], "component_results": [], "observations": []}
    task = TaskContext(task_id="task:1", intent="receipt", operation="diagnose",
        entities={"equipment": [Fact.span("Эвотор 7.3", 1)]},
        shown_units=[shown], eligible_units=[eligible], checks=[check])
    return DialogueState(task_id="task:1", task_context=task), components


def test_progress_reducer_uses_exact_shown_components_when_eligible_snapshot_is_stale():
    state, _ = _legacy_composite_progress_state()
    # Eligible snapshot is stale; its exact verified shown counterpart has the
    # current source-derived component structure.
    assert "components" not in state.task_context.eligible_units[0]
    assert state.task_context.shown_units[0]["components"]

    DialogueManager._reduce_progress(
        state, "Очередь неотправленных документов не уменьшается.", 2)

    check = state.task_context.checks[0]
    assert check["status"] == "failed"
    assert check["result_span"]["quote"] == "Очередь неотправленных документов не уменьшается"
    results = {item["component_id"]: item for item in check["component_results"]}
    assert results["queue"]["status"] == "failed"
    assert "eou-network-ofd" not in results
    assert "compare-ofd" not in results


@pytest.mark.parametrize(("message", "expected_statuses", "expected_quotes"), [
    ("EoU работает, интернет работает, адрес, порт и ИНН ОФД совпадают с актуальными настройками оператора",
     {"eou-network-ofd": "passed", "compare-ofd": "passed", "queue": None},
     {"eou-network-ofd": {"EoU работает", "интернет работает",
                          "адрес, порт и ИНН ОФД совпадают с актуальными настройками оператора"},
      "compare-ofd": {"адрес, порт и ИНН ОФД совпадают с актуальными настройками оператора"}}),
    ("EoU работает, интернет работает",
     {"eou-network-ofd": "unknown", "compare-ofd": None, "queue": None},
     {"eou-network-ofd": {"EoU работает", "интернет работает"}}),
    ("Адрес и порт совпадают с настройками оператора",
     {"eou-network-ofd": "unknown", "compare-ofd": "unknown", "queue": None},
     {"eou-network-ofd": {"Адрес и порт совпадают с настройками оператора"},
      "compare-ofd": {"Адрес и порт совпадают с настройками оператора"}}),
])
def test_progress_reducer_keeps_multiple_and_partial_component_results(
        message, expected_statuses, expected_quotes):
    state, _ = _legacy_composite_progress_state()

    DialogueManager._reduce_progress(state, message, 2)

    check = state.task_context.checks[0]
    results = {item["component_id"]: item for item in check["component_results"]}
    for component_id, expected in expected_statuses.items():
        if expected is None:
            assert component_id not in results
        else:
            assert results[component_id]["status"] == expected
    for component_id, quotes in expected_quotes.items():
        saved = {item["quote"] for item in results[component_id]["observations"]}
        assert saved == quotes
        for item in results[component_id]["observations"]:
            assert item["quote"] in message
    if message.startswith("Адрес"):
        assert "инн" not in " ".join(item["quote"].casefold()
                                      for item in results["compare-ofd"]["observations"])
        assert results["compare-ofd"]["status"] != "passed"


def test_conflicting_results_for_same_topic_remain_unknown_and_separate_checks_do_not_conflict():
    state, _ = _legacy_composite_progress_state()
    DialogueManager._reduce_progress(state, "EoU работает, EoU не работает.", 2)
    check = state.task_context.checks[0]
    eou_result = next(item for item in check["component_results"]
                      if item["component_id"] == "eou-network-ofd")
    assert [item["quote"] for item in eou_result["observations"]] == [
        "EoU работает", "EoU не работает"]
    assert eou_result["status"] == "unknown"
    assert eou_result["contradictions"]

    state, _ = _legacy_composite_progress_state()
    DialogueManager._reduce_progress(
        state, "Очередь неотправленных документов не уменьшается.", 2)
    DialogueManager._reduce_progress(
        state, "EoU работает, интернет работает, адрес, порт и ИНН ОФД совпадают с актуальными настройками оператора.", 3)
    check = state.task_context.checks[0]
    assert check["status"] == "failed"
    assert not check.get("contradictions")
    assert next(item for item in check["component_results"]
                if item["component_id"] == "queue")["status"] == "failed"
    assert next(item for item in check["component_results"]
                if item["component_id"] == "eou-network-ofd")["status"] == "passed"


def test_source_component_backfill_does_not_attach_generic_shared_words_to_multiple_checks():
    source = f"data/knowledge/{COMPOUND_SOURCE}"
    section = "Что проверить сначала"
    label = "Проверьте настройки оператора и настройки терминала."
    components = [
        {"component_id": "operator-settings", "label": "Проверьте настройки оператора."},
        {"component_id": "terminal-settings", "label": "Проверьте настройки терминала."},
    ]
    unit = {"unit_id": "verified-unit", "label": label, "source": source,
        "section": section, "source_verified": True, "components": components}
    check = {"task_id": "task:1", "unit_id": "verified-unit", "label": label,
        "source": source, "section": section, "source_verified": True,
        "status": "passed", "observations": [{"status": "passed",
            "message_id": 2, "quote": "Настройки совпадают", "start": 0, "end": 19}],
        "component_results": []}
    state = DialogueState(task_context=TaskContext(task_id="task:1",
        shown_units=[unit], eligible_units=[unit], checks=[check]))

    _merge_source_components(state, [unit], source, section)

    assert all(not result["observations"] for result in check["component_results"])
    assert all(result["status"] is None for result in check["component_results"])


def test_multiple_component_results_survive_bot_sqlite_reopen(monkeypatch, tmp_path):
    cases = _compound_dialogue()
    cases[-1] = {**cases[-1], "id": "all_remaining_checks_passed",
        "text": ("EoU работает, интернет работает, адрес, порт и ИНН ОФД "
                 "совпадают с актуальными настройками оператора"),
        "provider_raw": _continuation_raw(
            "EoU работает, интернет работает, адрес, порт и ИНН ОФД "
            "совпадают с актуальными настройками оператора")}
    trace = _run_replay(monkeypatch, tmp_path, cases,
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True)
    final = trace[-1]
    assert "state_after_sqlite_reopen" in final
    task = final["state_after_sqlite_reopen"]["task_context"]
    saved_quotes = {item.get("quote") for check in task["checks"]
        for item in [*check.get("observations", []),
                     *(obs for result in check.get("component_results", [])
                       for obs in result.get("observations", []))]}
    assert {"EoU работает", "интернет работает",
            "адрес, порт и ИНН ОФД совпадают с актуальными настройками оператора",
            "Очередь неотправленных документов не уменьшается"} <= saved_quotes, json.dumps(
                {"saved_quotes": sorted(saved_quotes), "checks": task["checks"],
                 "shown": task["shown_units"]}, ensure_ascii=True)
    compare_result = next((result for check in task["checks"]
        for result in check.get("component_results", [])
        if result.get("component_id") == "83e8d9224a8c1c77bc94"), None)
    if compare_result:
        assert compare_result["status"] == "passed"
    assert all(not check.get("contradictions")
               for check in task["checks"] if check.get("component_results"))


@pytest.mark.parametrize(("case_id", "message", "required", "forbidden", "reason"), [
    ("internet_absent", "Интернет отсутствует.", "восстановите сетевое подключение",
     "сопоставьте адрес, порт", "progress_ledger_next_approved_check"),
    ("internet_works", "Интернет работает.", "сопоставьте адрес, порт и ИНН ОФД",
     "восстановите сетевое подключение", "progress_ledger_next_approved_check"),
    ("eou_failed_internet_works", "EoU не работает. Интернет работает.",
     "сопоставьте адрес, порт и ИНН ОФД", "восстановите сетевое подключение",
     "progress_ledger_next_approved_check"),
    ("internet_unknown", "Не знаю, есть ли интернет.", "есть или отсутствует",
     "восстановите сетевое подключение", "progress_ledger_conditional_context_unknown"),
    ("internet_contradictory", "Интернет работает. Интернет отсутствует.",
     "есть или отсутствует", "восстановите сетевое подключение",
     "progress_ledger_conditional_context_unknown"),
])
def test_evotor_internet_condition_matrix_uses_only_confirmed_source_branch(
        monkeypatch, tmp_path, case_id, message, required, forbidden, reason):
    trace = _run_replay(monkeypatch, tmp_path, _evotor_prefix_and_result(message),
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True)
    answer = trace[2]
    assert answer["reason"] == reason, case_id
    assert required.casefold() in answer["final_reply"].casefold(), case_id
    assert forbidden not in answer["final_reply"].casefold(), case_id
    assert answer["stage_call_counts"]["planner"] == 1
    assert answer["coordinator_decision"]["route"] == "technical_action"
    assert answer["state_after_sqlite_reopen"]["task_context"]["task_id"] == "task:1"


def test_evotor_address_mismatch_does_not_claim_support_boundary_or_network_failure(
        monkeypatch, tmp_path):
    mismatch = "EoU работает. Адрес, порт и ИНН ОФД не совпадают."
    cases = _evotor_prefix_and_result("Интернет работает.") + [
        {"id": "settings_mismatch", "text": mismatch,
         "provider_raw": _continuation_raw(mismatch)},
    ]
    trace = _run_replay(monkeypatch, tmp_path, cases,
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True)
    answer = trace[3]
    assert answer["reason"] == "progress_ledger_known_issue_without_approved_next_step"
    assert "не совпадают" not in answer["final_reply"].casefold()
    assert "в подтверждённой инструкции нет следующего действия" in answer["final_reply"].casefold()
    assert "запросите специалиста" in answer["final_reply"].casefold()
    assert "поддержку эвотора" not in answer["final_reply"].casefold()
    assert "восстановите сетевое подключение" not in answer["final_reply"].casefold()
    saved = answer["state_after_sqlite_reopen"]["task_context"]
    mismatch_quote = "Адрес, порт и ИНН ОФД не совпадают"
    assert not any(mismatch_quote in (check.get("result_span") or {}).get("quote", "")
                   for check in saved["checks"]
                   if "сопоставьте адрес" not in check.get("label", ""))


REAL_ACTION_SOURCES = [
    pytest.param(
        "goods", "aqsi_devices/errors/goods-not-on-device.md",
        "На aQsi (физическая ККТ) товары из кабинета не видны на кассе. Что проверить?",
        "товары", "aQsi", "aQsi (физическая ККТ)",
        "Проверенная информация", "убедитесь", 1, id="aqsi-goods-убедитесь"),
    pytest.param(
        "fn7", "aqsi_devices/errors/fn7-date.md",
        "На aQsi (физическая ККТ) ошибка ФН 7: неверные дата и время. Что проверить?",
        "ФН 7", "aQsi", "aQsi (физическая ККТ)",
        "Проверенная информация", "сравните", 2, id="aqsi-fn7-сравните"),
    pytest.param(
        "fn235", "evotor/fn/fn-235.md",
        "На Эвотор 7.3 ошибка ФН 235, документы ждут отправки в ОФД. Что проверить?",
        "ФН 235", "Эвотор", "Эвотор 7.3",
        "Смысл и безопасная проверка", "убедитесь", 1, id="evotor-fn235-убедитесь"),
]


def _real_source_case(case_id, text, obj, manufacturer, equipment):
    equipment_quote = equipment if equipment in text else manufacturer
    raw = {"request_type": "diagnosis", "relation": "new_task", "intent": "device",
        "operation": "diagnose", "object": obj, "object_evidence": {"quote": obj},
        "goal": {"quote": "Что проверить?"},
        "symptom": {"quote": text.split(" Что проверить?")[0]},
        "entities": [
            {"slot": "manufacturer", "value": manufacturer,
             "evidence": {"quote": manufacturer}},
            {"slot": "equipment", "value": equipment,
             "evidence": {"quote": equipment_quote}},
        ], "unknown_facts": [], "specialist_requested": False,
        "specialist_evidence": None, "confidence": 0.95}
    return {"id": case_id, "text": text, "provider_raw": raw}


@pytest.mark.parametrize(
    ("case_id", "source", "text", "obj", "manufacturer", "equipment",
     "section", "verb", "component_count"), REAL_ACTION_SOURCES)
def test_real_approved_source_action_components_survive_bot_sqlite_reopen_and_are_stable(
        monkeypatch, tmp_path, case_id, source, text, obj, manufacturer,
        equipment, section, verb, component_count):
    case = _real_source_case(case_id, text, obj, manufacturer, equipment)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()

    first_mp = pytest.MonkeyPatch()
    first = _run_replay(first_mp, first_root, [case], sources=(source,),
        coordinator_enabled=True, planner_section_contains=section)[0]
    first_mp.undo()
    second_mp = pytest.MonkeyPatch()
    second = _run_replay(second_mp, second_root, [case], sources=(source,),
        coordinator_enabled=True, planner_section_contains=section)[0]
    second_mp.undo()

    first_task = first["state_after_sqlite_reopen"]["task_context"]
    second_task = second["state_after_sqlite_reopen"]["task_context"]
    assert source in first["final_reply"]
    assert first_task["procedure_id"] is not None
    eligible = [item for item in first_task["eligible_units"]
                if item.get("source", "").endswith(source)]
    assert eligible
    components = [component for unit in eligible for component in unit.get("components", [])]
    assert any(verb in item["label"].casefold() for item in components)
    assert all(len(unit["components"]) == component_count
               for unit in eligible if verb in unit["label"].casefold())

    first_ids = [(unit["unit_id"], [(item["component_id"], item["label"])
                                    for item in unit.get("components", [])])
                 for unit in eligible]
    second_ids = [(unit["unit_id"], [(item["component_id"], item["label"])
                                     for item in unit.get("components", [])])
                  for unit in second_task["eligible_units"]
                  if unit.get("source", "").endswith(source)]
    assert first_ids == second_ids

    if case_id == "goods":
        first_check = next(item for item in eligible if "убедитесь" in item["label"].casefold())
        assert len(first_check["components"]) == 1
        assert "проверьте привязку категорий" not in first_check["components"][0]["label"].casefold()
    elif case_id == "fn7":
        compare = next(item for item in eligible if "сравните" in item["label"].casefold())
        labels = [item["label"].casefold() for item in compare["components"]]
        assert any("сравните" in label for label in labels)
        assert any("проверьте синхронизацию" in label for label in labels)
        assert not any("откройте настройки" in label for label in labels)
    else:
        check_index = next(index for index, item in enumerate(eligible)
                           if "проверьте количество" in item["label"].casefold())
        after_restore = next(item for item in eligible[check_index + 1:]
                             if "убедитесь" in item["label"].casefold())
        assert len(after_restore["components"]) == 1
        assert "восстановите связь" not in after_restore["components"][0]["label"].casefold()


def test_real_aqsi_result_is_saved_only_on_shown_check_after_sqlite_reopen(
        monkeypatch, tmp_path):
    source = "aqsi_devices/errors/goods-not-on-device.md"
    opening = _real_source_case("goods", "На aQsi (физическая ККТ) товары из кабинета не видны на кассе. Что проверить?",
        "товары", "aQsi", "aQsi (физическая ККТ)")
    result_text = "Интернет работает, касса привязана к правильному магазину."
    trace = _run_replay(monkeypatch, tmp_path, [opening,
        {"id": "first_check_passed", "text": result_text,
         "provider_raw": _continuation_raw(result_text, intent="device")}],
        sources=(source,), coordinator_enabled=True,
        planner_section_contains="Проверенная информация")
    saved = trace[1]["state_after_sqlite_reopen"]["task_context"]
    shown_ids = {item["unit_id"] for item in saved["shown_units"]}
    result_checks = [item for item in saved["checks"]
                     if item.get("result_span", {}).get("quote")]
    assert saved["procedure_id"] is not None
    assert result_checks
    assert all(item["unit_id"] in shown_ids for item in result_checks)
    assert all(item["result_span"]["quote"] in result_text for item in result_checks)
    assert not any("категорий" in item.get("label", "").casefold()
                   and item["unit_id"] not in shown_ids for item in result_checks)


def test_failed_composite_asks_only_unreported_source_components_and_keeps_quotes(
        monkeypatch, tmp_path):
    trace = _run_replay(monkeypatch, tmp_path, _compound_dialogue(),
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True)

    failed_turn = trace[3]
    task = failed_turn["state_after_sqlite_reopen"]["task_context"]
    check = next(item for item in task["checks"] if item["status"] == "failed")
    failed_quote = "Очередь неотправленных документов не уменьшается"
    assert check.get("result_span", {}).get("quote") == failed_quote, json.dumps(
        {"checks": task["checks"], "shown": task["shown_units"],
         "eligible": task["eligible_units"]}, ensure_ascii=True)
    assert check["result_span"]["quote"] in failed_turn["user_text"]
    assert len(check["components"]) == 2
    assert any(item["status"] == "failed" and item["result_span"]["quote"] == failed_quote
               for item in check["component_results"])
    assert failed_turn["reason"] == "progress_ledger_failed_composite_needs_remaining_results"
    assert "Осталось сообщить результаты пунктов инструкции" in failed_turn["final_reply"]
    assert "сопоставьте адрес, порт и ИНН ОФД" in failed_turn["final_reply"]
    assert "восстановите сетевое подключение" not in failed_turn["final_reply"]
    assert "уменьшается ли очередь" not in failed_turn["final_reply"]
    assert "Настройки → Обслуживание кассы → Диагностика" not in failed_turn["final_reply"]

    completed = trace[4]["state_after_sqlite_reopen"]["task_context"]
    completed_check = next(item for item in completed["checks"] if item["status"] == "failed")
    queue_result = next(item for item in completed_check["component_results"]
                        if item["status"] == "failed")
    compare_result = next(item for item in completed_check["component_results"]
                          if "сопоставьте адрес" in item.get("label", ""))
    assert queue_result["result_span"]["quote"] == failed_quote
    assert any(item["status"] == "passed" and "Адрес, порт и ИНН" in item["quote"]
               for item in compare_result["observations"])
    for result in completed_check["component_results"]:
        message = failed_turn["user_text"] if result["status"] == "failed" else trace[4]["user_text"]
        assert result["result_span"]["quote"] in message
    final_check = next(item for item in trace[4]["state_after_sqlite_reopen"]["task_context"]["checks"]
                       if item["status"] == "failed")
    assert final_check["component_results"] == completed_check["component_results"]
    assert trace[4]["reason"] == "progress_ledger_conditional_source_boundary"
    assert "поддержку Эвотора" in trace[4]["final_reply"]
    assert "Настройки → Обслуживание кассы → Диагностика" not in trace[4]["final_reply"]


def test_b1_3a_legacy_composite_checkpoint_backfills_split_source_components(
        monkeypatch, tmp_path):
    cases = _compound_dialogue()[:2] + [
        {"id": "queue_failed", "text": "Очередь неотправленных документов не уменьшается.",
         "provider_raw": _continuation_raw("Очередь неотправленных документов не уменьшается.")},
    ]
    legacy_label = (
        "В нём проверьте состояние приложения EoU, доступ в интернет, адрес и порт ОФД. "
        "Если интернет отсутствует, восстановите сетевое подключение. "
        "Если интернет есть, сопоставьте адрес, порт и ИНН ОФД с актуальными настройками "
        "своего оператора, затем посмотрите, уменьшается ли очередь неотправленных документов. "
        "Если базовые проверки не выявили причину, передайте диагностический отчёт "
        "в поддержку Эвотора. Низкоуровневые команды и технологическое обнуление "
        "в этот краткий конспект не включены.")
    legacy_source = f"data/knowledge/{COMPOUND_SOURCE}"

    def restore_legacy_checkpoint(turn, store, conversation_id):
        if turn != 3:
            return
        state = store.dialogue_state(conversation_id)
        task = state.task_context
        old_check = next(item for item in task.checks if item.get("status") == "asked")
        old_unit = next(item for item in task.shown_units
                        if item.get("unit_id") == old_check.get("unit_id"))
        old_check.update({"unit_id": "7ecc73b5ecb8e7125d80", "label": legacy_label,
                          "source": legacy_source, "section": "Что проверить сначала",
                          "source_verified": True})
        old_check.pop("components", None)
        old_check.pop("component_results", None)
        old_unit.update({"unit_id": old_check["unit_id"], "label": legacy_label,
                         "source": legacy_source, "section": "Что проверить сначала",
                         "source_verified": True})
        old_unit.pop("components", None)
        for unit in task.eligible_units:
            if unit.get("unit_id") == old_check["unit_id"]:
                unit.update({"label": legacy_label, "source": legacy_source,
                             "section": "Что проверить сначала", "source_verified": True})
                unit.pop("components", None)
        with store.connect() as db:
            db.execute("UPDATE dialogue_states_v2 SET state_json=? WHERE conversation_id=?",
                       (json.dumps(state.to_dict(), ensure_ascii=False), conversation_id))

    trace = _run_replay(monkeypatch, tmp_path, cases,
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True,
        before_turn=restore_legacy_checkpoint)

    negative = trace[2]
    assert negative["reason"] == "progress_ledger_failed_composite_needs_remaining_results"
    assert "сопоставьте адрес, порт и ИНН ОФД" in negative["final_reply"]
    assert "Настройки → Обслуживание кассы → Диагностика" not in negative["final_reply"]
    saved_negative = negative["state_after_sqlite_reopen"]["task_context"]
    legacy_check = next(item for item in saved_negative["checks"]
                        if item.get("unit_id") == "7ecc73b5ecb8e7125d80")
    assert len(legacy_check["components"]) >= 2
    assert any(item.get("status") == "failed" and "Очередь" in item.get("result_span", {}).get("quote", "")
               for item in legacy_check["component_results"])


def test_unknown_shown_check_blocks_later_instruction_until_its_result_is_known(
        monkeypatch, tmp_path):
    next_question = "Что делать дальше?"
    cases = _compound_dialogue()[:3] + [{
        "id": "what_next_with_unknown_check", "text": next_question,
        "provider_raw": _continuation_raw(next_question)}]

    def resume_before_unreached_conditional(index, store, conversation_id):
        if index != 4:
            return
        state = store.dialogue_state(conversation_id)
        task = state.task_context
        unknown_check = next((check for check in reversed(task.checks)
            if check.get("status") == "unknown" and any(
                "Интернет работает" in item.get("quote", "")
                for item in check.get("observations", []))), None)
        assert unknown_check is not None
        shown_ids = {str(unknown_check["unit_id"])}
        index_of_check = next(i for i, unit in enumerate(task.shown_units)
                              if str(unit.get("unit_id")) == str(unknown_check["unit_id"]))
        task.shown_units = task.shown_units[:index_of_check + 1]
        shown_ids.update(str(unit.get("unit_id")) for unit in task.shown_units)
        task.checks = [check for check in task.checks
                       if str(check.get("unit_id")) in shown_ids]
        with store.connect() as db:
            db.execute("UPDATE dialogue_states_v2 SET state_json=? WHERE conversation_id=?",
                       (json.dumps(state.to_dict(), ensure_ascii=False), conversation_id))

    trace = _run_replay(monkeypatch, tmp_path, cases,
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True, validate_with_state=True,
        before_turn=resume_before_unreached_conditional)

    final = trace[-1]
    assert final["reason"] == "progress_ledger_waiting_for_check_result"
    assert "не хватает результата" in final["final_reply"].casefold()
    assert "сопоставьте адрес, порт и инн" not in final["final_reply"].casefold()
    assert "уменьшается ли очередь" not in final["final_reply"].casefold()
    assert final["state_after_sqlite_reopen"]["task_context"]["task_id"] == "task:1"


@pytest.mark.parametrize("classified_operation", ["request_specialist", "explain"])
def test_continuation_keeps_model_when_provider_mistypes_eou_and_asks_what_next(
        monkeypatch, tmp_path, classified_operation):
    cases = _compound_dialogue()
    followup = ("EoU работает. Адрес, порт и ИНН ОФД совпадают с настройками оператора. "
                "Очередь всё ещё не уменьшается. Что делать дальше?")
    raw = _continuation_raw(followup)
    raw["operation"] = classified_operation
    raw["entities"] = [{"slot": "equipment", "value": "EoU",
                        "evidence": {"quote": "EoU"}}]
    cases[-1] = {**cases[-1], "id": "eou_typed_as_equipment_and_what_next",
                 "text": followup, "provider_raw": raw}

    trace = _run_replay(monkeypatch, tmp_path, cases,
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True, validate_with_state=True)

    final = trace[-1]
    task = final["state_after_sqlite_reopen"]["task_context"]
    assert final["reason"] == "progress_ledger_conditional_source_boundary"
    assert task["task_id"] == "task:1"
    assert task["entities"]["equipment"][0]["value"] == "Эвотор 7.3"
    assert task["entities"]["component"][0]["value"] == "EoU"
    assert "поддержку Эвотора" in final["final_reply"]
    assert "не нашёл подтверждения, что этот approved-раздел подходит" not in final["final_reply"]


def test_legacy_sqlite_backfills_only_exact_shown_components_and_keeps_results_separate(
        monkeypatch, tmp_path):
    cases = _compound_dialogue()[:2] + [
        {"id": "internet_passed", "text": "Интернет работает.",
         "provider_raw": _continuation_raw("Интернет работает.")},
        {"id": "eou_and_settings_passed", "text":
         "EoU работает. Адрес, порт и ИНН ОФД совпадают.",
         "provider_raw": _continuation_raw("EoU работает. Адрес, порт и ИНН ОФД совпадают.")},
        {"id": "queue_not_decreasing", "text": "Очередь не уменьшается.",
         "provider_raw": _continuation_raw("Очередь не уменьшается.")},
    ]

    def strip_new_metadata_from_legacy_checkpoint(turn, store, conversation_id):
        if turn != 3:
            return
        with store.connect() as db:
            row = db.execute("SELECT state_json FROM dialogue_states_v2 WHERE conversation_id=?",
                             (conversation_id,)).fetchone()
            state = json.loads(row["state_json"])
            task = state["task_context"]
            for key in ("shown_units", "eligible_units", "checks"):
                for item in task.get(key, []):
                    item.pop("components", None)
                    item.pop("component_results", None)
            db.execute("UPDATE dialogue_states_v2 SET state_json=? WHERE conversation_id=?",
                       (json.dumps(state, ensure_ascii=False), conversation_id))

    trace = _run_replay(monkeypatch, tmp_path, cases,
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True,
        before_turn=strip_new_metadata_from_legacy_checkpoint)

    backfilled = trace[2]["state_after_sqlite_reopen"]["task_context"]
    diagnostic_check = next(item for item in backfilled["checks"]
                            if "EoU" in item.get("label", ""))
    assert len(diagnostic_check["components"]) == 1
    assert len(diagnostic_check["component_results"]) == 1
    assert any(item["quote"] == "Интернет работает" and item["status"] == "passed"
               for item in diagnostic_check["component_results"][0]["observations"])
    assert "сопоставьте адрес, порт и ИНН ОФД" in trace[2]["final_reply"]

    reported = trace[3]["state_after_sqlite_reopen"]["task_context"]
    printed_check = next(item for item in reported["checks"]
                         if item["unit_id"] == "f09c43177d5a42267fe0")
    assert printed_check["result_span"]["quote"] == "Диагностический отчёт напечатал"
    final = trace[4]
    assert final["reason"] == "progress_ledger_conditional_source_boundary"
    final_task = final["state_after_sqlite_reopen"]["task_context"]
    composite = next(item for item in final_task["checks"]
                     if len(item.get("component_results", [])) == 2)
    outcomes = {item["component_id"]: item["status"]
                for item in composite["component_results"]}
    assert set(outcomes.values()) == {"passed", "failed"}
    assert "поддержку эвотора" in final["final_reply"].casefold()
    final_compare = next(item for item in final["state_after_sqlite_reopen"]["task_context"]["checks"]
                         if "сопоставьте адрес" in item.get("label", ""))
    assert any("Очередь" in observation["quote"] and observation["status"] == "failed"
               for item in final_compare["component_results"]
               for observation in item.get("observations", []))


def test_failed_single_check_uses_next_ordered_approved_step(monkeypatch, tmp_path):
    followup = "Раздел поиска чеков в кабинете ОФД не работает."
    cases = [
        {**json.loads((ROOT / "tests/fixtures/live_compound_check_20261029.json")
                      .read_text(encoding="utf-8"))[0]},
        {"id": "single_check_failed", "text": followup,
         "provider_raw": _continuation_raw(followup)},
    ]
    root = tmp_path / "approved_fixture_root"
    source_path = root / "data/knowledge/test/single-check-next.md"
    source_path.parent.mkdir(parents=True)
    source_text = """---
document_id: fixture-single-check-next
title: "Эвотор 7.3: диагностика, если чеки не отправляются в ОФД"
category: ofd
service: "Эвотор"
task_category: receipt_transmission
operations: [check_transmission]
manufacturer: "Эвотор"
model:
verified_at: "2026-11-03"
status: approved
---

# Эвотор 7.3 не отправляет чеки в ОФД

## Безопасные проверки
1. Проверьте, доступен ли раздел поиска чеков в кабинете ОФД.
2. Проверьте доступность сетевого соединения кассы.
"""
    source_path.write_text(source_text, encoding="utf-8")
    trace = _run_replay(monkeypatch, tmp_path, cases,
        sources=("test/single-check-next.md",), coordinator_enabled=True,
        source_root=root)

    failed = trace[1]
    state = failed["state_after_sqlite_reopen"]["task_context"]
    first = state["checks"][0]
    assert first["status"] == "failed"
    assert len(first["components"]) == 1
    assert first["result_span"]["quote"] == followup.rstrip(".")
    assert failed["reason"] == "progress_ledger_next_approved_check"
    assert "Проверьте доступность сетевого соединения кассы." in failed["final_reply"]
    assert "остальным пунктам" not in failed["final_reply"].casefold()
    assert len(state["shown_units"]) == 2


def test_failed_single_check_without_next_step_is_reported_honestly(monkeypatch, tmp_path):
    first = json.loads((ROOT / "tests/fixtures/live_compound_check_20261029.json")
                       .read_text(encoding="utf-8"))[0]
    followup = "Раздел поиска чеков в кабинете ОФД не работает."
    cases = [first, {"id": "only_check_failed", "text": followup,
                     "provider_raw": _continuation_raw(followup)}]
    root = tmp_path / "approved_fixture_root"
    source_path = root / "data/knowledge/test/single-check-no-next.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("""---
document_id: fixture-single-check-no-next
title: "Тестовая одиночная проверка"
category: ofd
service: "Эвотор"
task_category: receipt_transmission
operations: [check_transmission]
manufacturer: "Эвотор"
model:
verified_at: "2026-11-03"
status: approved
---

# Проверка передачи

## Безопасные проверки
1. Проверьте, доступен ли раздел поиска чеков в кабинете ОФД.
""", encoding="utf-8")
    trace = _run_replay(monkeypatch, tmp_path, cases,
        sources=("test/single-check-no-next.md",), coordinator_enabled=True,
        source_root=root)

    failed = trace[1]
    assert failed["reason"] == "progress_ledger_failed_atomic_no_next_check"
    assert "нет следующего шага" in failed["final_reply"]
    assert "остальных пунктов" not in failed["final_reply"].casefold()


def test_composite_failure_without_saved_quote_does_not_invent_one(
        monkeypatch, tmp_path):
    cases = _compound_dialogue()[:4] + [
        {"id": "what_next", "text": "Что делать дальше?",
         "provider_raw": _continuation_raw("Что делать дальше?")}
    ]
    def clear_failed_result_quote(turn, store, conversation_id):
        if turn != 5:
            return
        with store.connect() as db:
            row = db.execute("SELECT state_json FROM dialogue_states_v2 WHERE conversation_id=?",
                             (conversation_id,)).fetchone()
            state = json.loads(row["state_json"])
            check = next(item for item in state["task_context"]["checks"]
                         if item.get("status") == "failed")
            check["result_span"] = None
            check["observations"] = []
            for result in check.get("component_results", []):
                result["status"] = None
                result["result_span"] = None
                result["observations"] = []
            db.execute("UPDATE dialogue_states_v2 SET state_json=? WHERE conversation_id=?",
                       (json.dumps(state, ensure_ascii=False), conversation_id))

    trace = _run_replay(monkeypatch, tmp_path, cases,
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True,
        before_turn=clear_failed_result_quote)

    question = trace[4]["final_reply"]
    check = next(item for item in trace[4]["state_after_sqlite_reopen"]["task_context"]["checks"]
                 if "сопоставьте адрес" in item.get("label", ""))
    assert check.get("status") == "failed"
    assert check.get("result_span") is None
    assert not any((item.get("result_span") or {}).get("quote") ==
                   "Очередь неотправленных документов не уменьшается"
                   for item in check.get("component_results", []))
    assert "Зафиксировал отрицательный результат («" not in question
    assert "Очередь неотправленных документов не уменьшается" not in question
    assert "Осталось сообщить результаты пунктов инструкции" in question
    assert "сопоставьте адрес, порт и ИНН ОФД" in question
    assert "уменьшается ли очередь" in question
    assert "После этого выберу следующую подтверждённую инструкцией ветку." in question


def test_new_task_does_not_inherit_old_model_or_diagnostic_checks(monkeypatch, tmp_path):
    opening = json.loads((ROOT / "tests/fixtures/live_compound_check_20261029.json")
                         .read_text(encoding="utf-8"))[0]
    printed = {"id": "printed", "text": "Диагностический отчёт напечатал.",
               "provider_raw": _continuation_raw("Диагностический отчёт напечатал.")}
    new_text = "На АТОЛ 30Ф чеки тоже не доходят до ОФД."
    new_task = {"id": "atol_new_task", "text": new_text, "provider_raw": {
        "request_type": "diagnosis", "relation": "new_task", "intent": "device",
        "operation": "diagnose", "object": "чеки", "object_evidence": {"quote": "чеки"},
        "goal": None, "symptom": {"quote": "чеки тоже не доходят до ОФД"},
        "entities": [
            {"slot": "manufacturer", "value": "АТОЛ", "evidence": {"quote": "АТОЛ"}},
            {"slot": "equipment", "value": "АТОЛ 30Ф", "evidence": {"quote": "АТОЛ 30Ф"}}],
        "unknown_facts": [], "specialist_requested": False,
        "specialist_evidence": None, "confidence": 0.9}}
    trace = _run_replay(monkeypatch, tmp_path, [opening, printed, new_task],
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True)

    before = trace[1]["state_after_sqlite_reopen"]["task_context"]
    after = trace[2]["state_after_sqlite_reopen"]
    task = after["task_context"]
    assert before["checks"]
    assert after["task_id"] != trace[1]["state_after_sqlite_reopen"]["task_id"]
    assert task["checks"] == []
    assert [fact["value"] for fact in task["entities"]["equipment"]] == ["АТОЛ 30Ф"]
    assert [fact["value"] for fact in task["entities"]["manufacturer"]] == ["АТОЛ"]
    assert "Эвотор 7.3" not in json.dumps(task, ensure_ascii=False)
    assert task["symptom"]["quote"] == "чеки тоже не доходят до ОФД"


def test_verified_legacy_composite_marks_exact_split_source_units_as_shown():
    source, section = "data/knowledge/example.md", "Approved"
    units = [
        {"unit_id": "first", "label": "Проверьте связь.", "source": source, "section": section},
        {"unit_id": "second", "label": "Сопоставьте настройки.", "source": source, "section": section},
        {"unit_id": "third", "label": "Передайте отчёт.", "source": source, "section": section},
    ]
    shown = {"unit_id": "old-composite", "label": "Проверьте связь. Сопоставьте настройки.",
             "source": source, "section": section, "source_verified": True}
    assert [u["unit_id"] for u in _matching_verified_source_units(shown, units, source, section)] == ["first", "second"]
    assert not _matching_verified_source_units({**shown, "source_verified": False}, units, source, section)
    assert not _matching_verified_source_units({**shown, "section": "Other"}, units, source, section)
    assert not _matching_verified_source_units({**shown, "label": "Проверьте связь."}, units, source, section)


def test_ambiguous_feedback_asks_result_of_current_shown_check(monkeypatch, tmp_path):
    opening = _compound_dialogue()[0]
    raw = {**_continuation_raw("Проверил."), "request_type": "feedback"}
    trace = _run_replay(monkeypatch, tmp_path,
        [opening, {"id": "ambiguous_feedback", "text": "Проверил.", "provider_raw": raw}],
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True)
    final = trace[-1]
    assert final["final_reply"] == "Удалось выполнить показанную проверку и каков её результат?"
    assert final["state_after_sqlite_reopen"]["task_context"]["checks"][-1]["status"] in {"asked", "unknown"}
