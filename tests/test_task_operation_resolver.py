"""Independent phrasings and safety boundaries for the shared resolver."""
import pytest

from app.dialogue_state import DialogueManager, DialogueState
from app.dialogue_understanding import validate_response
from app.procedure_policy import operation_compatibility
from app.response_grounding import unsafe_operation_issue
from app.task_operation_resolver import resolve_task_operation


@pytest.mark.parametrize("text,task,operation", [
    ("Какие сведения сверить до фискализации облачной ККТ?", "service_connection", "fiscalize"),
    ("Покупатель возвращает часть товара; как оформить возврат?", "refund", "return"),
    ("У сервиса возник долг за обслуживание; где проверить состояние оплаты?", "billing", "check"),
    ("Можно ли проверить, заблокирован ли ФН?", "fiscal_drive", "check"),
    ("API интеграции отвечает, но результат запроса не виден; как тестировать?", "integration", "check"),
    ("Как узнать статус конкретного чека после контроля ФНС?", "receipt_status", "status"),
    ("Появилась ошибка ФН 7; какие первые проверки безопасны?", "error_diagnosis", "diagnose"),
    ("Внешний сканер не считывает штрихкоды; как проверить подключение?", "peripheral_setup", "check"),
    ("Добавьте нового пользователя кабинета и назначьте роль.", "access", "add_employee"),
    ("Чеки перестали передаваться оператору; как выяснить причину?", "receipt_transmission", "diagnose"),
])
def test_independent_task_paraphrases(text, task, operation):
    result = resolve_task_operation(text)
    assert (result.task_category, result.operation) == (task, operation)


def _payload(text, *, operation="procedure", intent="question", relation="new_task"):
    return {"request_type": "question", "relation": relation, "intent": intent,
        "operation": operation, "object": None, "object_evidence": None,
        "goal": {"quote": text}, "symptom": None, "entities": [], "unknown_facts": [],
        "specialist_requested": False, "specialist_evidence": None, "confidence": .9}


def test_operation_is_resolved_before_state_and_no_model_is_invented():
    text = "В aQsi Online требуется фискализация; с чего начать?"
    _, _, _, obs = validate_response(_payload(text), text, 1)
    state = DialogueManager().advance(DialogueState(), text, 1, observation=obs)
    assert (state.intent, state.operation) == ("device", "fiscalize")
    assert state.task_entity("service") == "aQsi Online"
    assert state.task_entity("equipment") is None
    assert state.task_entity("manufacturer") is None


def test_physical_aqsi_and_online_are_distinct_and_scanner_is_not_shtrih_brand():
    physical = "На aQsi внешний сканер штрихкодов не подключается."
    online = "В aQsi Online сканер не нужен; как настроить сервис?"
    _, _, _, p = validate_response(_payload(physical), physical, 1)
    _, _, _, o = validate_response(_payload(online), online, 2)
    assert [f.value for f in p.entities.get("manufacturer", [])] == ["aQsi"]
    assert not p.entities.get("service")
    assert [f.value for f in o.entities.get("service", [])] == ["aQsi Online"]
    assert not o.entities.get("manufacturer")


def test_cloud_atol_and_physical_atol_are_distinct():
    for text, slot in (("В АТОЛ Онлайн ошибка шлюза.", "service"),
                       ("На кассе АТОЛ 30Ф ошибка печати.", "manufacturer")):
        _, _, _, obs = validate_response(_payload(text), text, 1)
        assert obs.entities.get(slot)
        assert not obs.entities.get("manufacturer" if slot == "service" else "service")


def test_unknown_service_ffd_does_not_invent_atol():
    text = "Перед переходом на ФФД 1.2 что нужно проверить?"
    _, _, _, obs = validate_response(_payload(text), text, 1)
    assert resolve_task_operation(text).task_category == "fiscal_format"
    assert not obs.entities.get("service") and not obs.entities.get("manufacturer")


def test_refund_and_status_do_not_become_issue_or_correction():
    assert resolve_task_operation("Вернуть часть покупки по чеку.").task_category == "refund"
    assert resolve_task_operation("Проверить статус чека в ФНС.").task_category == "receipt_status"
    meta = {"task_category": "receipt_status", "operations": ["inspect_fns_status"],
            "_operations_explicit": True}
    assert operation_compatibility("status", meta, "Проверить статус чека в ФНС.",
                                   task_category="receipt_status") == "match"
    assert operation_compatibility("return", {"task_category": "receipt_issue",
        "operations": ["issue_receipt"], "_operations_explicit": True},
        "Вернуть часть покупки.", task_category="refund") == "mismatch"


def test_precise_metadata_operations_share_one_projection():
    cases = [("service_connection", "fiscalize", "fiscalize_cash_register"),
             ("billing", "check", "manage_billing"),
             ("peripheral_setup", "check", "configure_peripheral")]
    for task, operation, supported in cases:
        meta = {"task_category": task, "operations": [supported], "_operations_explicit": True}
        assert operation_compatibility(operation, meta, "Безопасная проверка",
                                       task_category=task) == "match"


def test_new_resolution_does_not_reclassify_followup_result():
    first = "На Эвотор 7.3 чеки перестали передаваться в ОФД."
    _, _, _, obs = validate_response(_payload(first, operation="diagnosis"), first, 1)
    state = DialogueManager().advance(DialogueState(), first, 1, observation=obs)
    followup = "Интернет проверен, работает."
    _, _, _, next_obs = validate_response(_payload(followup, operation="unknown",
        intent="unknown", relation="continue"), followup, 2)
    next_state = DialogueManager().advance(state, followup, 2, observation=next_obs)
    assert next_state.task_id == state.task_id
    assert next_state.operation == "diagnose"
    assert next_state.task_entity("equipment") == "Эвотор 7.3"


def test_dangerous_fiscal_actions_still_trigger_existing_guard():
    for text in ("Закрыть архив ФН самостоятельно", "Перерегистрировать ККТ без специалиста"):
        assert unsafe_operation_issue(text)
