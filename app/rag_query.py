"""Build a bounded, standalone retrieval request from typed client facts."""
from __future__ import annotations

from app.dialogue_state import DialogueState


OPERATIONS = {
    "add_employee": "добавление сотрудника", "assign_role": "назначение роли сотруднику",
    "change_permissions": "изменение прав существующего сотрудника",
    "reset_password": "восстановление пароля учётной записи", "search": "поиск",
    "check": "проверка", "status": "проверка статуса", "diagnose": "диагностика ошибки",
    "connect": "подключение", "configure": "настройка", "close": "закрытие",
    "replace": "замена", "return": "возврат", "add": "добавление", "change": "изменение", "assign": "назначение",
    "transmit": "проверка передачи чеков и документов в ОФД",
}


class QueryNeedsClarification(ValueError):
    pass


def build_rag_query(state: DialogueState, max_chars: int = 500) -> str:
    if state.analysis_required:
        raise QueryNeedsClarification("Message relationship is unresolved")
    if state.intent == "unknown" or state.operation in {"explain", "unknown"}:
        task = state.task.value if state.task else ""
    else:
        task = OPERATIONS[state.operation]
        if state.intent not in {"access", "credentials"} and state.object:
            task += " " + state.object
    entities = [f"{label}: {state.entity(slot)}" for slot, label in (
        ("service", "сервис"), ("equipment", "оборудование"), ("manufacturer", "производитель"),
        ("ofd", "ОФД"), ("software", "ПО")) if state.entity(slot)]
    required = [*entities, task]
    if state.error:
        required.append("код ошибки " + state.error.value)
    # Never cut the middle of a fact or drop an exclusion to satisfy the search
    # API limit. Oversized states need a targeted clarification/compression step.
    parts = [*required]
    if state.goals:
        parts.append("цель: " + "; ".join(f.value for f in state.goals))
    if state.constraints:
        parts.append("ограничения: " + "; ".join(f.value for f in state.constraints))
    if state.details:
        parts.append("уточнение клиента: " + "; ".join(f.value for f in state.details))
    query = " — ".join(parts).strip()
    if not query or len(query) > max_chars:
        raise QueryNeedsClarification("Task and grounded requirements exceed retrieval budget")
    return query
