"""Typed coordination layer over validated Understanding and reducer state.

The model interprets the current turn; the existing DialogueManager remains
the sole owner of client facts. This module selects a route/action and records
why without promoting coordinator text into state facts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.dialogue_state import DialogueState


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
    raw_relation = str(state.relation or "unknown")
    if raw_relation in {"new_task", "continue", "answer_to_clarification",
                        "parameter_update", "constraint_update", "contradiction"}:
        relation: TaskRelation = raw_relation
    else:
        relation = "unknown"
    goals = observation.get("goals") or []
    current_subgoal = next((str(item.get("value")) for item in reversed(goals)
                            if isinstance(item, dict) and item.get("value")), None)

    operation = state.operation
    current_quote = ((observation.get("evidence") or {}).get("quote")
                     if isinstance(observation.get("evidence"), dict) else None)
    reports_check = bool(current_quote and state.active_task and any(
        (item.get("result_span") or {}).get("quote") == current_quote
        and (item.get("result_span") or {}).get("message_id") ==
            (observation.get("evidence") or {}).get("message_id")
        for item in state.active_task.checks))
    if request_type == "resolved":
        route, action, rationale = "conversation", "close_resolved_task", "client_reports_resolution"
    elif request_type in {"greeting", "feedback", "escalation"} and not reports_check:
        route: Route = "conversation"
        action = "respond_or_handoff"
        rationale = "social_or_handoff_turn"
    elif state.expected and state.expected.slot in {"task", "goal", "details"}:
        route, action, rationale = "conversation", "ask_for_missing_task_detail", "task_not_ready"
    elif operation == "explain" and state.intent == "general":
        route, action, rationale = (
            "grounded_information", "retrieve_and_quote_focused_approved_evidence",
            "grounded_explanation_requires_scoped_evidence")
    elif operation != "unknown":
        route, action, rationale = (
            "technical_action", "retrieve_then_apply_independent_scope_and_safety_gates",
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
