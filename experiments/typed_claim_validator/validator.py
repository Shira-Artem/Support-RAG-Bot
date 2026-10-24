"""Offline typed claim validation. No production imports, I/O, or LLM calls.

The caller supplies atomic claims and exact clauses. This module never extracts
claims or infers a semantic relation from document-level word overlap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re


class Verdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ClaimKind(str, Enum):
    FACT = "fact"
    ACTION = "action"
    UI = "ui"
    ACCESS = "access"
    LIMITATION = "limitation"
    GENERAL = "general"


class Risk(str, Enum):
    LOW = "low"
    SETTINGS = "settings"
    ACCESS = "access"
    FINANCIAL = "financial"
    FISCAL = "fiscal"
    UNKNOWN = "unknown"


def norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").casefold().replace("ё", "е")).strip()


def contains(text: str, fragment: str | None) -> bool:
    return bool(fragment and norm(fragment) in norm(text))


def tokens(value: str) -> set[str]:
    return set(re.findall(r"[\w]+", norm(value)))


def numbers(value: str) -> set[str]:
    return set(re.findall(r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)", value))


def negated(value: str) -> bool:
    return bool(re.search(r"\bне\b|\bбез\b|недоступ\w*|запре\w*|невозмож\w*", norm(value)))


@dataclass(frozen=True)
class Scope:
    service: str | None = None
    equipment: str | None = None
    version: str | None = None
    operation: str | None = None


@dataclass(frozen=True)
class Claim:
    id: str
    quote: str
    start: int
    end: int
    kind: ClaimKind
    subject: str | None = None
    action: str | None = None
    object: str | None = None
    parameters: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    negated: bool | None = None
    modality: str | None = None
    scope: Scope = Scope()
    risk: Risk = Risk.UNKNOWN
    changes_state: bool | None = None
    ui_labels: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evidence:
    document_id: str
    status: str
    clause: str
    source_text: str
    scope: Scope = Scope()
    limitations: tuple[str, ...] = ()
    # Explicit reviewed declarations only; never derive these from topic words.
    allowed_operations: tuple[str, ...] = ()
    satisfied_prerequisites: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    claim_id: str
    verdict: Verdict
    reason: str
    checks: tuple[str, ...] = ()
    document_id: str | None = None
    clause: str | None = None
    general_exempt: bool = False


def _decision(claim: Claim, verdict: Verdict, reason: str, checks: list[str],
              evidence: Evidence | None = None, *, general: bool = False) -> Decision:
    return Decision(claim.id, verdict, reason, tuple(checks),
                    evidence.document_id if evidence else None,
                    evidence.clause if evidence else None, general)


def validate_claim(claim: Claim, answer: str, evidence: Evidence | None,
                   prior: dict[str, Decision] | None = None) -> Decision:
    checks: list[str] = []
    if claim.start < 0 or claim.end > len(answer) or claim.start >= claim.end or answer[claim.start:claim.end] != claim.quote:
        return _decision(claim, Verdict.UNSUPPORTED, "claim_span_mismatch", checks)
    checks.append("exact_answer_span")
    if claim.kind == ClaimKind.GENERAL:
        return _decision(claim, Verdict.SUPPORTED, "general_exempt_from_specialized_evidence", checks, general=True)
    if claim.depends_on:
        missing = [item for item in claim.depends_on if item not in (prior or {})]
        if missing:
            return _decision(claim, Verdict.NEEDS_REVIEW, "dependency_missing:" + ",".join(missing), checks)
        failed = [item for item in claim.depends_on if (prior or {})[item].verdict != Verdict.SUPPORTED]
        if failed:
            return _decision(claim, Verdict.UNSUPPORTED, "dependency_not_supported:" + ",".join(failed), checks)
        checks.append("dependencies_supported")
    if evidence is None:
        return _decision(claim, Verdict.UNSUPPORTED, "approved_clause_missing", checks)
    if evidence.status != "approved":
        return _decision(claim, Verdict.UNSUPPORTED, "source_not_approved", checks, evidence)
    if not evidence.document_id or not evidence.clause or not contains(evidence.source_text, evidence.clause):
        return _decision(claim, Verdict.UNSUPPORTED, "clause_not_in_approved_source", checks, evidence)
    checks.append("approved_exact_clause")
    for name in ("service", "equipment", "version", "operation"):
        claimed = getattr(claim.scope, name)
        sourced = getattr(evidence.scope, name)
        if claimed and sourced and norm(claimed) != norm(sourced):
            result = Verdict.NEEDS_REVIEW if name == "version" else Verdict.CONTRADICTED
            reason = "version_compatibility_unknown" if name == "version" else f"{name}_scope_mismatch"
            return _decision(claim, result, reason, checks, evidence)
        if claimed and not sourced:
            return _decision(claim, Verdict.NEEDS_REVIEW, f"{name}_scope_unknown", checks, evidence)
    checks.append("scope_no_known_mismatch")
    if claim.scope.operation and evidence.allowed_operations and norm(claim.scope.operation) not in {norm(x) for x in evidence.allowed_operations}:
        return _decision(claim, Verdict.CONTRADICTED, "operation_not_reviewed_for_source", checks, evidence)
    if claim.negated is not None and claim.negated != negated(evidence.clause):
        # A negative claim cannot be proved by a positive clause, or vice versa.
        return _decision(claim, Verdict.NEEDS_REVIEW, "polarity_requires_semantic_review", checks, evidence)
    checks.append("polarity_compatible")
    for value in numbers(claim.quote) | set(claim.parameters):
        if re.fullmatch(r"\d+(?:[.,]\d+)*", value) and value not in evidence.clause:
            return _decision(claim, Verdict.UNSUPPORTED, "number_not_in_clause:" + value, checks, evidence)
    for label in claim.ui_labels:
        if not contains(evidence.clause, label):
            return _decision(claim, Verdict.UNSUPPORTED, "ui_label_not_in_clause:" + label, checks, evidence)
    checks.append("numbers_and_ui_in_clause")
    for value in claim.conditions + claim.prerequisites:
        if not contains(evidence.clause, value) and value not in evidence.satisfied_prerequisites:
            return _decision(claim, Verdict.NEEDS_REVIEW, "condition_not_established:" + value, checks, evidence)
    checks.append("conditions_checked")
    if not claim.negated and any(contains(claim.quote, limit) for limit in evidence.limitations):
        return _decision(claim, Verdict.CONTRADICTED, "known_limitation_conflict", checks, evidence)
    if claim.kind in {ClaimKind.ACTION, ClaimKind.ACCESS, ClaimKind.UI} or claim.changes_state:
        if claim.kind in {ClaimKind.ACTION, ClaimKind.ACCESS} and (claim.risk == Risk.UNKNOWN or claim.changes_state is None):
            return _decision(claim, Verdict.NEEDS_REVIEW, "action_risk_or_state_change_unknown", checks, evidence)
        if not claim.action or not claim.object:
            return _decision(claim, Verdict.NEEDS_REVIEW, "action_object_relation_unknown", checks, evidence)
        if not (contains(claim.quote, claim.action) and contains(claim.quote, claim.object)):
            return _decision(claim, Verdict.NEEDS_REVIEW, "typed_action_not_bound_to_quote", checks, evidence)
        if not (contains(evidence.clause, claim.action) and contains(evidence.clause, claim.object)):
            return _decision(claim, Verdict.NEEDS_REVIEW, "action_object_not_in_same_clause", checks, evidence)
        checks.append("same_clause_action_object")
        if claim.changes_state or claim.risk in {Risk.SETTINGS, Risk.ACCESS, Risk.FINANCIAL, Risk.FISCAL}:
            if not claim.prerequisites:
                return _decision(claim, Verdict.NEEDS_REVIEW, "risk_constraints_not_declared", checks, evidence)
            if not all(x in evidence.satisfied_prerequisites for x in claim.prerequisites):
                return _decision(claim, Verdict.NEEDS_REVIEW, "risk_constraints_not_satisfied", checks, evidence)
            checks.append("risk_constraints_satisfied")
    # Full equality needs no paraphrase inference. Matching relation anchors
    # elsewhere in a sentence are still not semantic entailment.
    if norm(claim.quote) == norm(evidence.clause):
        return _decision(claim, Verdict.SUPPORTED, "exact_clause_with_checked_scope", checks, evidence)
    return _decision(claim, Verdict.NEEDS_REVIEW, "semantic_entailment_unproven", checks, evidence)


def coverage(answer: str, claims: list[Claim], substantive_spans: list[tuple[int, int]] | None) -> dict:
    if substantive_spans is None:
        return {"certified": False, "reason": "substantive_spans_not_provided", "uncovered": []}
    if answer.strip() and not substantive_spans:
        return {"certified": False, "reason": "empty_substantive_inventory", "uncovered": []}
    covered = set()
    for claim in claims:
        if answer[claim.start:claim.end] == claim.quote:
            covered.update(range(claim.start, claim.end))
    uncovered = [(start, end) for start, end in substantive_spans
                 if start < 0 or end > len(answer) or start >= end or not set(range(start, end)) <= covered]
    return {"certified": not uncovered, "reason": "all_declared_spans_covered" if not uncovered else "substantive_span_uncovered", "uncovered": uncovered}


def validate_ledger(answer: str, claims: list[Claim],
                    evidence_by_claim: dict[str, Evidence],
                    substantive_spans: list[tuple[int, int]] | None) -> dict:
    """Validate an ordered ledger and report whether publication is certified.

    The caller must independently supply every substantive span. Omission of
    that inventory makes the whole answer uncertified even when all submitted
    claims are supported.
    """
    decisions: dict[str, Decision] = {}
    for claim in claims:
        if claim.id in decisions:
            raise ValueError(f"duplicate claim ID: {claim.id}")
        decisions[claim.id] = validate_claim(claim, answer, evidence_by_claim.get(claim.id), decisions)
    checked_coverage = coverage(answer, claims, substantive_spans)
    return {"decisions": decisions, "coverage": checked_coverage,
            "safe_to_publish": checked_coverage["certified"] and all(
                d.verdict == Verdict.SUPPORTED for d in decisions.values())}
