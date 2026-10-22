"""Statistics and lossless local exports for expert reviews and LLM usage."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
from statistics import mean

from app.expert_store import ExpertStore


# Groq public standard token rates for openai/gpt-oss-20b, USD per million tokens.
GROQ_GPT_OSS_20B_INPUT_PER_M = 0.075
GROQ_GPT_OSS_20B_CACHED_INPUT_PER_M = 0.037
GROQ_GPT_OSS_20B_OUTPUT_PER_M = 0.30


def _known_sum(rows: list[dict], field: str) -> int | None:
    values = [row[field] for row in rows if row.get(field) is not None]
    return sum(values) if values else None


def _known_mean(rows: list[dict], field: str) -> float | None:
    values = [row[field] for row in rows if row.get(field) is not None]
    return round(mean(values), 2) if values else None


def groq_paid_cost_estimate(row: dict) -> float | None:
    if row.get("provider") != "groq" or "gpt-oss-20b" not in (row.get("model") or ""):
        return None
    if row.get("prompt_tokens") is None or row.get("completion_tokens") is None:
        return None
    prompt = row["prompt_tokens"]
    cached = row.get("cached_tokens") or 0
    # Only subtract a cached-token discount when the API reports cached usage.
    cached = min(cached, prompt)
    output = row["completion_tokens"]
    cost = ((prompt - cached) * GROQ_GPT_OSS_20B_INPUT_PER_M
            + cached * GROQ_GPT_OSS_20B_CACHED_INPUT_PER_M
            + output * GROQ_GPT_OSS_20B_OUTPUT_PER_M) / 1_000_000
    return round(cost, 8)


def token_metrics(rows: list[dict]) -> dict:
    # Rejected and truncated attempts still called the provider and consumed tokens.
    calls = [r for r in rows if r.get("llm_call_attempted") or
             r.get("generation_status") in {"generated", "rejected", "truncated"}]
    usage_calls = [r for r in calls if any(r.get(k) is not None for k in
                   ("prompt_tokens", "completion_tokens", "total_tokens"))]
    metrics = {
        "llm_calls": len(calls),
        "calls_with_usage": len(usage_calls),
        "prompt_tokens_total": _known_sum(calls, "prompt_tokens"),
        "completion_tokens_total": _known_sum(calls, "completion_tokens"),
        "total_tokens_total": _known_sum(calls, "total_tokens"),
        "reasoning_tokens_total": _known_sum(calls, "reasoning_tokens"),
        "cached_tokens_total": _known_sum(calls, "cached_tokens"),
        "prompt_tokens_average": _known_mean(calls, "prompt_tokens"),
        "completion_tokens_average": _known_mean(calls, "completion_tokens"),
        "total_tokens_average": _known_mean(calls, "total_tokens"),
        "prompt_tokens_max": max((r["prompt_tokens"] for r in calls if r.get("prompt_tokens") is not None), default=None),
        "completion_tokens_max": max((r["completion_tokens"] for r in calls if r.get("completion_tokens") is not None), default=None),
        "total_tokens_max": max((r["total_tokens"] for r in calls if r.get("total_tokens") is not None), default=None),
        "average_duration_ms": _known_mean(calls, "duration_ms"),
        "average_rag_chunks": _known_mean(calls, "rag_chunks"),
        "average_context_chars": _known_mean(calls, "context_chars"),
    }
    daily, monthly = {}, {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        average_value = metrics[f"{field}_average"]
        daily[f"{field}_per_100_calls"] = round(average_value * 100, 2) if average_value is not None else None
        monthly[f"{field}_per_3000_calls"] = round(average_value * 3000, 2) if average_value is not None else None
    metrics["projection_100_calls_per_day"] = daily
    metrics["projection_3000_calls_per_month"] = monthly

    cost_rows = [(row, groq_paid_cost_estimate(row)) for row in calls]
    cost_rows = [(row, cost) for row, cost in cost_rows if cost is not None]
    mean_cost = mean(cost for _, cost in cost_rows) if cost_rows else None
    metrics["groq_paid_tariff_estimate"] = {
        "model": "openai/gpt-oss-20b",
        "priced_calls": len(cost_rows),
        "observed_estimated_usd": round(sum(cost for _, cost in cost_rows), 6) if cost_rows else None,
        "average_per_call_usd": round(mean_cost, 8) if mean_cost is not None else None,
        "estimate_for_100_calls_usd": round(mean_cost * 100, 6) if mean_cost is not None else None,
        "estimate_for_3000_calls_usd": round(mean_cost * 3000, 6) if mean_cost is not None else None,
        "actual_charges_usd": None,
        "pricing_basis": "Standard paid token rates; estimate only, not an invoice or free-tier charge.",
        "input_usd_per_million": GROQ_GPT_OSS_20B_INPUT_PER_M,
        "cached_input_usd_per_million": GROQ_GPT_OSS_20B_CACHED_INPUT_PER_M,
        "output_usd_per_million": GROQ_GPT_OSS_20B_OUTPUT_PER_M,
        "unreported_cached_tokens_assumed": 0,
        "pricing_source_url": "https://console.groq.com/docs/model/openai/gpt-oss-20b",
    }
    return metrics


def statistics(rows: list[dict]) -> dict:
    rated = [r for r in rows if r.get("score") is not None
             and r.get("generation_status") in {"generated", "clarification", "rejected", "no_context"}]
    technical_feedback = [r for r in rows if r.get("score") is not None
                          and r.get("generation_status") in {"error", "unavailable", "truncated"}]
    low = [r for r in rated if r["score"] < 7]
    categories = defaultdict(list)
    sessions = defaultdict(list)
    session_questions = defaultdict(dict)
    for row in rated:
        categories[row["category"]].append(row["score"])
        sessions[row["session_id"]].append(row["score"])
        session_questions[row["session_id"]][row["question_id"]] = row["score"]
    ordered_sessions = list(sessions)
    comparisons = []
    for previous, current in zip(ordered_sessions, ordered_sessions[1:]):
        common = sorted(session_questions[previous].keys() & session_questions[current].keys())
        comparisons.append({
            "previous_session": previous, "current_session": current,
            "average_score_change": round(mean(sessions[current]) - mean(sessions[previous]), 2),
            "same_questions": [
                {"question_id": qid, "previous_score": session_questions[previous][qid],
                 "current_score": session_questions[current][qid],
                 "change": session_questions[current][qid] - session_questions[previous][qid]}
                for qid in common
            ],
        })
    return {
        "reviewed_questions": len({(r['session_id'], r['question_id']) for r in rated}),
        "reviewed_attempts": len(rated),
        "average_score": round(mean(r["score"] for r in rated), 2) if rated else None,
        "below_7": len(low),
        "problem_categories": [
            {"category": name, "average_score": round(mean(scores), 2), "reviewed": len(scores)}
            for name, scores in sorted(categories.items(), key=lambda item: mean(item[1]))
        ],
        "common_reasons": dict(Counter(r["reason"] for r in rated if r.get("reason")).most_common()),
        "common_error_tags": dict(Counter(tag.strip() for r in rated
            for tag in (r.get("error_tags") or "").split(";") if tag.strip()).most_common()),
        "technical_feedback_count": len(technical_feedback),
        "technical_feedback_average_score": round(mean(r["score"] for r in technical_feedback), 2)
            if technical_feedback else None,
        "questions_to_fix": [
            {"session_id": r["session_id"], "question_id": r["question_id"],
             "category": r["category"], "score": r["score"], "reason": r.get("reason"),
             "error_tags": r.get("error_tags"), "comment": r.get("comment"),
             "generation_status": r.get("generation_status")}
            for r in low
        ],
        "sessions": [
            {"session_id": sid, "reviewed": len(scores), "average_score": round(mean(scores), 2)}
            for sid, scores in sessions.items()
        ],
        "session_comparisons": comparisons,
        "technical_errors": sum(r.get("generation_status") == "error" for r in rows),
        "generation_unavailable": sum(r.get("generation_status") == "unavailable" for r in rows),
        "retrieval_no_context": sum(r.get("generation_status") == "no_context" for r in rows),
        "validation_rejected": sum(r.get("generation_status") == "rejected" for r in rows),
        "truncated_generations": sum(r.get("generation_status") == "truncated" for r in rows),
        "scenarios": dict(Counter(r.get("scenario") for r in rows if r.get("scenario"))),
        "scenario_reasons": dict(Counter(r.get("scenario_reason") for r in rows if r.get("scenario_reason"))),
        "token_usage": token_metrics(rows),
    }


def session_summaries(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["session_id"]].append(row)
    result = []
    for session_id, session_rows in grouped.items():
        first = session_rows[0]
        result.append({
            "session_id": session_id,
            "specialist_id": first.get("specialist_id"),
            "telegram_id": first.get("telegram_id"),
            "started_at": first.get("started_at"),
            "finished_at": first.get("finished_at"),
            "questions": len({row["question_id"] for row in session_rows}),
            **token_metrics(session_rows),
        })
    return result


def export(store: ExpertStore, output_dir: Path, expert_id: int | None = None) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = store.rows(expert_id)
    session_rows = session_summaries(rows)
    # CSV is question/attempt level; separate session CSV carries the aggregates.
    cost_rows = [{**row, "groq_paid_cost_estimate_usd": groq_paid_cost_estimate(row)} for row in rows]
    csv_path = output_dir / "expert_reviews.csv"
    sessions_csv_path = output_dir / "expert_sessions.csv"
    json_path = output_dir / "expert_reviews.json"
    fields = list(cost_rows[0]) if cost_rows else ["session_id", "question_id", "attempt_id", "prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens", "cached_tokens", "rag_chunks", "context_chars", "groq_paid_cost_estimate_usd"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(cost_rows)
    session_fields = list(session_rows[0]) if session_rows else ["session_id", "specialist_id", "telegram_id", "llm_calls", "prompt_tokens_total", "completion_tokens_total", "total_tokens_total"]
    with sessions_csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=session_fields)
        writer.writeheader()
        writer.writerows([{key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                           for key, value in row.items()} for row in session_rows])
    questions = [{**row, "groq_paid_cost_estimate_usd": groq_paid_cost_estimate(row),
                  "results": json.loads(row.get("results_json") or "[]")} for row in rows]
    report = {
        "summary": statistics(rows),
        "sessions": session_rows,
        "questions": questions,
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, sessions_csv_path, json_path
