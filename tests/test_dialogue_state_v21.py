from __future__ import annotations

from app.answer_service import Answer, _pre_retrieval_clarification
from app.conversation_store import ConversationStore
from app.dialogue_state import DialogueManager, DialogueState
from app.procedure_policy import normalize_operation
from app.rag_query import QueryNeedsClarification, build_rag_query


def apply(manager, state, text, message_id):
    return manager.advance(state, text, message_id)


def observe_clarification(manager, state, slot="service"):
    return manager.observe_answer(state, scenario="clarify", reason=f"{slot}_not_confirmed",
                                  question=f"Уточните {slot}", message_id=f"assistant:{state.revision}", slot=slot)


def maybe_query(state):
    try:
        return build_rag_query(state)
    except QueryNeedsClarification:
        return None


def test_new_topic_after_pending_old_task_resets_task_and_preserves_history(tmp_path):
    manager = DialogueManager()
    state = apply(manager, DialogueState(), "Где в 1С открыть список банковских выписок?", 1)
    old_task, old_operation = state.task_id, state.operation
    state = observe_clarification(manager, state, "service")
    assert state.expected and state.task_id == old_task

    state = apply(manager, state, "А теперь другой вопрос. Как проверить срок договора Платформа ОФД?", 2)
    assert state.task_id != old_task
    assert state.relation == "new_task" and state.expected is None
    assert state.intent == "billing" and state.operation == "check"
    assert state.task_context.symptom is None
    query = build_rag_query(state)
    assert "банковских выписок" not in query
    assert "договор" in query

    # State reduction does not delete any conversation events.
    store = ConversationStore(tmp_path / "history.sqlite3", manager=manager)
    cid = store.new(1, 2)
    for text in ("Где в 1С открыть список банковских выписок?",
                 "А теперь другой вопрос. Как проверить срок договора Платформа ОФД?"):
        assistant_id = store.begin(cid, text)
        store.complete(assistant_id, Answer("ok"))
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (cid,)).fetchone()[0] == 4
    assert old_operation == "list"


def test_service_answer_completes_requested_slot_without_replacing_operation():
    manager = DialogueManager()
    state = apply(manager, DialogueState(), "В 1С перестали загружаться банковские выписки. Как разобраться?", 1)
    assert state.intent == "bank_statement" and state.operation == "diagnose"
    task_id, symptom = state.task_id, state.symptom.value
    state = observe_clarification(manager, state, "service")
    state = apply(manager, state, "В 1С:Бухгалтерия, подключение к банку через DirectBank.", 2)
    assert state.task_id == task_id
    assert state.intent == "bank_statement" and state.operation == "diagnose"
    assert state.symptom.value == symptom
    assert state.routing_service == "1С" and state.task_entity("software") == "1С"
    assert state.task_entity("integration") == "DirectBank"
    assert state.expected is None
    assert state.relation == "answer_to_clarification"
    query = build_rag_query(state)
    assert "перестали загружаться банковские выписки" in query and "DirectBank" in query


def test_repeated_question_keeps_meaning_and_root_request_in_query():
    manager = DialogueManager()
    text = "В 1С перестали загружаться банковские выписки. Как разобраться?"
    first = apply(manager, DialogueState(), text, 1)
    first_query = build_rag_query(first)
    repeated = apply(manager, first, text, 2)
    assert repeated.task_id == first.task_id
    assert repeated.intent == first.intent and repeated.operation == first.operation == "diagnose"
    assert repeated.revision == 2
    assert build_rag_query(repeated) == first_query
    assert repeated.symptom.value == first.symptom.value


def test_added_employee_retains_view_only_goal_and_no_settings_constraint():
    manager = DialogueManager()
    state = apply(manager, DialogueState(), "Как добавить сотрудника в личный кабинет?", 1)
    assert state.intent == "access" and state.operation == "add_employee"
    task_id = state.task_id
    state = observe_clarification(manager, state, "service")
    state = apply(manager, state,
                  "В aQsi Online: он должен просматривать документы, но не менять настройки.", 2)
    assert state.task_id == task_id and state.intent == "access" and state.operation == "add_employee"
    assert state.routing_service == "aQsi Online"
    assert state.goals and any("просматривать документы" in f.value for f in state.goals)
    assert state.constraints and any("не менять настройки" in f.value for f in state.constraints)
    query = build_rag_query(state)
    assert "просматривать документы" in query and "не менять настройки" in query


