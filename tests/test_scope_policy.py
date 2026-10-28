from hashlib import sha256
import json

from app.dialogue_state import DialogueState, Fact
from app.semantic_evidence_selector import EvidenceDecision, EvidenceUnit, validate_selected_units
from app.scope_policy import (assess_source_scope, manufacturer_from_equipment,
                              matches_scope_value)


def _state(**entities):
    state = DialogueState(intent="device", operation="diagnose")
    state.task_context.entities = {
        slot: [Fact.span(value, "scope-test")]
        for slot, value in entities.items()
    }
    return state


def test_scope_aliases_keep_physical_and_online_products_distinct():
    assert matches_scope_value("aQsi", "aQsi")
    assert matches_scope_value("АТОЛ Онлайн", "АТОЛ online")
    assert not matches_scope_value("aQsi", "aQsi Online")
    assert not matches_scope_value("АТОЛ", "АТОЛ Онлайн")


def test_hardware_manufacturer_can_satisfy_redundant_vendor_service_label():
    state = _state(manufacturer="aQsi", equipment="aQsi физическая ККТ")
    result = assess_source_scope(state, {
        "service": "aQsi", "manufacturer": "aQsi",
        "model": "aQsi (физическая ККТ)", "task_category": "peripheral_setup",
    })
    assert result.missing == ()
    assert result.mismatches == ()


def test_physical_manufacturer_does_not_confirm_aqsi_online_service():
    state = _state(manufacturer="aQsi")
    result = assess_source_scope(state, {
        "service": "aQsi Online", "manufacturer": "aQsi",
        "model": "aQsi Online (облачная касса)", "task_category": "refund",
    })
    assert result.missing == ("service",)
    assert result.mismatches == ()


def test_atol_online_service_is_not_physical_atol_device_scope():
    physical = assess_source_scope(_state(manufacturer="АТОЛ"), {
        "service": "АТОЛ Онлайн", "manufacturer": "АТОЛ",
        "model": "АТОЛ Онлайн cloud KKT", "task_category": "receipt_transmission",
    })
    cloud = assess_source_scope(_state(service="АТОЛ Онлайн"), {
        "service": "АТОЛ Онлайн", "manufacturer": "АТОЛ",
        "model": "АТОЛ Онлайн cloud KKT", "task_category": "receipt_transmission",
    })
    assert "service" in physical.mismatches
    assert cloud.missing == ()
    assert cloud.mismatches == ()


def test_selector_validator_uses_the_shared_source_scope_policy(tmp_path):
    text = "## Проверенная информация\nСовместимость зависит от модели сканера."
    source_text = (
        "---\n"
        "document_id: physical-scanner\n"
        "status: approved\n"
        "service: aQsi\n"
        "manufacturer: aQsi\n"
        "model: ''\n"
        "task_category: peripheral_setup\n"
        "---\n\n"
        + text + "\n"
    )
    path = tmp_path / "physical-scanner.md"
    path.write_text(source_text, encoding="utf-8")
    digest = sha256(path.read_bytes()).hexdigest()
    unit = EvidenceUnit("unit-1", "physical-scanner", path.name, digest,
        "Проверенная информация", 1, "Совместимость зависит от модели сканера.",
        "sentence", {"service": "aQsi", "manufacturer": "aQsi",
                     "task_category": "peripheral_setup"}, True)
    state = _state(manufacturer="aQsi")
    decision = EvidenceDecision("select", (unit.id,), None, "direct_evidence", "{}")
    selected, rejection = validate_selected_units(decision, [unit], state, tmp_path,
                                                   informational=False)
    assert rejection is None
    assert selected == [unit]


def test_scope_policy_distinguishes_unknown_from_confirmed_conflict():
    source = {"service": "aQsi Online", "manufacturer": "aQsi",
              "model": "aQsi Online cloud KKT", "task_category": "refund"}
    unknown = assess_source_scope(_state(), source)
    conflict = assess_source_scope(_state(service="АТОЛ Онлайн"), source)
    assert unknown.missing == ("service",)
    assert unknown.mismatches == ()
    assert conflict.missing == ()
    assert conflict.mismatches == ("service",)


def test_registered_equipment_brand_satisfies_manufacturer_without_inventing_model():
    scope = {"service": "Эвотор", "manufacturer": "Эвотор", "model": None,
             "task_category": "error_diagnosis"}
    assert assess_source_scope(_state(equipment="Эвотор"), scope).missing == ()
    assert assess_source_scope(_state(equipment="Эвотор 7.3"), scope).missing == ()
    assert manufacturer_from_equipment("Эвотор 7.3") == "Эвотор"
    assert manufacturer_from_equipment("7.3") is None
    assert manufacturer_from_equipment("АТОЛ Онлайн") is None
    assert "manufacturer" in assess_source_scope(
        _state(manufacturer="aQsi", equipment="Эвотор 7.3"), scope).mismatches
