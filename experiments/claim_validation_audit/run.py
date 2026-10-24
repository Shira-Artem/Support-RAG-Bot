"""Offline replay of existing grounding functions on the frozen claim ledger.

This adapter does not reproduce retrieval, generation, production chunking, or
the AnswerService decision path. It makes no network or database calls.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.answer_service import _validation_issue  # noqa: E402
from app.dialogue_state import DialogueManager, DialogueState  # noqa: E402
from app.rag import SearchResult  # noqa: E402
from app.response_grounding import (  # noqa: E402
    _content_terms, claim_supported, needs_procedure_grounding, normalize,
    statements, unsafe_operation_issue,
)
from experiments.oracle_rag.cli import DOCUMENTS  # noqa: E402

HERE = Path(__file__).resolve().parent
BENCHMARK = ROOT / "experiments" / "model_benchmark"
STATUS_POSITIVE = {"supported"}
STATUS_NEGATIVE = {"unsupported", "contradicted", "potentially_dangerous"}


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def source_metadata(doc_id: str, expected_sha: str) -> dict:
    path = DOCUMENTS[doc_id]
    if file_sha(path) != expected_sha:
        raise ValueError(f"Source SHA mismatch: {doc_id}")
    parts = path.read_text(encoding="utf-8").split("---", 2)
    meta = yaml.safe_load(parts[1])
    if meta.get("document_id") != doc_id or meta.get("status") != "approved":
        raise ValueError(f"Source is not approved: {doc_id}")
    meta["_operations_explicit"] = bool(meta.get("operations"))
    return meta


def section_results(turn: dict, source_sha: dict) -> tuple[str, list[SearchResult]]:
    """Keep the exact prompt evidence, split only for section metadata hints."""
    blocks = []
    results = []
    for item in turn["evidence"]:
        doc_id = item["document_id"]
        if item["sha256"] != source_sha[doc_id]:
            raise ValueError(f"Turn evidence SHA mismatch: {doc_id}")
        meta = source_metadata(doc_id, item["sha256"])
        body = item["text"]
        local_body = DOCUMENTS[doc_id].read_text(encoding="utf-8").split("---", 2)[2].strip()
        if body != local_body:
            raise ValueError(f"Turn evidence body differs from approved file: {doc_id}")
        blocks.append(body)
        current_section = ""
        section_lines: list[str] = []

        def add_section():
            content = "\n".join(section_lines).strip()
            if content:
                results.append(SearchResult(
                    source=str(DOCUMENTS[doc_id].relative_to(ROOT)),
                    text=content,
                    score=1.0,
                    metadata={**meta, "section": current_section},
                ))

        for line in body.splitlines():
            match = re.match(r"^##\s+(.+?)\s*$", line)
            if match:
                add_section()
                current_section = match.group(1)
                section_lines = []
            else:
                section_lines.append(line)
        add_section()
    return "\n\n".join(blocks), results


def locate_quote(answer: str, quote: str) -> tuple[int, str | None]:
    def plain(value: str) -> str:
        return normalize(value.replace("**", "").replace("__", ""))

    normalized_answer, normalized_quote = plain(answer), plain(quote)
    count = normalized_answer.count(normalized_quote)
    matches = [sentence for sentence in statements(answer) if normalized_quote in plain(sentence)]
    return count, matches[0] if len(matches) == 1 else None


def candidate_clauses(quote: str, results: list[SearchResult]) -> list[dict]:
    """Lexical review hints only; never used for the acceptance decision."""
    terms = _content_terms(quote)
    ranked = []
    for result in results:
        meta = result.metadata or {}
        for clause in statements(result.text):
            if clause.startswith("#") or len(clause.split()) < 2:
                continue
            overlap = len(terms & _content_terms(clause))
            if overlap:
                ranked.append((overlap, len(clause), {
                    "document_id": meta.get("document_id"), "section": meta.get("section"),
                    "clause": clause, "shared_terms": overlap,
                }))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in ranked[:3]]


def matrix(rows: list[dict], decision_key: str) -> dict:
    result = Counter()
    for row in rows:
        if row["manual_status"] in STATUS_POSITIVE:
            result["TP" if row[decision_key] else "FN"] += 1
        elif row["manual_status"] in STATUS_NEGATIVE:
            result["FP" if row[decision_key] else "TN"] += 1
        else:
            result["excluded_general"] += 1
    result["total_scored"] = sum(result[key] for key in ("TP", "FN", "FP", "TN"))
    result["dangerous_false_acceptance"] = sum(
        row["manual_status"] == "potentially_dangerous" and row[decision_key]
        for row in rows
    )
    result["supported_false_rejection"] = result["FN"]
    return dict(result)


def main():
    raw_path = BENCHMARK / "results.json"
    review = load_json(BENCHMARK / "claim-review.json")
    raw = load_json(raw_path)
    oracle_scenarios = load_json(ROOT / "experiments" / "oracle_rag" / "scenarios.json")
    if file_sha(raw_path) != review["raw_sha256"]:
        raise ValueError("Raw benchmark SHA does not match manual review")
    if raw["successful_calls"] != 30 or raw["attempted_calls"] != 30:
        raise ValueError("Expected exactly 30 saved successful calls")
    oracle_by_id = {item["id"]: item for item in oracle_scenarios}
    if len(oracle_by_id) != 5 or len(raw["scenarios"]) != 5:
        raise ValueError("Expected five frozen Oracle scenarios")
    source_sha = {key: value["sha256"] for key, value in raw["receipt"]["approved_documents"].items()}
    reviewed = {scenario["id"]: scenario for scenario in review["scenarios"]}
    rows: list[dict] = []
    turn_rows: list[dict] = []
    for scenario in raw["scenarios"]:
        scenario_id = scenario["id"]
        oracle = oracle_by_id[scenario_id]
        for model_id, turns in scenario["models"].items():
            if len(turns) != 3 or [turn["user"] for turn in turns] != oracle["turns"]:
                raise ValueError(f"Oracle turn mismatch: {scenario_id}/{model_id}")
            if [turn["evidence_ids"] for turn in turns] != oracle["evidence_by_turn"]:
                raise ValueError(f"Oracle evidence mismatch: {scenario_id}/{model_id}")
            manual_turns = reviewed[scenario_id]["models"][model_id]["turns"]
            if len(turns) != len(manual_turns):
                raise ValueError("Turn count mismatch")
            state = DialogueState()
            manager = DialogueManager()
            for turn, manual_turn in zip(turns, manual_turns, strict=True):
                if turn["turn"] != manual_turn["turn"]:
                    raise ValueError("Turn order mismatch")
                answer = turn["raw_answer"]
                if sha256(answer.encode("utf-8")).hexdigest() != manual_turn["raw_answer_sha256"]:
                    raise ValueError("Answer SHA mismatch")
                state = manager.advance(state, turn["user"], f"{scenario_id}-{turn['turn']}")
                context, results = section_results(turn, source_sha)
                evidence_scope = []
                for doc_id in turn["evidence_ids"]:
                    meta = source_metadata(doc_id, source_sha[doc_id])
                    evidence_scope.append({
                        "document_id": doc_id, "service": meta.get("service"),
                        "model": meta.get("model"), "task_category": meta.get("task_category"),
                        "operations": meta.get("operations"),
                    })
                request = "\n".join(t["user"] for t in turns[:turn["turn"]])
                service = state.routing_service
                full_procedure_issue = needs_procedure_grounding(answer, context, state, results)
                full_validation_issue = _validation_issue(answer, context, request, service, results=results)
                turn_rows.append({
                    "scenario": scenario_id, "model": model_id, "turn": turn["turn"],
                    "state_intent": state.intent, "state_operation": state.operation,
                    "confirmed_service": service, "evidence_ids": turn["evidence_ids"],
                    "evidence_scope": evidence_scope,
                    "full_answer_procedure_issue": full_procedure_issue,
                    "full_answer_validation_issue": full_validation_issue,
                    "caveat": "Oracle context and section adapter; not a production execution",
                })
                for index, claim in enumerate(manual_turn["claims"], start=1):
                    quote = claim["quote"]
                    occurrence_count, sentence = locate_quote(answer, quote)
                    if occurrence_count == 0:
                        raise ValueError(f"Manual quote missing: {scenario_id}/{model_id}/{turn['turn']}/{index}")
                    lexical = claim_supported(quote, context, evidence_results=results)
                    isolated_issue = _validation_issue(quote, context, request, service, results=results)
                    isolated_procedure_issue = needs_procedure_grounding(quote, context, state, results)
                    sentence_issue = (_validation_issue(sentence, context, request, service, results=results)
                                      if sentence else None)
                    sentence_lexical = (claim_supported(sentence, context, evidence_results=results)
                                        if sentence else None)
                    rows.append({
                        "id": f"{scenario_id}/{model_id.rsplit('-', 1)[-1]}/{turn['turn']}/{index:02d}",
                        "scenario": scenario_id, "model": model_id, "turn": turn["turn"],
                        "quote": quote, "manual_status": claim["status"],
                        "manual_source": claim["source"], "manual_reason": claim["reason"],
                        "candidate_source_clauses_not_proof": candidate_clauses(quote, results),
                        "evidence_ids": turn["evidence_ids"],
                        "evidence_scope": evidence_scope,
                        "adapter_state_operation": state.operation,
                        "adapter_confirmed_service": service,
                        "quote_occurrences": occurrence_count, "enclosing_statement": sentence,
                        "span_ambiguous": occurrence_count != 1 or sentence is None,
                        "exact_normalized_in_evidence": normalize(quote) in normalize(context),
                        "claim_supported_accepts": lexical,
                        "isolated_validation_accepts": isolated_issue is None and not isolated_procedure_issue,
                        "isolated_validation_issue": isolated_issue,
                        "isolated_procedure_issue": isolated_procedure_issue,
                        "enclosing_statement_issue": sentence_issue,
                        "enclosing_statement_claim_supported_accepts": sentence_lexical,
                        "fiscal_pattern_issue": unsafe_operation_issue(quote),
                    })
    summary = {
        "input_sha256": {"raw": file_sha(raw_path),
                         "manual_review": file_sha(BENCHMARK / "claim-review.json"),
                         "adapter": file_sha(Path(__file__))},
        "rows": len(rows), "turns": len(turn_rows),
        "manual_statuses": dict(Counter(row["manual_status"] for row in rows)),
        "span_ambiguous": sum(row["span_ambiguous"] for row in rows),
        "direct_claim_supported": matrix(rows, "claim_supported_accepts"),
        "isolated_validation": matrix(rows, "isolated_validation_accepts"),
        "unique_span_claim_supported": matrix([row for row in rows if not row["span_ambiguous"]],
                                              "claim_supported_accepts"),
        "ambiguous_span_claim_supported": matrix([row for row in rows if row["span_ambiguous"]],
                                                 "claim_supported_accepts"),
        "by_scenario": {},
        "by_model": {},
        "full_answer_issue_counts": dict(Counter(
            str(row["full_answer_validation_issue"] or
                ("procedural_details_not_grounded" if row["full_answer_procedure_issue"] else "passed"))
            for row in turn_rows)),
    }
    for field, key in (("by_scenario", "scenario"), ("by_model", "model")):
        groups = defaultdict(list)
        for row in rows:
            groups[row[key]].append(row)
        summary[field] = {
            group: {"count": len(items), "manual_statuses": dict(Counter(x["manual_status"] for x in items)),
                    "direct_claim_supported": matrix(items, "claim_supported_accepts"),
                    "isolated_validation": matrix(items, "isolated_validation_accepts")}
            for group, items in groups.items()
        }
    (HERE / "claim-decisions.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "turn-decisions.json").write_text(json.dumps(turn_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (HERE / "claim-decisions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, extrasaction="ignore", fieldnames=[
            "id", "scenario", "model", "turn", "quote", "manual_status", "manual_source",
            "evidence_ids", "source_scope", "quote_occurrences", "span_ambiguous",
            "claim_supported_accepts", "isolated_validation_accepts", "isolated_validation_issue",
            "isolated_procedure_issue", "enclosing_statement_issue", "manual_reason",
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **row,
                "evidence_ids": ";".join(row["evidence_ids"]),
                "source_scope": json.dumps(row["evidence_scope"], ensure_ascii=False),
            })
    def md(value) -> str:
        return str(value or "—").replace("|", "\\|").replace("\n", " ")

    error_lines = [
        "# Расхождения прямого `claim_supported` с ручной разметкой",
        "",
        "Положительный класс — `supported`; `general` исключён. Цитаты и ссылки на источник "
        "из исходной ручной разметки. Полный набор и второй gate — в `claim-decisions.csv`.",
        "",
    ]
    for heading, predicate in (
        ("False positive: неподтверждённое принято", lambda row: row["manual_status"] in STATUS_NEGATIVE
         and row["claim_supported_accepts"]),
        ("False negative: подтверждённое отклонено", lambda row: row["manual_status"] in STATUS_POSITIVE
         and not row["claim_supported_accepts"]),
    ):
        selected = [row for row in rows if predicate(row)]
        error_lines.extend([f"## {heading} ({len(selected)})", "",
                            "| ID | Ручная метка | Цитата | Ручной источник | Span неоднозначен |",
                            "|---|---|---|---|:---:|"])
        error_lines.extend(
            f"| {md(row['id'])} | {md(row['manual_status'])} | {md(row['quote'])} | "
            f"{md(row['manual_source'])} | {'да' if row['span_ambiguous'] else 'нет'} |"
            for row in selected
        )
        error_lines.append("")
    (HERE / "errors.md").write_text("\n".join(error_lines).rstrip() + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"by_scenario", "by_model"}}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
