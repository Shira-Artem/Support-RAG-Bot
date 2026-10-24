"""P0.4: contextual facts preserve the active task across product domains."""

import pytest

from app.dialogue_state import DialogueManager, DialogueState
from app.rag_query import build_rag_query


@pytest.mark.parametrize("first,followup,intent,operation,root", [
    (
        "В 1С перестали загружаться банковские выписки. Как разобраться?",
        "У нас 1С:Бухгалтерия 3.0, подключение к банку через DirectBank.",
        "bank_statement", "diagnose", "перестали загружаться",
    ),
    (
        "В 1С не загружаются выписки банка. Помогите выяснить причину.",
        "Работаем в 1С:Бухгалтерия 3.0, интеграция DirectBank уже настроена.",
        "bank_statement", "diagnose", "не загружаются выписки",
    ),
    (
        "Мне нужно проверить срок действия договора с ОФД. Как это сделать?",
        "У меня Платформа ОФД. Распиши подробно, куда заходить и что проверять.",
        "billing", "check", "срок действия договора",
    ),
    (
        "Касса Эвотор выдаёт ошибку 123. Как разобраться?",
        "У меня Эвотор 7.3.",
        "device", "diagnose", "ошибку 123",
    ),
])
def test_contextual_fact_keeps_task_and_root(first, followup, intent, operation, root):
    manager = DialogueManager()
    original = manager.advance(DialogueState(), first, 1)
    continued = manager.advance(original, followup, 2)
    assert continued.task_id == original.task_id
    assert (continued.intent, continued.operation) == (intent, operation)
    assert continued.task == original.task
    assert root.casefold() in build_rag_query(continued).casefold()
    assert followup.casefold() in build_rag_query(continued).casefold()


def test_expected_service_reply_preserves_contract_task_and_closes_slot():
    manager = DialogueManager()
    original = manager.advance(DialogueState(), "Как проверить срок договора с ОФД?", 1)
    waiting = manager.observe_answer(original, scenario="clarify", reason="service_not_confirmed",
                                    question="Какой ОФД?", slot="service")
    result = manager.advance(waiting, "У меня Платформа ОФД.", 2)
    assert result.task_id == original.task_id
    assert (result.intent, result.operation) == ("billing", "check")
    assert result.expected is None


def test_explicit_new_task_does_not_inherit_bank_facts():
    manager = DialogueManager()
    bank = manager.advance(DialogueState(), "В 1С не загружаются банковские выписки.", 1)
    bank = manager.advance(bank, "У нас 1С:Бухгалтерия, интеграция DirectBank.", 2)
    next_task = manager.advance(bank, "Другой вопрос: как добавить сотрудника в aQsi Online?", 3)
    assert next_task.task_id != bank.task_id
    query = build_rag_query(next_task)
    assert "DirectBank" not in query and "выписк" not in query.casefold()


def test_new_failure_mode_starts_new_task_without_old_symptom():
    manager = DialogueManager()
    bank = manager.advance(DialogueState(), "В 1С перестали загружаться банковские выписки.", 1)
    changed = manager.advance(bank, "Теперь касса Эвотор не печатает чеки.", 2)
    assert changed.task_id != bank.task_id
    assert changed.intent != "bank_statement"
    assert "выписк" not in build_rag_query(changed).casefold()


def test_explicit_command_for_other_object_is_new_task():
    manager = DialogueManager()
    bank = manager.advance(DialogueState(), "В 1С не загружаются банковские выписки.", 1)
    changed = manager.advance(bank, "Добавьте сотрудника в aQsi Online.", 2)
    assert changed.task_id != bank.task_id
    assert "выписк" not in build_rag_query(changed).casefold()


def test_service_correction_updates_route_inside_same_task():
    manager = DialogueManager()
    first = manager.advance(DialogueState(), "Как найти чек в Платформе ОФД?", 1)
    corrected = manager.advance(first, "Нет, у нас Первый ОФД.", 2)
    assert corrected.task_id == first.task_id
    assert corrected.routing_service == "Первый ОФД"
    assert "Платформа ОФД" not in build_rag_query(corrected)
