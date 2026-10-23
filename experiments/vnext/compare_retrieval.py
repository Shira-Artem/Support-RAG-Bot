"""Pinned, no-Groq paired replay of the three raw-question retrieval controls."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from experiments.vnext.stage3_retrieval import ReadOnlyStage3

CASES = (
    ("platforma_receipt", "Как найти чек по номеру ФД в Платформе ОФД?",
     "platformaofd-lkk-receipt-search"),
    ("aqsi_add_user", "Как добавить сотрудника в aQsi Online?",
     "aqsi-online-account-add-user"),
    ("directbank", "В 1С перестали загружаться банковские выписки. Как разобраться?",
     "batch-20261013-bank-directbank-all-accounts"),
)
FORBIDDEN = {
    "platforma_receipt": {"platformaofd-fns-registration", "platformaofd-fn-number-in-lkk",
                           "platformaofd-tariff-activation"},
    "aqsi_add_user": {"aqsi-online-receipts-full-refund", "aqsi-online-setup-add-store"},
    "directbank": {"batch-20261013-taxes-ens-menu-2026",
                   "batch-20261013-vat-usn-advances-2026"},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt():
    paths = ["experiments/vnext/cli.py", "experiments/vnext/stage3_retrieval.py",
             "experiments/vnext/compare_retrieval.py", "experiments/vnext/scenarios.json",
             "experiments/vnext/scenario-ofd-live-history.json", "app/retrieval.py",
             "app/response_grounding.py", "app/embeddings.py",
             "experiments/vnext/p0-expected-outcomes.json"]
    scenarios = json.loads((ROOT / paths[3]).read_text(encoding="utf-8"))
    history = json.loads((ROOT / paths[4]).read_text(encoding="utf-8"))
    expected = json.loads((ROOT / "experiments/vnext/p0-expected-outcomes.json").read_text(encoding="utf-8"))["scenarios"]
    counts = {"scenario_count": len(scenarios),
              "scenario_turns": sum(len(x["turns"]) for x in scenarios),
              "exact_history_turns": sum(len(x["turns"]) for x in history)}
    if counts != {"scenario_count": 7, "scenario_turns": 15, "exact_history_turns": 3}:
        raise RuntimeError(f"Frozen fixture count changed: {counts}")
    for scenario in [*scenarios, *history]:
        if len(expected.get(scenario["id"], [])) != len(scenario["turns"]):
            raise RuntimeError(f"Missing expected outcome for {scenario['id']}")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True).splitlines()
    return {"head": head, "dirty_paths": dirty,
            "sha256": {path: sha(ROOT / path) for path in paths}, "fixtures": counts,
            "demo": False}


def main():
    env = dotenv_values(ROOT / ".env")  # read only
    store = ReadOnlyStage3(os.getenv("QDRANT_URL") or env.get("QDRANT_URL") or
                           "http://127.0.0.1:6333",
                           os.getenv("EMBEDDING_MODEL") or env.get("EMBEDDING_MODEL") or
                           "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    result = {"receipt": {**receipt(), **store.receipt,
                          "groq_calls": 0, "query_origin": "raw_user_question"},
              "controls": []}
    for name, question, expected in CASES:
        case = {"id": name, "expected_document_id": expected, "question": question}
        for strategy in ("dense", "hybrid"):
            context, trace = store.search_with_trace(
                question, [question], strategy=strategy, query_origin="raw_user_question")
            if any(x["status"] != "approved" for x in context):
                raise RuntimeError("Non-approved fragment entered model context")
            selected = {x["document_id"] for x in trace["candidates"] if x["reason"] == "selected"}
            if set(trace["context_document_ids"]) != selected:
                raise RuntimeError("Context and candidate decisions disagree")
            case[strategy] = trace
            case[strategy]["expected_in_context"] = expected in trace["context_document_ids"]
        result["controls"].append(case)
        if FORBIDDEN[name] & set(case["hybrid"]["context_document_ids"]):
            raise RuntimeError(f"Incompatible instructions entered hybrid context: {name}")
        print(json.dumps({"case": name, "expected": expected,
                          "dense": {"found": case["dense"]["expected_in_context"],
                                    "documents": case["dense"]["context_document_ids"],
                                    "ms": case["dense"]["retrieval_ms"]},
                          "hybrid": {"found": case["hybrid"]["expected_in_context"],
                                     "documents": case["hybrid"]["context_document_ids"],
                                     "ms": case["hybrid"]["retrieval_ms"]}},
                         ensure_ascii=False), flush=True)
    result["summary"] = {"dense_recall_at_context": sum(c["dense"]["expected_in_context"] for c in result["controls"]),
                         "hybrid_recall_at_context": sum(c["hybrid"]["expected_in_context"] for c in result["controls"]),
                         "control_count": len(CASES)}
    path = Path(__file__).with_name("p0-raw-retrieval-results.json")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "output": str(path)}, ensure_ascii=False), flush=True)
    if result["summary"]["hybrid_recall_at_context"] != len(CASES):
        raise SystemExit("Hybrid control failed: inspect trace, no P0.2 admission")


if __name__ == "__main__":
    main()
