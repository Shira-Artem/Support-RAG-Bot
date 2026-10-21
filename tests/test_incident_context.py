"""Small offline regressions for the reported conversations and object binding."""
import asyncio

from app.answer_service import Answer
from app.conversation_store import ConversationStore
from app.dialogue_state import DialogueManager, DialogueState
from app.rag_query import build_rag_query
from scripts.replay_incident import replay


def test_seven_real_turns_keep_context_gate_knowledge_and_repair_recorded_output():
    rows = asyncio.run(replay())
    assert len(rows) == 7
    states = [row['after_user'] for row in rows]
    assert [s['operation'] for s in states] == [
        'add_employee', 'change_permissions', 'change_permissions', 'change_permissions',
        'list', 'search', 'search']
    assert rows[0]['answer']['text'].find('имя и email') >= 0
    assert not any(word in rows[0]['answer']['text'] for word in ('фамилию', 'пароль'))
    assert 'вой' not in rows[1]['answer']['text'].lower()  # unsupported login verification removed
    assert states[2]['goals'] and states[2]['constraints']
    assert 'меню этой записи' in rows[2]['answer']['text']
    assert 'aQsi' not in rows[3]['query']
    assert rows[3]['simulated_generation_calls'] == 0
    assert not rows[3]['answer']['retrieval_diagnostics']['selected']
    assert states[5]['entities']['ofd'] == states[4]['entities']['ofd'] == states[6]['entities']['ofd']
    assert states[6]['task_id'] == states[5]['task_id'] != states[4]['task_id']
    assert states[6]['object'] == 'чек' and states[6]['object_reference']['message_id'] == 61
    assert 'за прошлый месяц; по номеру ФН' in rows[6]['query']
    for row in rows[5:]:
        assert {d['source'] for d in row['answer']['retrieval_diagnostics']['selected']} == {
            'platformaofd/ofd/lkk-receipt-search.md'}
        assert 'Мониторинг' not in row['answer']['text']
    assert 'не подтверждён поиск по номеру ФН' in rows[6]['answer']['text']
    assert 'номер ФД' in rows[6]['answer']['text']
    assert rows[6]['answer']['response_repair']['mode'] == 'documented_search_scope'


def test_search_arguments_do_not_outrank_objects_or_explicit_new_operations():
    manager = DialogueManager()
    state = manager.advance(DialogueState(), 'Платформа ОФД, найти чек по номеру ФН 12345', 1)
    assert state.intent == 'receipt' and state.operation == 'search' and state.error is None
    state = manager.advance(state, 'А по сумме?', 2)
    assert state.intent == 'receipt' and state.object_reference.message_id == 2
    changed = manager.advance(state, 'А как заменить ФН?', 3)
    assert changed.intent == 'fiscal_drive' and changed.operation == 'replace'
    assert changed.task_id != state.task_id and not changed.parameters
    assert changed.entity('ofd') == 'Платформа ОФД'


def test_parameters_and_session_facts_survive_store_reload_without_changing_history(tmp_path):
    store = ConversationStore(tmp_path / 'conversation.sqlite3')
    cid = store.new(1, 1)
    for text in ['Платформа ОФД, касса Эвотор 6. Посмотреть список касс.',
                 'Найти чек за прошлый месяц.', 'А найти его по номеру ФД?']:
        pending = store.begin(cid, text)
        store.complete(pending, Answer('Ответ', scenario='answer'))
    state = ConversationStore(store.path).dialogue_state(cid)
    assert state.entity('ofd') == 'Платформа ОФД' and state.entity('equipment') == 'Эвотор 6'
    assert state.intent == 'receipt' and state.object == 'чек'
    assert state.object_reference and len(state.parameters) == 2
    assert state.routing_service == 'Платформа ОФД'
    assert 'Эвотор' not in build_rag_query(state)  # hardware must not hard-filter OFD receipt articles
    equipment_update = DialogueManager().advance(state, 'Касса АТОЛ', 98)
    assert equipment_update.routing_service == 'Платформа ОФД'
    assert equipment_update.entity('manufacturer') == 'АТОЛ'
    updated = DialogueManager().advance(state, 'За этот месяц', 99)
    query = build_rag_query(updated)
    assert 'прошлый' not in query and 'этот месяц' in query
    assert state.to_dict() == DialogueState.from_dict(state.to_dict()).to_dict()
