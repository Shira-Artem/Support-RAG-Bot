"""Bounded Decision-only diagnostic using frozen Understanding/Qdrant evidence cassettes.

This runner never calls Understanding, writes Qdrant, or retries a provider error.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from time import perf_counter

from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.dialogue_state import DialogueState
from app.semantic_evidence_selector import (EvidenceUnit, select_evidence,
    validate_selected_units)


TRACE = ROOT / "experiments/architecture_recovery_audit/p1_semantic_selector_ab_20261026.json"
DEV = ROOT / "experiments/architecture_recovery_audit/p1_semantic_selector_dev_cassettes_20261026.json"
HOLDOUT = ROOT / "experiments/architecture_recovery_audit/p1_semantic_selector_holdout_cassettes_20261026.json"
OUTPUT = ROOT / "experiments/architecture_recovery_audit/p1_semantic_selector_diagnostic_20261026.json"
MAX_DECISION_CALLS = 4


def _cases() -> list[tuple[str, dict]]:
    dev = json.loads(DEV.read_text(encoding="utf-8"))
    holdout = json.loads(HOLDOUT.read_text(encoding="utf-8"))
    return [("DEV", dev["cases"][0]), ("HOLDOUT", holdout["cases"][0]),
            ("DEV", dev["cases"][1]), ("HOLDOUT", holdout["cases"][1])]


def _units(case: dict) -> list[EvidenceUnit]:
    raw = case.get("evidence_units") or case.get("candidate_units") or []
    return [EvidenceUnit(**item) for item in raw]


def _history(cases: list[tuple[str, dict]], index: int) -> list[dict]:
    # The original A/B runner persisted the lexical answer before the next turn.
    if index == 1:
        previous = cases[0][1]
    elif index == 3:
        previous = cases[2][1]
    else:
        return []
    answer = (previous.get("lexical") or {}).get("answer") or ""
    return [{"role": "user", "content": previous["question"]},
            {"role": "assistant", "content": answer}]


def _qdrant_preflight(expected_collection: str) -> dict:
    url = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
    collection = os.getenv("QDRANT_COLLECTION", "")
    if not collection or collection != expected_collection:
        raise RuntimeError("qdrant_collection_mismatch_or_missing")
    client = QdrantClient(url=url, timeout=10)
    try:
        info = client.get_collection(collection)
        return {"url_host": url.split("//")[-1].split("/")[0], "collection": collection,
                "points_count": info.points_count, "status": str(info.status),
                "mode": "read-only get_collection"}
    finally:
        client.close()


async def run(start_index: int = 0) -> dict:
    settings = get_settings()
    original = json.loads(TRACE.read_text(encoding="utf-8"))
    cases = _cases()
    result = {"status": "BLOCKED", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": settings.llm_provider, "model": settings.groq_model,
        "source_trace": str(TRACE.relative_to(ROOT)).replace("\\", "/"),
        "dev_cassette": str(DEV.relative_to(ROOT)).replace("\\", "/"),
        "holdout_cassette": str(HOLDOUT.relative_to(ROOT)).replace("\\", "/"),
        "understanding_calls": 0, "qdrant_writes": 0, "automatic_retries": 0,
        "decision_call_limit": MAX_DECISION_CALLS, "decision_calls": 0,
        "start_case_index": start_index,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "turns": [], "prompt_frozen_for_holdout": True}
    if settings.llm_provider != "groq" or not settings.groq_api_key:
        result["stop_reason"] = "groq_not_configured"
        return result
    try:
        result["qdrant_preflight"] = _qdrant_preflight(original["qdrant_collection"])
    except Exception as exc:
        result["stop_reason"] = f"qdrant_read_only_preflight_failed:{type(exc).__name__}"
        return result

    for index, (split, case) in enumerate(cases[start_index:MAX_DECISION_CALLS], start=start_index):
        state_data = case.get("state_after") or case.get("state")
        state = DialogueState.from_dict(state_data)
        units = _units(case)
        turn = {"split": split, "question": case["question"],
            "understanding_raw": case.get("understanding_raw"),
            "understanding_validated": case.get("understanding_validated"),
            "coordinator_decision": case.get("coordinator_decision"),
            "state": state.to_dict(), "history": _history(cases, index),
            "evidence_ids": [u.id for u in units],
            "source_hashes": list(dict.fromkeys(u.source_sha256 for u in units))}
        started = perf_counter()
        result["decision_calls"] += 1  # Count the attempted request, including provider failures.
        try:
            decision, generation = await select_evidence(case["question"], state,
                turn["history"], units, settings,
                current_subgoal=(case.get("coordinator_decision") or {}).get("current_subgoal"))
            for key in result["usage"]:
                value = getattr(generation, key, None)
                if isinstance(value, int):
                    result["usage"][key] += value
            informational = state.intent == "general" and state.operation == "explain"
            selected, rejection = validate_selected_units(decision, units, state, ROOT,
                informational=informational)
            turn.update({"decision": asdict(decision), "selected_ids_verified": [u.id for u in selected],
                "selected_text": " ".join(u.text for u in selected) if selected else None,
                "safety_passed": rejection is None,
                "validation_rejection": rejection,
                "latency_ms": generation.duration_ms,
                "usage": {key: getattr(generation, key) for key in result["usage"]},
                "model": generation.model, "api_call_id": generation.api_call_id})
        except Exception as exc:
            provider_usage = getattr(exc, "provider_usage", None)
            if isinstance(provider_usage, dict):
                for key in result["usage"]:
                    value = provider_usage.get(key)
                    if isinstance(value, int):
                        result["usage"][key] += value
            turn.update({"error_type": type(exc).__name__, "error": str(exc)[:120],
                "phase": getattr(exc, "stage", None), "http_status": getattr(exc, "http_status", None),
                "provider_error_type": getattr(exc, "error_type", None),
                "provider_error_code": getattr(exc, "provider_error_code", None),
                "provider_error_param": getattr(exc, "provider_error_param", None),
                "retry_after_seconds": getattr(exc, "retry_after_seconds", None),
                "schema_error": getattr(exc, "schema_error", None),
                "latency_ms": getattr(exc, "duration_ms", None),
                "provider_usage": provider_usage})
            result["turns"].append(turn)
            result["stop_reason"] = "provider_error_stopped_without_retry"
            break
        if turn.get("latency_ms") is None:
            turn["latency_ms"] = round((perf_counter() - started) * 1000)
        result["turns"].append(turn)
    else:
        result["status"] = "COMPLETED"
        result["stop_reason"] = "requested_decision_calls_completed"
    if result["decision_calls"] < MAX_DECISION_CALLS and result.get("stop_reason") == "provider_error_stopped_without_retry":
        result["status"] = "BLOCKED" if result["turns"][-1].get("http_status") in {None, 408, 429, 500, 502, 503, 504} else "COMPLETED_WITH_PROVIDER_ERROR"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="make at most four real Decision calls")
    parser.add_argument("--start-index", type=int, choices=range(0, MAX_DECISION_CALLS), default=0,
                        help="start at a saved cassette case; earlier calls are not repeated")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"mode": "preflight_only", "will_make_groq_calls": False,
            "decision_call_limit": MAX_DECISION_CALLS, "understanding_calls": 0,
            "qdrant_mode": "read-only get_collection", "output": str(args.output)}, indent=2))
        return 0
    result = asyncio.run(run(args.start_index))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result.get(key) for key in ("status", "stop_reason", "decision_calls", "usage", "qdrant_preflight")}, ensure_ascii=False, indent=2))
    print(args.output)
    return 0 if result["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
