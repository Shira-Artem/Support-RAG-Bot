from __future__ import annotations

import pytest

from scripts.compare_dialogue_analyzers import (
    build_schema, validate_payload,
)


def payload(**overrides):
    result = {
        "intent": "unknown", "operation": "unknown", "object": None, "entities": [],
        "symptom": None, "error": None, "goals": [], "constraints": [], "details": [],
        "parameters": [], "relation": "unknown", "new_topic": False, "reference": False,
        "question": False, "requirement": False, "entity_only": False, "feedback": False,
        "uncertain": True, "binds_object": False, "confidence": 0.3,
        "intent_confidence": 0.0, "operation_confidence": 0.0, "relation_confidence": 0.3,
        "intent_evidence": None, "object_evidence": None, "operation_evidence": None,
        "relation_evidence": None,
    }
    result.update(overrides)
    return result


def test_schema_is_strict_and_uses_dialogue_state_vocabularies():
    schema = build_schema()
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert "answer_to_clarification" in schema["schema"]["properties"]["relation"]["enum"]
    assert "diagnose" in schema["schema"]["properties"]["operation"]["enum"]


def test_valid_payload_must_ground_typed_claims_in_exact_message_spans():
    text = "В 1С DirectBank перестали загружаться банковские выписки."
    result = payload(
        intent="bank_statement", operation="diagnose", object="банковская выписка",
        entities=[{"slot": "software", "value": "1С", "evidence": {"quote": "1С"}},
                  {"slot": "integration", "value": "DirectBank", "evidence": {"quote": "DirectBank"}}],
        symptom={"quote": "перестали загружаться банковские выписки"},
        relation="new_task", new_topic=True, uncertain=False, confidence=.9,
        intent_confidence=.9, operation_confidence=.9, relation_confidence=.9,
        intent_evidence={"quote": "банковские выписки"},
        object_evidence={"quote": "банковские выписки"},
        operation_evidence={"quote": "перестали загружаться"},
        relation_evidence={"quote": "перестали загружаться банковские выписки"},
    )
    observation = validate_payload(result, text, "m1")
    assert observation.operation == "diagnose"
    assert observation.entities["integration"][0].value == "DirectBank"
    assert observation.symptom.quote in text


def test_equipment_slot_accepts_only_a_value_verbatim_in_its_evidence():
    text = "Касса АТОЛ 30Ф"
    result = payload(entities=[{"slot": "equipment", "value": "АТОЛ 30Ф",
                               "evidence": {"quote": "АТОЛ 30Ф"}}])
    observation = validate_payload(result, text, "m1")
    assert observation.entities["equipment"][0].value == "АТОЛ 30Ф"
    result["entities"][0]["value"] = "АТОЛ 55Ф"
    with pytest.raises(ValueError, match="grounded"):
        validate_payload(result, text, "m1")


@pytest.mark.parametrize("mutation", ["invented_intent", "invalid_relation", "unquoted_span",
                                      "invented_entity", "mismatched_object", "topic_relation_conflict"])
def test_invalid_semantic_claim_is_reported_instead_of_falling_back(mutation):
    text = "Платформа ОФД"
    result = payload()
    if mutation == "invented_intent":
        result["intent"] = "refund_case"
    elif mutation == "invalid_relation":
        result["relation"] = "same_task"
    elif mutation == "unquoted_span":
        result.update(intent="billing", intent_confidence=.9,
                      intent_evidence={"quote": "договор истёк"})
    elif mutation == "mismatched_object":
        result.update(intent="bank_statement", object="договор")
    elif mutation == "topic_relation_conflict":
        result.update(new_topic=True, relation="continue", relation_evidence={"quote": text})
    else:
        result["entities"] = [{"slot": "service", "value": "АТОЛ Онлайн",
                               "evidence": {"quote": "Платформа ОФД"}}]
    with pytest.raises(ValueError):
        validate_payload(result, text, "m1")


def test_validation_rejects_non_boolean_flags_and_non_unique_evidence():
    text = "ОФД, ОФД"
    bad_flag = payload(question="false")
    with pytest.raises(ValueError, match="boolean"):
        validate_payload(bad_flag, text, "m1")
    repeated = payload(intent="billing", intent_confidence=.9,
                       intent_evidence={"quote": "ОФД"})
    with pytest.raises(ValueError, match="unique"):
        validate_payload(repeated, text, "m1")
