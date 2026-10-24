"""Offline aggregate of immutable live trace, saved raw labels and manual review."""
from __future__ import annotations

from collections import Counter
import json

from experiments.evidence_first_vertical.planner import render
from experiments.evidence_first_vertical.prototype import HERE, ROOT, index_documents


def main() -> None:
    trace = [json.loads(line) for line in (HERE / "llm_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    review = json.loads((HERE / "manual_review.json").read_text(encoding="utf-8"))
    cases = {row["id"]: row for row in review["cases"]}
    successes = {row["id"]: row for row in trace if row.get("result")}
    assert len(trace) == 13 and len(successes) == 12
    assert set(successes) == {case for case in cases if cases[case]["verdict"] != "not_run"}
    source_units = sum(len(row["result"]["source_units"]) for row in successes.values())
    index = index_documents()
    current_render = []
    for row in successes.values():
        case = {"id": row["id"], "question": row["question"], "messages": row["messages"]}
        rerendered = render(case, row["proposal"], row["groups"], index)
        assert rerendered["mode"] == row["result"]["mode"]
        assert rerendered["source_units"] == row["result"]["source_units"]
        current_render.append({"id": row["id"], "original_live_answer": row["result"]["answer"],
                               "current_renderer_answer": rerendered["answer"],
                               "answer_text_changed_after_live": rerendered["answer"] != row["result"]["answer"]})
    (HERE / "current-render.json").write_text(json.dumps(current_render, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verdicts = Counter(row["verdict"] for row in cases.values())
    raw = json.loads((ROOT / "experiments/model_benchmark/claim-review.json").read_text(encoding="utf-8"))
    old_final = {}
    for scenario in raw["scenarios"]:
        counts = Counter()
        for model in scenario["models"].values():
            counts.update(claim["status"] for turn in model["turns"] if turn["turn"] == 3
                          for claim in turn["claims"])
        old_final[scenario["id"]] = dict(counts)
    output = {
        "live_attempts": len(trace), "live_successes": len(successes),
        "provider_errors": [row["id"] for row in trace if row.get("error")],
        "source_units_published": source_units,
        "manually_useful_action_units": sum(row["useful_action_units"] for row in cases.values()),
        "source_verifier_rejections_in_live_run": sum(len(row["result"]["rejected"]) for row in successes.values()),
        "confirmed_dangerous_actions_passed": sum(row["dangerous_passed"] for row in cases.values()),
        "verdicts": dict(verdicts),
        "usage_successful_calls": {
            field: sum((row.get("usage") or {}).get(field, 0) for row in successes.values())
            for field in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "old_model_benchmark_final_turn_labels_two_models": old_final,
        "old_final_turn_label_totals": dict(sum((Counter(v) for v in old_final.values()), Counter())),
        "comparison_limit": "Old labels are claim-level on ten free-form final-turn answers; live results are source-section/task-level on twelve successful calls. These are not paired claim-level confusion matrices.",
        "cases": [{**case, "output_mode": (successes.get(case["id"], {}).get("result") or {}).get("mode"),
                   "output_document_id": (successes.get(case["id"], {}).get("result") or {}).get("document_id"),
                   "source_units": len((successes.get(case["id"], {}).get("result") or {}).get("source_units", []))}
                  for case in review["cases"]],
    }
    (HERE / "scorecard.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: output[k] for k in ("live_attempts", "live_successes", "source_units_published",
                                            "manually_useful_action_units", "verdicts",
                                            "confirmed_dangerous_actions_passed")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
