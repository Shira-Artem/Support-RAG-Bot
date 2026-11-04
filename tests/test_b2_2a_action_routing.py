import pytest

from app.ai_coordinator import coordinate
from app.dialogue_state import DialogueManager, DialogueState
from app.dialogue_understanding import validate_response


def _validated(question, *, operation="explain", subject="банковская выписка", evidence="выписки"):
    raw = {"request_type": "information", "relation": "new_task", "intent": "general",
           "operation": operation, "object": subject,
           "object_evidence": {"quote": evidence} if subject else None,
           "goal": {"quote": question}, "symptom": None, "entities": [], "unknown_facts": [],
           "specialist_requested": False, "specialist_evidence": None, "confidence": 0.9}
    kind, _, _, obs = validate_response(raw, question, 1)
    obs.request_type = kind
    state = DialogueManager().advance(DialogueState(), question, 1, observation=obs)
    return obs, coordinate({"request_type": kind}, state)


@pytest.mark.parametrize("question,subject,evidence", [
    ("Как загрузить банковские выписки?", "банковская выписка", "выписки"),
    ("Как подключить кассу?", "касса", "кассу"),
    ("Как напечатать чек?", "чек", "чек"),
])
def test_action_goal_can_reach_retrieval_without_inventing_operation(question, subject, evidence):
    obs, decision = _validated(question, subject=subject, evidence=evidence)
    assert obs.operation != "explain"
    assert decision.route == "technical_action"


def test_concept_question_stays_explanation():
    obs, decision = _validated("Что такое ОФД и зачем он нужен?", subject="ОФД", evidence="ОФД")
    assert obs.operation == "explain"
    assert decision.route == "grounded_information"


def test_reported_failure_remains_diagnosis():
    obs, decision = _validated("Почему банковские выписки не загружаются через DirectBank?", evidence="выписки")
    assert obs.operation == "diagnose"
    assert decision.route == "technical_action"
