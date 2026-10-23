"""P0.2: reviewed diagnostic evidence without granting bank mutations."""
from __future__ import annotations

import re

import pytest

from app.answer_service import _pre_retrieval_clarification
from app.dialogue_state import DialogueManager, DialogueState
from app.procedure_policy import operation_compatibility
from app.rag_query import build_rag_query
from app.response_grounding import _evidence, claim_supported, unsafe_operation_issue
from app.retrieval_pipeline import RetrievalPipeline
from experiments.p02_directbank_replay import CASES, MemorySource, replay

EXPECTED = "batch-20261013-bank-directbank-all-accounts"
SAFE_SECTION = "Безопасная диагностика"


@pytest.fixture(scope="module")
def rows():
    return {row["id"]: row for row in replay()["cases"]}


@pytest.mark.parametrize("case_id", ["original", "paraphrase_missing", "paraphrase_stale"])
def test_incident_paraphrases_get_only_partial_safe_diagnostics(rows, case_id):
    row = rows[case_id]
    assert (row["state"]["intent"], row["state"]["operation"]) == ("bank_statement", "diagnose")
    assert row["candidate_document_ids"] == row["context_document_ids"] == [EXPECTED]
    assert row["context_sections"] == [SAFE_SECTION]
    assert row["evidence_status"] == row["evidence_level"] == "partial"
    assert row["supported_steps"]
    assert all(step["section"] == SAFE_SECTION and step["document_id"] == EXPECTED
               for step in row["supported_steps"])
    assert any("Уточнить версию" in step["text"] for step in row["supported_steps"])
    assert not re.search(r"\b(?:загрузите|импортируйте|переподключите|настройте)\b",
                         " ".join(step["text"] for step in row["supported_steps"]), re.I)


def test_rejected_actions_cannot_be_grounded_by_diagnostic_context():
    question = CASES[0][1]
    state = DialogueManager().advance(DialogueState(), question, 1)
    result = RetrievalPipeline(MemorySource()).search(state, build_rag_query(state))
    evidence = _evidence(result.documents, result.context, state.operation, question,
                         task_category=state.intent)
    assert evidence and {item["section"] for item in evidence} == {SAFE_SECTION}
    for claim in ("Повторно импортируйте банковскую выписку.",
                  "Переподключите 1С:ДиректБанк.",
                  "Измените настройки банковского обмена."):
        assert not claim_supported(claim, result.context, evidence_results=result.documents)
    assert claim_supported("Откройте список «Банковские выписки».",
                           result.context, evidence_results=result.documents)


def test_explicit_operations_remain_distinct_from_diagnosis():
    guide = MemorySource().articles[EXPECTED]
    safe = next(hit.metadata for hit in guide if hit.metadata["section"] == SAFE_SECTION)
    capability = next(hit.metadata for hit in guide
                      if hit.metadata["section"] == "Подтверждённая возможность")
    assert operation_compatibility("diagnose", safe, task_category="bank_statement") == "match"
    assert operation_compatibility("diagnose", capability,
                                   task_category="bank_statement") == "mismatch"
    for operation in ("import_bank_statement_file", "integration_connect", "change",
                      "replace_fiscal_drive", "reregister_cash_register"):
        assert operation_compatibility(operation, safe,
                                       task_category="bank_statement") == "mismatch"
    assert operation_compatibility("diagnose", {**safe, "status": "draft"},
                                   task_category="bank_statement") == "mismatch"
    assert operation_compatibility("diagnose", {**safe, "operations": ["configure_bank_connection"]},
                                   task_category="bank_statement") == "mismatch"


def test_foreign_service_and_unsupported_release_stay_rejected(rows):
    foreign = rows["foreign_service"]
    older = rows["older_version"]
    assert not foreign["context_document_ids"] and not foreign["supported_steps"]
    assert "service_mismatch_or_unlabeled" in foreign["rejected"][0]["reasons"]
    assert not older["context_document_ids"] and not older["supported_steps"]
    assert "version_below_reviewed_minimum" in older["rejected"][0]["reasons"]
    guide = MemorySource().articles[EXPECTED]
    safe = next(hit.metadata for hit in guide if hit.metadata["section"] == SAFE_SECTION)
    assert operation_compatibility("diagnose", safe, "3.0.147",
                                   task_category="bank_statement") == "mismatch"
    assert operation_compatibility("diagnose", safe, "3.0.148",
                                   task_category="bank_statement") == "match"


def test_fiscal_change_and_kkt_reregistration_not_accepted(rows):
    for case_id in ("fn_change", "kkt_reregistration"):
        row = rows[case_id]
        assert not row["candidate_document_ids"]
        assert not row["context_document_ids"]
        assert not row["supported_steps"]
    assert rows["kkt_reregistration"]["evidence_level"] == "unsafe"
    fn_question = next(question for case_id, question in CASES if case_id == "fn_change")
    fn_state = DialogueManager().advance(DialogueState(), fn_question, 1)
    assert _pre_retrieval_clarification(fn_state)[1] == "fiscal_drive_change_scope_missing"
    kkt_question = next(question for case_id, question in CASES if case_id == "kkt_reregistration")
    assert unsafe_operation_issue(kkt_question)
