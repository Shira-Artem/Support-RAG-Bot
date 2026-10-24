"""Frozen V1.1 label replay. Candidate clauses are hints, never gold proof."""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.oracle_rag.cli import DOCUMENTS  # noqa: E402
from experiments.typed_claim_validator.validator import (  # noqa: E402
    Claim, ClaimKind, Evidence, Risk, Scope, Verdict, coverage, negated,
    validate_claim,
)

HERE = Path(__file__).resolve().parent
AUDIT = ROOT / "experiments" / "claim_validation_audit" / "claim-decisions.json"
RAW = ROOT / "experiments" / "model_benchmark" / "results.json"
REVIEW = ROOT / "experiments" / "model_benchmark" / "claim-review.json"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def documents(raw: dict) -> dict:
    result = {}
    for doc_id, receipt in raw["receipt"]["approved_documents"].items():
        path = DOCUMENTS[doc_id]
        if digest(path) != receipt["sha256"]:
            raise ValueError(f"source SHA mismatch: {doc_id}")
        _, front, body = path.read_text(encoding="utf-8").split("---", 2)
        meta = yaml.safe_load(front)
        if meta.get("document_id") != doc_id or meta.get("status") != "approved":
            raise ValueError(f"source status/ID mismatch: {doc_id}")
        result[doc_id] = (meta, body.strip())
    return result


def metric(rows: list[dict], field: str) -> dict:
    c = Counter()
    for row in rows:
        gold = row["manual_status"]
        if gold == "general":
            c["excluded_general"] += 1
            continue
        accepted = row[field] == "SUPPORTED" if field == "verdict" else row[field]
        c[("TP" if accepted else "FN") if gold == "supported" else ("FP" if accepted else "TN")] += 1
        if field == "verdict" and row[field] == "NEEDS_REVIEW":
            c["NEEDS_REVIEW"] += 1
        if gold == "potentially_dangerous" and accepted:
            c["dangerous_false_acceptance"] += 1
    return dict(c)


def main():
    raw, review, old = read(RAW), read(REVIEW), read(AUDIT)
    if digest(RAW) != review["raw_sha256"] or len(old) != 316:
        raise ValueError("frozen inputs changed")
    docs = documents(raw)
    turns = {(s["id"], model, t["turn"]): t
             for s in raw["scenarios"] for model, ts in s["models"].items() for t in ts}
    if len(turns) != 30:
        raise ValueError("expected 30 frozen turns")
    for turn in turns.values():
        if [e["document_id"] for e in turn["evidence"]] != turn["evidence_ids"]:
            raise ValueError("turn evidence IDs differ")
        for item in turn["evidence"]:
            doc_id = item["document_id"]
            if item["sha256"] != raw["receipt"]["approved_documents"][doc_id]["sha256"] or item["text"] != docs[doc_id][1]:
                raise ValueError(f"exact evidence mismatch: {doc_id}")
    output = []
    by_turn = defaultdict(list)
    for row in old:
        turn = turns[row["scenario"], row["model"], row["turn"]]
        answer = turn["raw_answer"]
        quote = row["quote"]
        start = answer.find(quote)
        # Manual markdown stripping makes some quotes non-literal. Do not
        # invent an offset; record a coverage failure and an unsupported span.
        if start < 0:
            start = -1
        # Gold labels are used only below for scoring, never as validator input.
        # No independent general/specialized extractor exists in this replay.
        kind = ClaimKind.FACT
        clause_hint = next((c for c in row["candidate_source_clauses_not_proof"]
                            if c["document_id"] in turn["evidence_ids"]), None)
        ev = None
        if clause_hint:
            doc_id = clause_hint["document_id"]
            meta, body = docs[doc_id]
            ev = Evidence(doc_id, meta["status"], clause_hint["clause"], body,
                          Scope(meta.get("service"), meta.get("model"), meta.get("version"), None),
                          allowed_operations=tuple(meta.get("operations") or ()))
        # The adapter's broad routing label is not a confirmed exact service
        # identity (e.g. a product family can differ from a source product).
        claim = Claim(row["id"], quote, start, start + len(quote), kind,
                      negated=negated(quote), risk=Risk.UNKNOWN)
        decision = validate_claim(claim, answer, ev)
        item = {"id": row["id"], "scenario": row["scenario"], "model": row["model"],
                "turn": row["turn"], "quote": quote, "start": start, "end": start + len(quote),
                "manual_status": row["manual_status"], "span_ambiguous": row["span_ambiguous"],
                "old_accepts": row["claim_supported_accepts"], "verdict": decision.verdict.value,
                "reason": decision.reason, "checks": decision.checks,
                "document_id": decision.document_id, "clause": decision.clause,
                "general_exempt": decision.general_exempt}
        output.append(item)
        by_turn[row["scenario"], row["model"], row["turn"]].append(claim)
    cover = []
    for key, claims in by_turn.items():
        answer = turns[key]["raw_answer"]
        # V1.1 does not mark all substantive spans, so certification is
        # impossible. Character coverage is only an observed lower bound.
        valid = set()
        for claim in claims:
            if claim.start >= 0 and answer[claim.start:claim.end] == claim.quote:
                valid.update(range(claim.start, claim.end))
        result = coverage(answer, claims, None)
        cover.append({"scenario": key[0], "model": key[1], "turn": key[2],
                      "declared_claims": len(claims), "answer_characters": len(answer),
                      "covered_characters": len(valid), **result})
    summary = {
        "inputs_sha256": {"raw": digest(RAW), "review": digest(REVIEW), "audit": digest(AUDIT)},
        "labels": len(output), "turns": len(cover), "span_ambiguous": sum(x["span_ambiguous"] for x in output),
        "old": metric(output, "old_accepts"), "typed": metric(output, "verdict"),
        "verdicts": dict(Counter(x["verdict"] for x in output)),
        "reasons": dict(Counter(x["reason"] for x in output)),
        "families": {family: {"old": metric([x for x in output if x["scenario"] == family], "old_accepts"),
                              "typed": metric([x for x in output if x["scenario"] == family], "verdict")}
                     for family in sorted({x["scenario"] for x in output})},
        "ambiguous_spans": {"old": metric([x for x in output if x["span_ambiguous"]], "old_accepts"),
                            "typed": metric([x for x in output if x["span_ambiguous"]], "verdict")},
        "coverage": {"certified_turns": sum(x["certified"] for x in cover),
                     "total_answer_characters": sum(x["answer_characters"] for x in cover),
                     "covered_characters_lower_bound": sum(x["covered_characters"] for x in cover)},
    }
    HERE.mkdir(exist_ok=True)
    for name, value in (("decisions.json", output), ("summary.json", summary), ("coverage.json", cover)):
        (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"old": summary["old"], "typed": summary["typed"],
                      "verdicts": summary["verdicts"], "coverage": summary["coverage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
