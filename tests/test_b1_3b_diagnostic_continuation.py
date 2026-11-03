"""B1.3b continuation contracts through bot.handle_message and SQLite reopens."""

from __future__ import annotations

import json

from test_telegram_pilot_sqlite_replay import ROOT, _run_replay


COMPOUND_SOURCE = "evotor/ofd/evotor-7-3-ofd-connection.md"


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
        result_case("queue_failed", "Очередь неотправленных документов не уменьшается."),
        result_case("remaining_results",
                    "EoU работает, интернет работает, адрес, порт и ИНН ОФД совпадают с настройками оператора."),
        result_case("what_next", "Что делать дальше?")]


def test_failed_composite_asks_only_unreported_source_components_and_keeps_quotes(
        monkeypatch, tmp_path):
    trace = _run_replay(monkeypatch, tmp_path, _compound_dialogue(),
        sources=(COMPOUND_SOURCE,), coordinator_enabled=True)

    failed_turn = trace[2]
    task = failed_turn["state_after_sqlite_reopen"]["task_context"]
    check = next(item for item in task["checks"] if item["status"] == "failed")
    failed_quote = "Очередь неотправленных документов не уменьшается"
    assert check["result_span"]["quote"] == failed_quote
    assert check["result_span"]["quote"] in failed_turn["user_text"]
    assert len(check["components"]) > 1
    assert any(item["status"] == "failed" and item["result_span"]["quote"] == failed_quote
               for item in check["component_results"])
    assert failed_turn["reason"] == "progress_ledger_failed_composite_needs_remaining_results"
    assert "Осталось сообщить результаты пунктов инструкции" in failed_turn["final_reply"]
    assert "проверьте состояние приложения EoU" in failed_turn["final_reply"]
    assert "сопоставьте адрес, порт и ИНН ОФД" in failed_turn["final_reply"]
    assert "уменьшается ли очередь" not in failed_turn["final_reply"]
    assert "Настройки → Обслуживание кассы → Диагностика" not in failed_turn["final_reply"]

    completed = trace[3]["state_after_sqlite_reopen"]["task_context"]
    completed_check = next(item for item in completed["checks"] if item["status"] == "failed")
    outcomes = {item["status"] for item in completed_check["component_results"]}
    assert outcomes == {"passed", "failed"}
    for result in completed_check["component_results"]:
        message = failed_turn["user_text"] if result["status"] == "failed" else trace[3]["user_text"]
        assert result["result_span"]["quote"] in message
    final_check = next(item for item in trace[4]["state_after_sqlite_reopen"]["task_context"]["checks"]
                       if item["status"] == "failed")
    assert final_check["component_results"] == completed_check["component_results"]
    assert trace[4]["reason"] == "progress_ledger_conditional_source_boundary"
    assert "поддержку Эвотора" in trace[4]["final_reply"]
    assert "Настройки → Обслуживание кассы → Диагностика" not in trace[4]["final_reply"]


def test_legacy_sqlite_backfills_only_exact_shown_components_and_keeps_results_separate(
        monkeypatch, tmp_path):
    cases = _compound_dialogue()

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

    failed_turn = trace[2]
    reopened = failed_turn["state_after_sqlite_reopen"]["task_context"]
    check = next(item for item in reopened["checks"] if item["status"] == "failed")
    assert len(check["components"]) == 3
    assert len(check["component_results"]) == 3
    assert check["component_results"][-1]["result_span"]["quote"] == \
        "Очередь неотправленных документов не уменьшается"
    assert "проверьте состояние приложения EoU" in failed_turn["final_reply"]
    assert "сопоставьте адрес, порт и ИНН ОФД" in failed_turn["final_reply"]

    reported = trace[3]["state_after_sqlite_reopen"]["task_context"]
    printed_check = next(item for item in reported["checks"]
                         if item["unit_id"] == "f09c43177d5a42267fe0")
    assert printed_check["result_span"]["quote"] == "Диагностический отчёт напечатал"
    failed_check = next(item for item in reported["checks"]
                        if item["unit_id"] != printed_check["unit_id"])
    results = {item["component_id"]: item for item in failed_check["component_results"]}
    assert len(results) == 3
    assert {item["status"] for item in results.values()} == {"passed", "failed"}
    assert any("ИНН" in (item.get("result_span") or {}).get("quote", "")
               for item in results.values())
    assert trace[4]["reason"] == "progress_ledger_conditional_source_boundary"


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
    cases = [*_compound_dialogue()[:3], _compound_dialogue()[4]]
    def clear_failed_result_quote(turn, store, conversation_id):
        if turn != 4:
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

    question = trace[3]["final_reply"]
    check = next(item for item in trace[3]["state_after_sqlite_reopen"]["task_context"]["checks"]
                 if item.get("unit_id") != "f09c43177d5a42267fe0")
    assert check.get("status") == "failed"
    assert check.get("result_span") is None
    assert not any((item.get("result_span") or {}).get("quote") ==
                   "Очередь неотправленных документов не уменьшается"
                   for item in check.get("component_results", []))
    assert "Зафиксировал отрицательный результат («" not in question
    assert "Очередь неотправленных документов не уменьшается" not in question
    assert "Осталось сообщить результаты пунктов инструкции" in question
    assert "проверьте состояние приложения EoU" in question
    assert "сопоставьте адрес, порт и ИНН ОФД" in question
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
