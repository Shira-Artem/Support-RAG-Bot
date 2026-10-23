"""Post-process existing assistant-review attempts into a no-LLM A/B pack.

The existing ``run_assistant_review.py`` remains the only live runner.  This
command reads its saved attempts, creates paired raw-vs-full records, scores
them offline, and writes a blind manual-review file.  It never calls Groq.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import assistant_ab_eval as ab  # noqa: E402
from scripts import run_assistant_review as runner  # noqa: E402


def _read_attempts(batch: str) -> list[tuple[dict, dict, dict]]:
    with runner.connect() as db:
        rows = db.execute(
            "SELECT case_id, turn_index, query, answer_json FROM assistant_review_attempts "
            "WHERE batch_id=? ORDER BY id", (batch,)).fetchall()
        cases = {row["case_id"]: json.loads(row["case_json"]) for row in db.execute(
            "SELECT case_id, case_json FROM assistant_review_cases WHERE batch_id=?", (batch,))}
    return [(dict(row), cases[row["case_id"]], json.loads(row["answer_json"])) for row in rows]


def build_pack(batch: str, output: Path) -> Path:
    attempts = _read_attempts(batch)
    if not attempts:
        raise ValueError(f"No saved attempts for batch {batch!r}; live runner was not called")
    records, scores = [], []
    for row, case, answer in attempts:
        turn = case["turns"][row["turn_index"]]
        pairs = ab.pair_attempt(row["case_id"], row["turn_index"], row["query"], answer,
                                expected_service=turn.get("expected_service"))
        for record in pairs:
            records.append(record)
            scores.append({**record.as_dict(), "score": ab.score_variant(record, turn)})
    blind_rows, blind_key = ab.make_blind_pairs(records)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in scores), encoding="utf-8")
    (output / "blind_pairs.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in blind_rows), encoding="utf-8")
    (output / "blind_grades_template.jsonl").write_text(
        "".join(json.dumps({"blind_id": item["blind_id"], "winner": None,
                            "score_1": None, "score_2": None, "comment": ""},
                           ensure_ascii=False) + "\n" for item in blind_rows), encoding="utf-8")
    (output / "blind_key.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in blind_key), encoding="utf-8")
    summary = _summary(scores)
    (output / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = ["# Assistant A/B evaluation", "", "A = raw model response + hard safety gates.",
              "B = saved current full pipeline response.", "No additional LLM calls were made.", "",
              f"Batch: {batch}", f"Records: {len(scores)}", f"Paired questions: {len(blind_rows)}", "",
              "## Offline metrics", "", "```json", json.dumps(summary, ensure_ascii=False, indent=2), "```", "",
              "Blind manual review: `blind_pairs.jsonl`; fill `blind_grades_template.jsonl`. Arm mapping is kept separately in `blind_key.jsonl`.", ""]
    (output / "report.md").write_text("\n".join(report), encoding="utf-8")
    return output


def _summary(records: list[dict]) -> dict:
    result = {"end_to_end": {"variants": {}}, "pairs": len(records) // 2, "api_calls": 0,
              "routing_retrieval_failures": {}, "llm_technical_failures": {},
              "generation_validator_comparison": {"eligible_pairs": 0, "variants": {}}}

    def variant_metrics(subset):
        return {
            "count": len(subset),
            "completeness_mean": round(sum(item["score"]["completeness"] for item in subset) / len(subset), 4) if subset else 0,
            "mandatory_facts_matched": sum(sum(f["matched"] for f in item["score"]["mandatory_facts"]) for item in subset),
            "unsupported_assertions": sum(item["score"]["unsupported_assertions"] for item in subset),
            "factuality_failures": sum(not item["score"]["factuality_pass"] for item in subset),
            "false_refusals": sum(item["score"]["false_refusal"] for item in subset),
            "technical_failures": sum(item["score"]["technical_failure"] for item in subset),
            "unsafe": sum(item["score"]["unsafe"] for item in subset),
        }

    for variant in ("A_raw_safe", "B_full_pipeline"):
        subset = [item for item in records if item["variant"] == variant]
        result["end_to_end"]["variants"][variant] = variant_metrics(subset)

    primary = [item for item in records if item["variant"] == "A_raw_safe"]
    result["routing_retrieval_failures"] = {
        "attempts": len(primary),
        "no_context_or_no_valid_candidates": sum(item["retrieval_failure"] for item in primary),
    }
    result["llm_technical_failures"] = {
        "attempts": len(primary),
        "generation_errors": sum(bool(item["generation_error"]) or item["generation_status"] == "error" for item in primary),
    }
    eligible = [item for item in records if item["comparison_eligible"]]
    eligible_keys = {(item["case_id"], item["turn_index"]) for item in eligible}
    result["generation_validator_comparison"]["eligible_pairs"] = len(eligible_keys)
    for variant in ("A_raw_safe", "B_full_pipeline"):
        result["generation_validator_comparison"]["variants"][variant] = variant_metrics(
            [item for item in eligible if item["variant"] == variant])
    by_key = {}
    for item in records:
        by_key.setdefault((item["case_id"], item["turn_index"]), {})[item["variant"]] = item
    result["generation_validator_comparison"]["facts_lost_after_validator"] = sum(
        max(0, sum(f["matched"] for f in pair["A_raw_safe"]["score"]["mandatory_facts"])
            - sum(f["matched"] for f in pair["B_full_pipeline"]["score"]["mandatory_facts"]))
        for key, pair in by_key.items()
        if key in eligible_keys and set(pair) == {"A_raw_safe", "B_full_pipeline"})
    # One full-run attempt produces both arms; count unique provider IDs.
    result["api_calls"] = len({item["api_call_id"] for item in primary if item["api_call_id"]})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, help="Existing run_assistant_review batch")
    parser.add_argument("--output", type=Path, help="Output directory; defaults to data/evaluations/assistant_ab/<batch>")
    args = parser.parse_args()
    output = args.output or ROOT / "data/evaluations/assistant_ab" / args.batch
    print(build_pack(args.batch, output))


if __name__ == "__main__":
    main()
