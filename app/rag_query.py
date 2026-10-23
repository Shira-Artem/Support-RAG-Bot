"""Build a bounded, standalone retrieval request from typed client facts."""
from __future__ import annotations

from app.dialogue_state import DialogueState


OPERATIONS = {
    "add_employee": "добавление сотрудника", "assign_role": "назначение роли сотруднику",
    "create_role": "создание роли", "view_reports": "просмотр отчётов",
    "change_permissions": "изменение прав существующего сотрудника",
    "reset_password": "восстановление пароля учётной записи", "search": "поиск",
    "list": "просмотр списка",
    "repeat_print": "повторная печать ранее выданного",
    "check": "проверка", "status": "проверка статуса", "diagnose": "диагностика ошибки",
    "connect": "подключение", "configure": "настройка", "close": "закрытие",
    "replace": "замена", "return": "возврат", "add": "добавление", "change": "изменение", "assign": "назначение",
    "correct": "исправление", "reconcile": "сверка расхождений",
    "transmit": "проверка передачи чеков и документов в ОФД",
}


class QueryNeedsClarification(ValueError):
    pass


def build_rag_query(state: DialogueState, max_chars: int = 500,
                    *, include_client_facts: bool = True) -> str:
    if state.analysis_required:
        raise QueryNeedsClarification("Message relationship is unresolved")
    if state.intent == "receipt" and state.operation == "search":
        task = "поиск чека"
    elif state.intent == "receipt" and state.operation == "repeat_print":
        task = "повторная печать ранее выданного чека"
    elif state.intent == "receipt" and state.operation == "transmit":
        task = "поиск документов, не переданных оператору ОФД"
    elif state.intent == "unknown" or state.operation in {"explain", "unknown"}:
        task = state.task.value if state.task else ""
    else:
        task = OPERATIONS[state.operation]
        if state.intent not in {"access", "credentials", "report"} and state.object and (
                state.operation != 'list' or state.intent == 'bank_statement') and not (
                    state.intent == 'receipt' and state.operation in {'repeat_print', 'transmit', 'search'}):
            task += " " + state.object
        if state.intent == "bank_statement" and state.operation == "list":
            task = "просмотр списка банковских выписок"
    entities = [f"{label}: {state.task_entity(slot)}" for slot, label in (
        ("service", "сервис"), ("equipment", "оборудование"), ("manufacturer", "производитель"),
        ("ofd", "ОФД"), ("software", "ПО")) if slot in state.task_entities and state.task_entity(slot)]
    required = [*entities, task]
    if state.error:
        required.append("код ошибки " + state.error.value)
    # Never cut the middle of a fact or drop an exclusion to satisfy the search
    # API limit. Oversized states need a targeted clarification/compression step.
    parts = [*required]
    # Keep the complete fact from the current task.  The typed operation and
    # object are useful routing hints, but they are not a substitute for the
    # client's parameters, conditions, numbers, or product/service names.
    # On the first turn this is the complete current request.  On later turns
    # the original text may contain a superseded service/model/code, so the
    # reducer-owned current facts below are the only safe source of additions.
    low_information_status = (state.intent == "receipt" and state.operation == "status"
                              and not state.parameters and not state.details
                              and not state.constraints and not state.goals
                              and not state.error)
    unresolved_access_task = state.intent == "access" and state.operation == "unknown"
    if (include_client_facts and state.task and state.revision <= 1
            and not low_information_status and not unresolved_access_task):
        parts.append("запрос клиента: " + state.task.value)
    if state.goals:
        parts.append("цель: " + "; ".join(f.value for f in state.goals))
    if state.constraints:
        parts.append("ограничения: " + "; ".join(f.value for f in state.constraints))
    if state.details:
        parts.append("уточнение клиента: " + "; ".join(f.value for f in state.details))
    if state.parameters:
        label = "параметры текущего поиска" if state.operation == "search" else "параметры клиента"
        parts.append(label + ": " + "; ".join(f.value for f in state.parameters))
    query = " — ".join(parts).strip()
    if not query or len(query) > max_chars:
        raise QueryNeedsClarification("Task and grounded requirements exceed retrieval budget")
    return query
