"""Read-only, privacy-minimized export of the seven November pilot turns.

Run from the repository root. The production database is opened with mode=ro;
the Understanding log is read, and only the report directory is written.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "production_trace_redacted.json"
DB = ROOT / "data/conversations.sqlite3"
LOG = ROOT / ".local/conversational-understanding.jsonl"
IDS = (557, 559, 561, 563, 565, 567, 569)


def redact(value):
    if isinstance(value, str):
        value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
        value = re.sub(r"(?<!\d)(?:\+?7|8)[\s()\-]*\d[\d\s()\-]{8,}\d(?!\d)", "[PHONE]", value)
        return value
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()
                if key not in {"user_id", "chat_id", "conversation_id", "request_payload",
                               "provider_error", "raw_model_text", "raw_text"}}
    return value


def state_summary(state):
    context = (state or {}).get("task_context") or {}
    session = (state or {}).get("session") or {}
    return {
        "revision": (state or {}).get("revision"),
        "task_start_message_id": context.get("topic_start_message_id"),
        "intent": context.get("intent"),
        "operation": context.get("operation"),
        "object": context.get("object"),
        "relation": context.get("relation"),
        "transition": context.get("transition"),
        "expected": context.get("expected"),
        "unresolved": context.get("unresolved"),
        "symptom": (context.get("symptom") or {}).get("value"),
        "goal": [x.get("value") for x in context.get("goals") or []],
        "session_entities": {k: [x.get("value") for x in v]
                             for k, v in (session.get("entities") or {}).items()},
        "task_entities": {k: [x.get("value") for x in v]
                          for k, v in (context.get("entities") or {}).items()},
    }


def main():
    records = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines()]
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = []
    for mid in IDS:
        user = con.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
        answer = con.execute("SELECT * FROM messages WHERE id=?", (mid + 1,)).fetchone()
        assert user and answer and user["role"] == "user" and answer["role"] == "assistant"
        assert user["conversation_id"] == answer["conversation_id"]
        ud = json.loads(user["diagnostics_json"] or "{}")
        ad = json.loads(answer["diagnostics_json"] or "{}")
        before = con.execute("""SELECT state_json FROM dialogue_turns
            WHERE conversation_id=? AND message_id<? ORDER BY message_id DESC LIMIT 1""",
            (user["conversation_id"], mid)).fetchone()
        after = con.execute("SELECT state_json FROM dialogue_turns WHERE message_id=?", (mid,)).fetchone()
        at = datetime.fromisoformat(user["created_at"])
        matches = [x for x in records if abs((datetime.fromisoformat(x["timestamp_utc"]) - at).total_seconds()) < 1]
        assert len(matches) == 1, (mid, len(matches))
        raw = matches[0]
        retrieval = ad.get("retrieval_diagnostics") or {}
        validated = ud.get("understanding") or {}
        row = {
            "question_message_id": mid,
            "answer_message_id": mid + 1,
            "timestamp_utc": user["created_at"],
            "question": user["content"],
            "answer": answer["content"],
            "raw_understanding_status": raw.get("status"),
            "raw_understanding_sha256": raw.get("structured_output_sha256"),
            "raw_understanding": raw.get("structured_output"),
            "raw_understanding_error_code": raw.get("error_code"),
            "validated_observation": validated.get("observation"),
            "validated_request_type": validated.get("request_type"),
            "rejected_claims": [x for x in validated.get("validation_diagnostics") or []
                                if x.get("status") == "rejected"],
            "resolver_decisions": [x for x in validated.get("validation_diagnostics") or []
                                   if x.get("field") in {"task_operation_resolution", "operation_resolution"}],
            "understanding_error": ud.get("understanding_error"),
            "state_before": state_summary(json.loads(before["state_json"])) if before else None,
            "state_after": state_summary(json.loads(after["state_json"])) if after else None,
            "coordinator": ad.get("coordinator_decision"),
            "rag_query": ad.get("rag_query"),
            "persisted_evaluated_candidates": retrieval.get("candidates") or [],
            "raw_chunk_ranking_status": "not_persisted; diagnostics deduplicate and evaluate candidates by document",
            "selected_candidates": retrieval.get("selected") or [],
            "evidence_status": retrieval.get("evidence_status"),
            "sufficient": retrieval.get("sufficient"),
            "insufficiency_reason": retrieval.get("insufficiency_reason"),
            "source_scope_gate": retrieval.get("source_scope_gate"),
            "conceptual_evidence_gate": retrieval.get("conceptual_evidence_gate"),
            "coordinator_evidence": retrieval.get("coordinator_evidence"),
            "planner": retrieval.get("planner"),
            "validation_status": ad.get("validation_status"),
            "validation_reason": ad.get("validation_reason"),
            "scenario": ad.get("scenario"),
            "scenario_reason": ad.get("scenario_reason"),
            "generation_status": ad.get("generation_status"),
            "generation_reason": ad.get("generation_reason"),
            "generation_error": ad.get("generation_error"),
            "llm_call_attempted_after_understanding": ad.get("llm_call_attempted"),
        }
        out.append(redact(row))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pairs": len(out), "message_ids": list(IDS),
                      "raw_correlations": len(out), "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
