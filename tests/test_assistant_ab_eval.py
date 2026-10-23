"""Offline A/B harness checks; no provider, Qdrant, Telegram or database calls."""
import json
from pathlib import Path
import sqlite3
import pytest

from scripts import assistant_ab_eval as ab
from scripts import run_assistant_ab_review as ab_runner
from scripts import run_assistant_review as runner
from app.answer_service import Answer
from app.dialogue_state import DialogueState
from dataclasses import asdict


ROOT = Path(__file__).resolve().parents[1]


def _answer(raw, final, *, query="Как проверить отчёт?", dangerous=False):
    return {
        "text": final,
        "raw_model_text": raw,
        "raw_text": raw,
        "generation_status": "rejected" if dangerous else "generated",
        "scenario": "escalate" if dangerous else "answer",
        "model": ab.EXPECTED_MODEL,
        "reasoning_effort": ab.EXPECTED_EFFORT,
        "duration_ms": 123,
        "total_tokens": 77,
        "confirmed_service": "Платформа ОФД",
        "retrieval_diagnostics": {
            "context": "[Источник: platformaofd/ofd/fns-indicators.md; section]\nподтверждённый текст"
        },
    }


def test_candidate_pack_has_twenty_new_questions_and_candidate_expectations():
    path = ROOT / "data/evaluations/ab_candidate_2026-10-23.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    questions = [turn for row in rows for turn in row["turns"]]
    assert len(rows) == len(questions) == 20
    assert len({turn["query"] for turn in questions}) == 20
    assert all(row["candidate_status"] == "candidate" and not row["manual_approved"] for row in rows)
    assert sum(bool(row["reference_documents"]) for row in rows) >= 18
    assert all(2 <= len(turn["mandatory_facts"]) <= 4 for turn in questions)
    assert all(turn["expected_type"] in {"answer", "clarify", "escalate"} for turn in questions)


def test_pair_uses_same_raw_context_and_keeps_full_pipeline_separate():
    raw = '{"scenario":"answer","reason":"ok","response":"Шаг 1. Откройте «ФНС». Шаг 2. Проверьте детали."}'
    final = "Откройте «ФНС» и проверьте детали."
    records = ab.pair_attempt("AB-012", 0, "Что означает запрет?", _answer(raw, final))
    assert [record.variant for record in records] == ["A_raw_safe", "B_full_pipeline"]
    assert records[0].final_answer == "Шаг 1. Откройте «ФНС». Шаг 2. Проверьте детали."
    assert records[1].final_answer == final
    assert records[0].sources == records[1].sources
    assert records[0].latency_ms == records[1].latency_ms == 123
    assert records[0].tokens == records[1].tokens == 77


def test_dangerous_query_cannot_make_raw_arm_unsafe():
    raw = '{"scenario":"answer","reason":"ok","response":"Откройте меню и нажмите «Закрыть архив ФН»."}'
    answer = _answer(raw, "Это ответственная фискальная операция; передайте вопрос специалисту.", dangerous=True)
    records = ab.pair_attempt("AB-011", 0, "Как закрыть архив ФН?", answer)
    assert records[0].hard_gate == "dangerous_operation"
    assert "Закрыть архив ФН" not in records[0].final_answer
    assert records[0].scenario == "escalate"


def test_no_context_and_real_refusal_wording_count_as_false_refusal():
    answer = _answer("", "Для сервиса не нашёл подтверждённых сведений; обратитесь к специалисту.")
    answer.update({"raw_model_text": None, "raw_text": None, "generation_status": "no_context",
                   "scenario": "escalate", "retrieval_diagnostics": {
                       "context": "", "insufficiency_reason": "no_task_matched_candidates"}})
    record = ab.pair_attempt("AB-002", 0, "Где изменить телефон?", answer,
                             expected_service="aQsi Online")[0]
    score = ab.score_variant(record, {"expected_type": "answer", "mandatory_facts": [],
                                      "forbidden_statements": [], "query": "Где изменить телефон?"})
    assert record.retrieval_failure is True
    assert score["false_refusal"] is True
    assert score["refusal_observed"] is True