def test_billing_lifecycle_paraphrases_do_not_guess_status_payment_or_renewal():
    manager = DialogueManager()
    ambiguous = (
        "У меня проблема, похоже закончился договор с ОФД.",
        "Кажется, истёк тариф обслуживания ОФД.",
        "Не проходит оплата Платформа ОФД.",
        "Нужно продлить тариф ОФД.",
    )
    for message_id, text in enumerate(ambiguous, 1):
        state = apply(manager, DialogueState(), text, message_id)
        assert state.intent == "billing"
        assert state.operation == "unknown" and state.analysis_required
        assert maybe_query(state) is None
        if "оплата" in text:
            assert state.symptom and state.symptom.value == "Не проходит"

    explicit = apply(manager, DialogueState(), "Как проверить срок действия договора с Платформа ОФД?", 10)
    assert explicit.intent == "billing" and explicit.operation == "check"
    assert not explicit.analysis_required
    assert normalize_operation(explicit.operation, "billing", explicit.task.value) == "check_contract_status"
    assert "срок действия договора" in build_rag_query(explicit)


def test_new_same_domain_failure_does_not_inherit_old_operation():
    manager = DialogueManager()
    old = apply(manager, DialogueState(), "Как проверить статус договора ОФД?", 1)
    assert old.intent == "billing" and old.operation == "check"
    new = apply(manager, old, "Не проходит оплата ОФД.", 2)
    assert new.task_id != old.task_id
    assert new.relation == "new_task"
    assert new.operation == "unknown" and new.analysis_required
    assert new.symptom and old.symptom is None
    assert maybe_query(new) is None


def test_directbank_symptom_and_plain_list_are_distinct_operations():
    manager = DialogueManager()
    fault = apply(manager, DialogueState(), "В 1С перестали загружаться банковские выписки.", 1)
    listing = apply(manager, DialogueState(), "Где открыть список банковских выписок?", 2)
    assert (fault.intent, fault.operation) == ("bank_statement", "diagnose")
    assert fault.symptom and fault.operation_confidence >= 0.8
    assert (listing.intent, listing.operation) == ("bank_statement", "list")
    assert listing.symptom is None


def test_fiscal_change_asks_for_exact_target_and_equipment_before_procedure():
    manager = DialogueManager()
    state = apply(manager, DialogueState(), "Нужно изменить настройки фискального накопителя.", 1)
    assert state.intent == "fiscal_drive" and state.operation == "change"
    clarification = _pre_retrieval_clarification(state)
    assert clarification and clarification[1] == "fiscal_drive_change_scope_missing"
    task_id = state.task_id
    state = observe_clarification(manager, state, "details")
    state = apply(manager, state, "АТОЛ 30Ф, нужно изменить ставку НДС.", 2)
    assert state.task_id == task_id and state.intent == "fiscal_drive" and state.operation == "change"
    assert state.task_entity("equipment") == "АТОЛ 30Ф"
    assert state.details
    clarification = _pre_retrieval_clarification(state)
    assert clarification is None
    assert "ставку НДС" in build_rag_query(state)


def test_service_confirmation_and_explicit_topic_switch_persist_as_events(tmp_path):
    manager = DialogueManager()
    store = ConversationStore(tmp_path / "turns.sqlite3", manager=manager)
    cid = store.new(44, 55)
    first_id = store.begin(cid, "Как добавить сотрудника в личный кабинет?")
    first = store.dialogue_state(cid)
    store.complete(first_id, Answer(
        "Какой сервис?", scenario="clarify", scenario_reason="service_not_confirmed",
        clarification_slot="service"))
    confirmed_id = store.begin(cid, "aQsi Online")
    confirmed = store.dialogue_state(cid)
    assert confirmed.task_id == first.task_id and confirmed.expected is None
    assert confirmed.routing_service == "aQsi Online"
    store.complete(confirmed_id, Answer("ok"))

    old_task_id = confirmed.task_id
    switch_id = store.begin(cid, "А теперь другой вопрос: как проверить срок договора Платформа ОФД?")
    switched = store.dialogue_state(cid)
    assert switched.task_id != old_task_id and switched.expected is None
    assert switched.intent == "billing" and switched.operation == "check"
    with store.connect() as db:
        rows = db.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
    assert len(rows) == 6 and rows[-2]["role"] == "user" and rows[-2]["content"].startswith("А теперь")
