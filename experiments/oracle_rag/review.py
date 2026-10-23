"""Attach a separately authored manual scorecard to immutable raw Groq answers."""
from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    raw_path = HERE / "results.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    card = json.loads((HERE / "scorecard.json").read_text(encoding="utf-8"))
    axes = card["axes"]
    rows = []
    for scenario in raw["scenarios"]:
        scores = card["scores"][scenario["id"]]
        if len(scores) != len(scenario["turns"]):
            raise ValueError(f"Score count mismatch: {scenario['id']}")
        for turn, score in zip(scenario["turns"], scores):
            marks = score["marks"].replace(" ", "")
            if len(marks) != len(axes) or set(marks) - {"P", "F", "N"}:
                raise ValueError(f"Bad marks: {scenario['id']} {turn['turn']}: {marks}")
            if turn["status"] != "generated" or not turn["raw_answer"]:
                raise ValueError(f"Cannot manually score missing answer: {scenario['id']}")
            turn["independent_review"] = {
                "axes": dict(zip(axes, marks)), "finding": score["finding"],
                "raw_answer_sha256": hashlib.sha256(turn["raw_answer"].encode("utf-8")).hexdigest(),
                "method": "manual claim/action comparison against exact supplied evidence; no answer rewrite",
                "delivery_disposition": "blocked_unverified_or_unsafe" if marks[4] == "F" or marks[5] == "F" else "reviewed_no_grounding_block",
            }
            rows.append(turn)
        scenario["outcome"] = card["scenario_outcomes"][scenario["id"]]
    raw["review"] = {"source_raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                     "scorecard_sha256": hashlib.sha256((HERE / "scorecard.json").read_bytes()).hexdigest(),
                     "reviewed_at": card["reviewed_at"], "axes": axes,
                     "resolved_scenarios": sum(s["outcome"]["resolved"] for s in raw["scenarios"]),
                     "generated_turns": len(rows),
                     "prompt_tokens": sum(t["usage"].get("prompt_tokens", 0) for t in rows),
                     "completion_tokens": sum(t["usage"].get("completion_tokens", 0) for t in rows),
                     "total_tokens": sum(t["usage"].get("total_tokens", 0) for t in rows),
                     "reasoning_tokens": sum((t["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens", 0) for t in rows),
                     "provider_latency_sum_ms": sum(t["latency_ms"] for t in rows),
                     "provider_latency_median_ms": statistics.median(t["latency_ms"] for t in rows)}
    (HERE / "reviewed-results.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Таблица независимой оценки", "", "P = pass; F = fail; N = неприменимо. Оси: понимание, память, задача, польза, grounding, безопасность, вопрос, эскалация.", "",
             "| Сценарий | Ход | Пон. | Пам. | Зад. | Польза | Факты | Безоп. | Вопрос | Эск. |", "|---|---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|"]
    for scenario in raw["scenarios"]:
        for turn in scenario["turns"]:
            marks = list(turn["independent_review"]["axes"].values())
            lines.append(f"| {scenario['id']} | {turn['turn']} | " + " | ".join(marks) + " |")
    lines += ["", "Подробные причины каждого балла и неизменённые исходные ответы находятся в `reviewed-results.json`."]
    (HERE / "score-table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(raw["review"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