def test_runner_preflight_rejects_stage_mismatch_before_provider():
    class Store:
        collection = "knowledge_stage3_retrieval_20261022"

    class RetrieverObject:
        store = Store()

    class Rag:
        retriever = RetrieverObject()

    class Service:
        rag = Rag()

    assert runner.verify_retriever_collection(Service(), "knowledge_stage3_retrieval_20261022") == \
        "knowledge_stage3_retrieval_20261022"
    with pytest.raises(RuntimeError, match="collection mismatch"):
        runner.verify_retriever_collection(Service(), "knowledge_organized_stage2_20261022")


def test_postprocessor_reads_case_id_and_writes_blind_pack(tmp_path, monkeypatch):
    path = tmp_path / "reviews.sqlite3"
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    runner.prepare(db)
    case = {"turns": [{"query": "Вопрос", "expected_service": None,
                        "expected_type": "answer", "mandatory_facts": [],
                        "forbidden_statements": []}]}
    answer = Answer("Ответ", generation_status="clarification", scenario="clarify")
    db.execute("INSERT INTO assistant_review_batches VALUES(?,?,?,?,?)", ("b", "now", "complete", "{}", "{}"))
    db.execute("INSERT INTO assistant_review_cases VALUES(?,?,?,?)", ("b", "AB-001", json.dumps(case), "cid"))
    db.execute("""INSERT INTO assistant_review_attempts(batch_id,case_id,turn_index,created_at,query,state_json,answer_json)
                 VALUES(?,?,?,?,?,?,?)""", ("b", "AB-001", 0, "now", "Вопрос",
                                              json.dumps(DialogueState().to_dict()), json.dumps(asdict(answer))))
    db.commit(); db.close()
    def connect_test_db():
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(runner, "connect", connect_test_db)
    monkeypatch.setattr(ab_runner.runner, "connect", connect_test_db)
    output = ab_runner.build_pack("b", tmp_path / "out")
    assert (output / "blind_pairs.jsonl").exists()
    assert len((output / "blind_pairs.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_offline_score_counts_missing_fact_forbidden_claim_and_not_false_refusal():
    raw = '{"scenario":"answer","reason":"ok","response":"Откройте журнал и проверьте статус."}'
    record = ab.pair_attempt("AB-001", 0, "Как проверить?", _answer(raw, "Откройте журнал и проверьте статус."))[0]
    turn = {
        "expected_type": "answer",
        "mandatory_facts": [
            {"id": "journal", "patterns": ["журнал"]},
            {"id": "status", "patterns": ["статус"]},
            {"id": "missing", "patterns": ["номер фд"]},
        ],
        "forbidden_statements": [
            {"id": "invented", "patterns": ["кнопк.*экспорт"]},
        ],
        "query": "Как проверить?",
    }
    score = ab.score_variant(record, turn)
    assert score["completeness"] == 2 / 3
    assert score["unsupported_assertions"] == 0
    assert score["factuality_pass"] is True
    assert score["false_refusal"] is False
    assert score["technical_failure"] is False


def test_offline_score_flags_unconfirmed_permission_without_erasing_safe_facts():
    raw = '{"scenario":"answer","reason":"ok","response":"Откройте «Отчёты» и выдайте доступ к разделу."}'
    record = ab.pair_attempt("AB-001", 0, "Какие права дать?", _answer(raw, "Откройте «Отчёты» и выдайте доступ к разделу."))[0]
    turn = {
        "expected_type": "clarify",
        "mandatory_facts": [{"id": "route", "patterns": ["отч[её]т"]}],
        "forbidden_statements": [{"id": "unconfirmed", "patterns": ["выдайте доступ"]}],
        "query": "Какие права дать?",
    }
    score = ab.score_variant(record, turn)
    assert score["completeness"] == 1.0
    assert score["unsupported_assertions"] == 1
    assert score["factuality_pass"] is False


def test_blind_rows_do_not_reveal_arm_mapping():
    raw = '{"scenario":"answer","reason":"ok","response":"Ответ A"}'
    records = ab.pair_attempt("AB-001", 0, "Вопрос", _answer(raw, "Ответ B"))
    rows, key = ab.make_blind_pairs(records, seed=7)
    assert len(rows) == len(key) == 1
    assert set(rows[0]) == {"blind_id", "case_id", "turn_index", "query", "response_1", "response_2"}
    assert "variant" not in rows[0]
    assert key[0]["response_1_variant"] != key[0]["response_2_variant"]
