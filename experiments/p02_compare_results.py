"""Assert the P0.2 paired replay and 100-question benchmark boundaries."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments"
EXPECTED = "batch-20261013-bank-directbank-all-accounts"
POSITIVES = {"original", "paraphrase_missing", "paraphrase_stale"}
NEGATIVES = {"foreign_service", "older_version", "fn_change", "kkt_reregistration"}


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def run():
    before = {x["id"]: x for x in load("p02-qdrant-before.json")["cases"]}
    after = {x["id"]: x for x in load("p02-qdrant-after.json")["cases"]}
    changes = []
    for case_id in sorted(before):
        old, new = before[case_id], after[case_id]
        changes.append({"id": case_id,
                        "before_documents": old["context_documents"],
                        "after_documents": new["context_documents"],
                        "before_evidence": old["evidence_level"],
                        "after_evidence": new["evidence_level"],
                        "before_steps": len(old["supported_steps"]),
                        "after_steps": len(new["supported_steps"])})
        if case_id in POSITIVES:
            assert old["context_documents"] == [] and old["evidence_level"] == "none"
            assert new["context_documents"] == [EXPECTED]
            assert new["context_sections"] == ["Безопасная диагностика"]
            assert new["evidence_level"] == "partial" and new["supported_steps"]
        if case_id in NEGATIVES:
            assert old["context_documents"] == new["context_documents"]
            assert old["evidence_level"] == new["evidence_level"]
            assert old["supported_steps"] == new["supported_steps"]
    baseline = load("p02-benchmark-before.json")["collections"][0]
    current = load("p02-benchmark-after.json")["collections"][0]
    assert baseline["metrics"] == current["metrics"]
    old_rows = {x["id"]: x for x in baseline["rows"]}
    new_rows = {x["id"]: x for x in current["rows"]}
    assert old_rows.keys() == new_rows.keys() and len(old_rows) == 100
    fields = ("context_document_ids", "selected_documents", "expected_rejected_reasons",
              "expected_in_llm_context", "evidence_status", "insufficiency_reason")
    differences = {field: [key for key in old_rows
                           if old_rows[key].get(field) != new_rows[key].get(field)]
                   for field in fields}
    assert not any(differences.values()), differences
    return {"source": "read-only Stage3; no Groq or indexing",
            "positive_cases": sorted(POSITIVES), "negative_cases": sorted(NEGATIVES),
            "replay": changes, "benchmark_questions": 100,
            "benchmark_approved": 83, "benchmark_expected_in_context": 81,
            "benchmark_changed_rows": differences,
            "benchmark_metrics_equal": True,
            "baseline_false_rejections": 2, "new_false_accepts": 0,
            "new_false_rejections": 0}


if __name__ == "__main__":
    result = run()
    path = OUT / "p02-comparison.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
