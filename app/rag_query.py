"""Build a bounded, standalone retrieval request from typed client facts."""
from __future__ import annotations

import re

from app.dialogue_state import DialogueState


OPERATIONS = {
    "add_employee": "добавление сотрудника", "assign_role": "назначение роли сотруднику",
    "create_role": "создание роли", "view_reports": "просмотр отчётов",
    "change_permissions": "изменение прав существующего сотрудника",
    "reset_password": "восстановление пароля учётной записи", "search": "поиск",
    "list": "просмотр списка",
    "repeat_print": "повторная печать ранее выданного",
    "check": "проверка", "status": "проверка статуса", "diagnose": "диагностика ошибки",
    "connect": "подключение", "configure": "настройка", "fiscalize": "фискализация", "close": "закрытие",
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
        ("ofd", "ОФД"), ("software", "ПО"), ("integration", "интеграция"))
        if slot in state.task_entities and state.task_entity(slot)]
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
    # The task fact is the immutable root request, not a first-message cache.
    # User refinements increment revision but must not erase the original
    # symptom/action from retrieval context; a new task gets a new task_fact.
    if (include_client_facts and state.task and state.task_id and state.operation != "explain"
            and not low_information_status and not unresolved_access_task):
        root_request = state.task.value
        # Keep root symptoms stable while removing facts explicitly superseded
        # later in this same task (service, device, operation, code). The
        # transcript remains intact in ConversationStore; only retrieval scope
        # follows the current task facts.
        active_entities = {(slot, fact.value)
                           for slot, facts in state.task_entities.items() for fact in facts}
        obsolete_entities = [
            fact
            for slot, facts in (state.task_context.entities.items() if state.task_context else [])
            for fact in facts
            if (slot, fact.value) not in active_entities
        ]
        redact = [*state.superseded_facts, *obsolete_entities]
        for fact in sorted(redact, key=lambda item: len(item.quote), reverse=True):
            if fact.quote:
                root_request = root_request.replace(fact.quote, " ")
        root_request = re.sub(r"\s+", " ", root_request).strip()
        if root_request:
            parts.append("запрос клиента: " + root_request)
    if state.goals:
        parts.append("цель: " + "; ".join(f.value for f in state.goals))
    if state.constraints:
        parts.append("ограничения: " + "; ".join(f.value for f in state.constraints))
    if state.details:
        # Reducer facts can overlap when one provider span is recorded both as
        # a whole reply and as its narrower goal/lead-in. Keep the longest
        # exact spans once; repeated history must not push an otherwise valid
        # follow-up over the retrieval character budget.
        detail_values = list(dict.fromkeys(f.value for f in state.details))
        normalized_details = [re.sub(r"\s+", " ", value).casefold().replace("ё", "е").strip()
                              for value in detail_values]
        anchors = [re.sub(r"\s+", " ", fact.value).casefold().replace("ё", "е").strip()
                   for fact in [*([state.task] if state.task else []), *state.goals,
                                *state.constraints, *state.parameters]]
        retained_details = [value for index, value in enumerate(detail_values)
            if not any(index != other and normalized_details[index] in normalized_details[other]
                       and normalized_details[index] != normalized_details[other]
                       for other in range(len(detail_values)))
            and not any(anchor in normalized_details[index] or normalized_details[index] in anchor
                        for anchor in anchors)]
        if retained_details:
            parts.append("уточнение клиента: " + "; ".join(retained_details))
    if state.parameters:
        label = "параметры текущего поиска" if state.operation == "search" else "параметры клиента"
        parts.append(label + ": " + "; ".join(f.value for f in state.parameters))
    query = " — ".join(parts).strip()
    if not query or len(query) > max_chars:
        raise QueryNeedsClarification("Task and grounded requirements exceed retrieval budget")
    return query
