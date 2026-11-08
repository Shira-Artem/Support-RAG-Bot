"""Typed coordination layer over validated Understanding and reducer state.

The model interprets the current turn; the existing DialogueManager remains
the sole owner of client facts. This module selects a route/action and records
why without promoting coordinator text into state facts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Literal

from app.dialogue_state import DialogueState
from app.dialogue_understanding import requests_procedure_context


Route = Literal["conversation", "grounded_information", "technical_action"]
TaskRelation = Literal["new_task", "continue", "answer_to_clarification",
                       "parameter_update", "constraint_update", "contradiction", "unknown"]


@dataclass(frozen=True)
class CoordinatorDecision:
    request_type: str
    route: Route
    task_relation: TaskRelation
    current_subgoal: str | None
    required_action: str
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def coordinate(understanding: dict | None, state: DialogueState) -> CoordinatorDecision:
    """Turn validated LLM understanding plus reducer-owned state into an action.

    This function is deliberately deterministic. Its input is the validated,
    persisted Understanding payload; entity values and task transitions come
    only from ``DialogueState`` after reducer replay.
    """
    request_type = str((understanding or {}).get("request_type") or "unknown")
    observation = (understanding or {}).get("observation") or {}
    frame = state.task_frame
    raw_relation = str(frame.relation or "unknown")
    if raw_relation in {"new_task", "continue", "answer_to_clarification",
                        "parameter_update", "constraint_update", "contradiction"}:
        relation: TaskRelation = raw_relation
    else:
        relation = "unknown"
    goals = observation.get("goals") or []
    current_subgoal = next((str(item.get("value")) for item in reversed(goals)
                            if isinstance(item, dict) and item.get("value")), None)

    operation = frame.operation
    def specific_enough(value: str | None) -> bool:
        words = {word.casefold().replace("ё", "е") for word in
                 re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", value or "")}
        words -= {"и", "а", "но", "с", "со", "в", "во", "на", "по", "что", "как",
                  "это", "не", "мне", "помоги", "помогите", "пожалуйста", "ошибка",
                  "ошибки", "проблема", "проблему", "сбой", "неисправность"}
        return len(words) >= 2

    has_diagnostic_detail = bool(state.error or
        (state.symptom and specific_enough(state.symptom.value)) or
        any(specific_enough(goal.value) for goal in state.goals))
    # An absent enum projection is not an absent client task. A reducer-owned
    # goal/symptom plus its subject is sufficient to search for evidence;
    # it never authorizes a procedure or fills a missing scope fact.
    semantic_task_ready = bool(not state.analysis_required and state.task and
        (state.goals or state.symptom) and
        (frame.subject or state.task_entities))
    current_quote = ((observation.get("evidence") or {}).get("quote")
                     if isinstance(observation.get("evidence"), dict) else None)
    reports_check = bool(current_quote and state.active_task and any(
        (item.get("result_span") or {}).get("quote") == current_quote
        and (item.get("result_span") or {}).get("message_id") ==
            (observation.get("evidence") or {}).get("message_id")
        for item in state.active_task.checks))
    # A diagnosis label and a product name do not identify the failure to
    # diagnose. Do not let a broad retrieval hit become an answer; ask for an
    # observable problem first.
    if operation == "diagnose" and not has_diagnostic_detail:
        route, action, rationale = (
            "conversation", "ask_for_missing_problem_detail",
            "diagnosis_has_no_observed_symptom_or_goal")
    elif request_type == "resolved":
        route, action, rationale = "conversation", "close_resolved_task", "client_reports_resolution"
    elif request_type in {"greeting", "feedback", "escalation"} and not reports_check:
        route: Route = "conversation"
        action = "respond_or_handoff"
        rationale = "social_or_handoff_turn"
    elif reports_check:
        # A verified result for an already-shown check must return to the
        # technical path so Planner and SourceFirst can evaluate source
        # conditions. An outstanding details slot must not swallow it.
        route, action, rationale = (
            "technical_action", "continue_verified_check_and_evaluate_source_conditions",
            "reported_result_for_shown_verified_check")
    elif (relation in {"continue", "answer_to_clarification"}
          and operation in {"check", "connect", "configure", "diagnose", "transmit", "change"}
          and (state.goals or state.symptom or state.error)):
        # A short answer to a clarification keeps the active task's route.
        # Its surface form may look informational, but it must not turn a
        # procedural task into a broad Composer search over adjacent articles.
        route, action, rationale = (
            "technical_action", "continue_active_technical_task",
            "clarification_reply_keeps_active_technical_route")
    elif frame.expected_slot in {"task", "goal", "details"}:
        route, action, rationale = "conversation", "ask_for_missing_task_detail", "task_not_ready"
    elif (request_type == "information"
            and requests_procedure_context(str(current_quote or (state.task.value if state.task else "")))):
        route, action, rationale = (
            "technical_action", "retrieve_then_apply_independent_scope_and_safety_gates",
            "procedure_context_requires_complete_scoped_section")
    elif request_type == "information" and operation not in {"diagnose", "transmit"}:
        # Information questions can be attached to a concrete product/operation
        # (compatibility, limits, version support) and may be projected as
        # check/connect by Understanding. Keep those read-only questions on the
        # grounded route; explicit how-to/source-order requests above stay strict.
        route, action, rationale = (
            "grounded_information", "retrieve_and_quote_focused_approved_evidence",
            "information_request_requires_grounded_evidence")
    elif (operation == "explain" and frame.intent == "general"
            and requests_procedure_context(str(current_quote or (state.task.value if state.task else "")))):
        route, action, rationale = (
            "technical_action", "retrieve_then_apply_independent_scope_and_safety_gates",
            "procedure_context_requires_complete_scoped_section")
    elif operation == "explain" and frame.intent == "general":
        route, action, rationale = (
            "grounded_information", "retrieve_and_quote_focused_approved_evidence",
            "grounded_explanation_requires_scoped_evidence")
    elif operation != "unknown" or semantic_task_ready:
        route, action, rationale = (
            "technical_action", "retrieve_then_apply_independent_scope_and_safety_gates",
            "semantic_goal_ready_for_evidence_search" if operation == "unknown" else
            "task_requires_applicability_checked_action")
    else:
        route, action, rationale = "conversation", "ask_for_task_or_goal", "task_not_ready"

    return CoordinatorDecision(
        request_type=request_type,
        route=route,
        task_relation=relation,
        current_subgoal=current_subgoal,
        required_action=action,
        rationale=rationale,
    )
