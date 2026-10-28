import asyncio
import json
import sqlite3

import pytest

from app.answer_service import Answer, AnswerService
from app.conversation_store import ConversationStore
from app.dialogue_state import DialogueManager, DialogueState, Fact, Observation
from app.llm_client import Generation
from app.rag import SearchResult
from app.rag_query import QueryNeedsClarification, build_rag_query
from test_expert import settings


QUESTIONS = [
    'Как добавить сотрудника в aQsi Online?',
    'А какую роль ему назначить?',
    'Мне нужно, чтобы он мог смотреть кассы и отчёты, но не менять настройки.',
    'А где изменить права уже созданному сотруднику?',
    'А если я использую АТОЛ Онлайн, там это делается так же?',
]


def test_exact_chain_persisted_state_queries_and_generation_boundary(tmp_path, monkeypatch):
    path = tmp_path / 'chat.sqlite3'
    store = ConversationStore(path)
    cid = store.new(1, 1)
    searches, prompts, snapshots = [], [], []

    class Rag:
        def search_for_service(self, query, service, top_k):
            searches.append((query, service))
            return [SearchResult('aqsi_online/account/add-user.md',
                                 'Администратор создаёт пользователя в разделе «Пользователи».', .9,
                                 metadata={'category': 'account'})] if service == 'aQsi Online' else []

        def build_context(self, results):
            return '\n'.join(r.text for r in results)

    async def fake_generate(messages, config):
        prompts.append(messages)
        return Generation(json.dumps({'scenario': 'answer', 'response': 'Подтверждённых сведений недостаточно.'}), 'model')

    monkeypatch.setattr('app.answer_service.generate', fake_generate)
    service = AnswerService(Rag(), settings(tmp_path))
    for n, question in enumerate(QUESTIONS):
        store = ConversationStore(path)  # every turn simulates a restart
        pending = store.begin(cid, question)
        state = store.dialogue_state(cid)
        answer = asyncio.run(service.answer(question, state=state))
        store.complete(pending, answer)
        snapshots.append(state)
        assert answer.confirmed_service == ('АТОЛ Онлайн' if n == 4 else 'aQsi Online')
        assert answer.scenario_reason != 'service_not_confirmed'
        assert answer.rag_query == build_rag_query(state)
        assert state.revision == n + 1
    assert [s.operation for s in snapshots] == ['add_employee', 'assign_role', 'assign_role', 'change_permissions', 'change_permissions']
    assert [s.transition for s in snapshots] == ['new_task', 'continue_task', 'refine_requirements', 'continue_task', 'change_service']
    assert len({s.task_id for s in snapshots}) == 1
    assert snapshots[2].goals and snapshots[2].constraints
    assert snapshots[4].goals == snapshots[2].goals and snapshots[4].constraints == snapshots[2].constraints
    query = searches[-1][0]
    assert all(term in query for term in ('АТОЛ Онлайн', 'изменение прав существующего сотрудника', 'кассы', 'отчёты', 'не менять настройки'))
    assert 'aQsi' not in query and 'Viewer' not in query and 'Read-only' not in query
    assert len(prompts) == 4  # missing ATOL docs don't cause an extra generation
    reloaded = ConversationStore(path).dialogue_state(cid)
    assert reloaded.to_dict() == store.dialogue_state(cid).to_dict()
    with store.connect() as db:
        rows = db.execute('SELECT * FROM messages ORDER BY id').fetchall()
        assert len(rows) == 10
        user_text = {r['id']: r['content'] for r in rows if r['role'] == 'user'}
        assert db.execute('SELECT count(*) FROM dialogue_turns').fetchone()[0] == 5
    facts = [f for values in reloaded.entities.values() for f in values]
    facts += [reloaded.task, reloaded.operation_evidence, *reloaded.goals, *reloaded.constraints]
    assert all(f.quote == user_text[f.message_id][f.start:f.end] for f in facts)


@pytest.mark.parametrize('chain', [
    ['Как пригласить коллегу в aQsi Online?', 'Какие полномочия ему выдать?',
     'Пусть он просматривает отчёты и кассы, без редактирования параметров.',
     'Как отредактировать доступ этого пользователя?', 'В АТОЛ Онлайн это тоже возможно?'],
    ['Хочу создать пользователя в aQsi Online', 'Какую роль выбрать для него?',
     'Ему нужен просмотр отчётов, но нельзя изменять настройки.',
     'Где поменять права сотрудника?', 'Использую АТОЛ Онлайн'],
])
def test_paraphrases_keep_goal_and_change_only_service(chain):
    manager, state = DialogueManager(), DialogueState()
    states = []
    for i, text in enumerate(chain):
        state = manager.advance(state, text, i + 1)
        states.append(state)
    assert all(s.entity('service') == 'aQsi Online' for s in states[:4])
    assert state.entity('service') == 'АТОЛ Онлайн'
    assert len({s.task_id for s in states}) == 1
    assert state.intent == 'access'
    assert state.goals and state.constraints
    assert 'aQsi' not in build_rag_query(state)


def test_equipment_manufacturer_ofd_and_cloud_are_independent():
    manager = DialogueManager()
    state = manager.advance(DialogueState(), 'Касса Эвотор 6, ОФД Такском. Как найти чек?', 1)
    assert state.entity('manufacturer') == 'Эвотор'
    assert state.entity('equipment') == 'Эвотор 6'
    assert state.entity('ofd') == 'Такском'
    assert state.entity('service') is None
    updated = manager.advance(state, 'Теперь ОФД Первый ОФД', 2)
    assert updated.transition == 'change_parameter' and updated.entity('equipment') == 'Эвотор 6'
    updated = manager.advance(state, 'ОФД Первый ОФД', 3)
    assert updated.entity('ofd') == 'Первый ОФД'
    assert updated.entity('equipment') == 'Эвотор 6'
    cloud = manager.advance(updated, 'В aQsi Online', 4)
    assert cloud.entity('service') == 'aQsi Online'
    assert cloud.entity('ofd') == 'Первый ОФД' and cloud.entity('manufacturer') == 'Эвотор'
    query = build_rag_query(cloud)
    assert all(s in query for s in ('aQsi Online', 'поиск', 'чек'))
    assert 'Эвотор' not in query and 'Первый ОФД' not in query
    assert cloud.entity('equipment') == 'Эвотор 6' and cloud.entity('ofd') == 'Первый ОФД'
    changed = manager.advance(cloud, 'Касса АТОЛ', 5)
    assert changed.entity('equipment') is None and changed.entity('manufacturer') == 'АТОЛ'
    assert changed.entity('ofd') == 'Первый ОФД'


@pytest.mark.parametrize('new_question', ['Что такое маркировка?', 'Как восстановить пароль в Эвотор?',
                                           'Другой вопрос: где найти чек?', 'Как вернуть чек в АТОЛ Онлайн?'])
def test_independent_task_resets_requirements_but_keeps_session_entities(new_question):
    manager, state = DialogueManager(), DialogueState()
    for i, question in enumerate(QUESTIONS[:3]):
        state = manager.advance(state, question, i + 1)
    new = manager.advance(state, new_question, 4)
    assert new.task_id != state.task_id and new.transition == 'new_task'
    assert not new.goals and not new.constraints
    assert new.entity('service') == ('АТОЛ Онлайн' if 'АТОЛ Онлайн' in new_question else 'aQsi Online')
    if 'Эвотор' in new_question:
        assert new.routing_service == 'Эвотор'
        assert new.entity('service') == 'aQsi Online'  # session fact, not the active cabinet


def test_expected_slot_short_replies_and_no_assistant_facts(tmp_path):
    manager = DialogueManager()
    state = manager.advance(DialogueState(), 'Как добавить сотрудника?', 1)
    state = manager.observe_answer(state, scenario='clarify', reason='service_not_confirmed',
                                   question='В каком сервисе?', message_id=2)
    ambiguous = manager.advance(state, 'Мой ОФД?', 3)
    assert ambiguous.expected.slot == 'service' and ambiguous.routing_service is None
    state = manager.advance(ambiguous, 'aQsi Online', 4)
    assert state.expected is None and state.intent == 'access'
    state = manager.observe_answer(state, scenario='answer', reason=None,
                                   question='Назначьте Viewer в АТОЛ Онлайн с полным доступом.', message_id=5)
    assert 'Viewer' not in json.dumps(state.to_dict(), ensure_ascii=False)
    assert state.entity('service') == 'aQsi Online'
    state = manager.observe_answer(state, scenario='clarify', reason=None, question='Что ему нужно?', slot='goal')
    assert state.expected.slot == 'goal'
    state = manager.advance(state, 'Он должен смотреть отчёты, без изменения настроек.', 6)
    assert state.goals and state.constraints and state.expected is None
    feedback = manager.advance(state, 'Не помогло', 7)
    assert feedback.task_id == state.task_id and not feedback.analysis_required


def test_unknown_relationship_and_over_budget_ask_without_network(tmp_path, monkeypatch):
    manager = DialogueManager()
    state = manager.advance(DialogueState(), QUESTIONS[0], 1)
    state = manager.advance(state, 'Ещё возникла непонятная ситуация с лицензией', 2)
    assert state.analysis_required and state.unresolved.message_id == 2
    with pytest.raises(QueryNeedsClarification):
        build_rag_query(state)
    class Rag:
        def search(self, *args, **kwargs): raise AssertionError('No search for unresolved task')
    async def no_generate(*args): raise AssertionError('No automatic analyser or generator call')
    monkeypatch.setattr('app.answer_service.generate', no_generate)
    service = AnswerService(Rag(), settings(tmp_path))
    answer = asyncio.run(service.answer('Ещё возникла непонятная ситуация с лицензией', state=state))
    assert answer.scenario == 'clarify' and answer.clarification_slot == 'task'
    awaiting = manager.observe_answer(state, scenario=answer.scenario, reason=answer.scenario_reason,
                                       question=answer.text, slot=answer.clarification_slot)
    assert manager.advance(awaiting, 'Да', 3).analysis_required
    long = manager.advance(DialogueState(), QUESTIONS[0], 1)
    long.constraints.append(Fact.span('не ' + 'менять параметры ' * 60, 2))
    with pytest.raises(QueryNeedsClarification):
        build_rag_query(long)
    answer = asyncio.run(service.answer('Длинные требования', state=long))
    assert answer.scenario_reason == 'query_budget_exceeded'
    awaiting = manager.observe_answer(long, scenario=answer.scenario, reason=answer.scenario_reason,
                                       question=answer.text, slot=answer.clarification_slot)
    concise = manager.advance(awaiting, 'Как изменить права сотрудника? Только чтение отчётов, без изменения настроек.', 3)
    assert concise.entity('service') == 'aQsi Online'
    assert len(concise.constraints) == 2
    assert len(build_rag_query(concise)) < 500
    assert not concise.analysis_required


def test_analyser_boundary_rejects_fabricated_provenance():
    class BadAnalyzer:
        def analyze(self, text, message_id, state):
            return Observation(entities={'service': [Fact('aQsi Online', 'assistant:9', 'aQsi', 0, 4)]})
    with pytest.raises(ValueError, match='client message'):
        DialogueManager(BadAnalyzer()).advance(DialogueState(), 'aQsi', 1)


def test_additive_legacy_migration_once_preserves_every_old_row(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.sqlite3'
    # Schema exactly as it existed before structured state.
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE conversations(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE chat_state(user_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,mode TEXT NOT NULL,conversation_id TEXT,PRIMARY KEY(user_id,chat_id));
            CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL,continuation INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'complete',diagnostics_json TEXT);
            INSERT INTO conversations VALUES('old',1,1,'2026-10-19');
            INSERT INTO chat_state VALUES(1,1,'free','old');
        ''')
        for question in QUESTIONS:
            db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES('old','user',?,'old')", (question,))
            db.execute("INSERT INTO messages(conversation_id,role,content,created_at,diagnostics_json) VALUES('old','assistant',?,'old',?)",
                       ('Назначьте Viewer в Диадок.', json.dumps({'scenario': 'answer'})))
        before = db.execute('SELECT * FROM messages').fetchall()
    store = ConversationStore(path)
    state = store.dialogue_state('old')
    assert state.entity('service') == 'АТОЛ Онлайн' and state.operation == 'change_permissions'
    assert state.goals and state.constraints and state.revision == 5
    assert 'Viewer' not in json.dumps(state.to_dict(), ensure_ascii=False)
    with store.connect() as db:
        assert [tuple(r) for r in db.execute('SELECT * FROM messages')] == before
        assert tuple(db.execute('SELECT * FROM chat_state').fetchone()) == (1, 1, 'free', 'old')
    def no_replay(*args): raise AssertionError('Existing messages must not be classified again')
    monkeypatch.setattr(DialogueManager, 'advance', no_replay)
    restarted = ConversationStore(path)
    assert restarted.dialogue_state('old').to_dict() == state.to_dict()
    assert len(restarted.history('old')) == 10


def test_pending_turn_recovery_does_not_duplicate_user_event(tmp_path):
    path = tmp_path / 'pending.sqlite3'
    store = ConversationStore(path)
    cid = store.new(1, 1)
    pending = store.begin(cid, QUESTIONS[0])
    before = store.dialogue_state(cid)
    with pytest.raises(RuntimeError, match='pending'):
        store.begin(cid, 'another question')
    store = ConversationStore(path)
    store.recover_pending()
    state = store.dialogue_state(cid)
    assert state.revision == 1 and state.task_id == before.task_id
    store.complete(pending, Answer('Late completion'))
    assert store.history(cid)[-1]['content'] != 'Late completion'


def test_state_round_trip_and_long_history_preserve_old_provenance(tmp_path):
    store = ConversationStore(tmp_path / 'long.sqlite3')
    cid = store.new(1, 1)
    for text in [QUESTIONS[0], QUESTIONS[2], *(['Не помогло'] * 20), QUESTIONS[-1]]:
        pending = store.begin(cid, text)
        store.complete(pending, Answer('Ответ', scenario='answer'))
    state = store.dialogue_state(cid)
    assert state.entity('service') == 'АТОЛ Онлайн' and state.goals and state.constraints
    assert len(store.history(cid)) <= 13
    assert DialogueState.from_dict(state.to_dict()).to_dict() == state.to_dict()
    assert len(build_rag_query(state)) <= 500


def test_model_expected_slot_is_persisted_but_model_response_is_not_evidence(tmp_path, monkeypatch):
    store = ConversationStore(tmp_path / 'expected.sqlite3')
    cid = store.new(1, 1)
    class Rag:
        def search(self, query, top_k):
            return [SearchResult('aqsi_online/account/add-user.md', 'Создание пользователя администратором.', .9)]
        def build_context(self, results): return results[0].text
    async def fake_generate(*args):
        return Generation(json.dumps({'scenario': 'clarify', 'clarification_slot': 'goal',
                                      'response': 'Какие действия должен выполнять сотрудник?'}), 'model')
    monkeypatch.setattr('app.answer_service.generate', fake_generate)
    pending = store.begin(cid, QUESTIONS[0])
    answer = asyncio.run(AnswerService(Rag(), settings(tmp_path)).answer(QUESTIONS[0], state=store.dialogue_state(cid)))
    store.complete(pending, answer)
    assert store.dialogue_state(cid).expected.slot == 'goal'
    pending = store.begin(cid, 'Только чтение отчётов')
    state = store.dialogue_state(cid)
    assert state.expected is None and state.constraints
    assert state.entity('service') == 'aQsi Online' and state.operation == 'add_employee'
    assert 'Какие действия' not in build_rag_query(state)
    store.complete(pending, Answer('Нужна документация', scenario='escalate'))


def test_switched_service_prompt_contains_no_obsolete_service_or_bot_claims(tmp_path, monkeypatch):
    manager, state = DialogueManager(), DialogueState()
    for i, text in enumerate(QUESTIONS):
        state = manager.advance(state, text, i + 1)
    captured = []
    class Rag:
        def search_for_service(self, query, service, top_k):
            assert service == 'АТОЛ Онлайн'
            return [SearchResult('atol_online/account/users.md', 'Сотрудники и права доступа.', .9,
                                 metadata={'category': 'account'})]
        def build_context(self, results): return results[0].text
    async def fake_generate(messages, config):
        captured.extend(messages)
        return Generation(json.dumps({'scenario': 'answer', 'response': 'Данных о ролях недостаточно.'}), 'model')
    monkeypatch.setattr('app.answer_service.generate', fake_generate)
    answer = asyncio.run(AnswerService(Rag(), settings(tmp_path)).answer(QUESTIONS[-1], state=state))
    assert 'aQsi' not in captured[-1]['content']
    assert all(text in captured[-1]['content'] for text in ('АТОЛ Онлайн', 'изменение прав', 'не менять настройки'))
    assert answer.dialogue_state['entities']['service'][0]['message_id'] == 5


def test_ofd_does_not_confirm_hardware_for_a_fiscal_error(tmp_path, monkeypatch):
    class Rag:
        def search(self, query, top_k): return []
    async def no_generate(*args): raise AssertionError('No generation without hardware')
    monkeypatch.setattr('app.answer_service.generate', no_generate)
    state = DialogueManager().advance(DialogueState(), 'ОФД Такском, ошибка ФН 235', 1)
    assert state.entity('ofd') == 'Такском' and state.routing_service is None
    answer = asyncio.run(AnswerService(Rag(), settings(tmp_path)).answer('ОФД Такском, ошибка ФН 235', state=state))
    assert answer.scenario_reason == 'error_product_missing'


def test_conflicting_same_kind_entities_are_not_resolved_by_alias_order():
    state = DialogueManager().advance(DialogueState(), 'Как изменить права: aQsi Online или АТОЛ Онлайн?', 1)
    assert state.analysis_required and state.entity('service') is None
    with pytest.raises(QueryNeedsClarification):
        build_rag_query(state)


@pytest.mark.parametrize(("text", "service"), [
    ("В Saby не могу найти входящий документ.", "Saby"),
    ("В кабинете СБИС не отображается входящий УПД.", "Saby"),
    ("В Диадоке не вижу отправленный УПД.", "Диадок"),
    ("БИФИТ не работает, нужна помощь.", "БИФИТ"),
    ("БИФИТ Касса не работает, нужна помощь.", "БИФИТ Касса"),
])
def test_registered_explicit_services_survive_lexical_reduction(text, service):
    state = DialogueManager().advance(DialogueState(), text, 1)
    assert state.entity("service") == service
    assert state.routing_slot == "service" and state.routing_service == service
    assert not state.task_entity("manufacturer")
    assert not state.task_entity("software")
    assert not state.task_entity("equipment")


def test_generic_document_does_not_become_receipt_search_object():
    text = "В Saby не могу найти входящий документ."
    state = DialogueManager().advance(DialogueState(), text, 1)
    assert state.operation == "search"
    assert state.intent == "unknown" and state.object is None
    assert state.routing_service == "Saby"


def test_unsupported_snapshot_version_is_preserved(tmp_path):
    store = ConversationStore(tmp_path / 'future.sqlite3')
    cid = store.new(1, 1)
    payload = json.dumps({'schema_version': 999})
    with store.connect() as db:
        db.execute('INSERT INTO dialogue_states VALUES(?,?,0)', (cid, payload))
    with pytest.raises(ValueError, match='Unsupported'):
        store.dialogue_state(cid)
    with store.connect() as db:
        assert db.execute('SELECT state_json FROM dialogue_states').fetchone()[0] == payload


def test_entity_correction_and_temporal_marker_are_parameter_changes():
    manager, state = DialogueManager(), DialogueState()
    for i, text in enumerate(QUESTIONS[:4]):
        state = manager.advance(state, text, i + 1)
    changed = manager.advance(state, 'Теперь использую АТОЛ Онлайн', 5)
    assert changed.transition == 'change_service' and changed.task_id == state.task_id
    assert changed.constraints == state.constraints
    corrected = manager.advance(state, 'Не aQsi Online, а АТОЛ Онлайн', 6)
    assert corrected.entity('service') == 'АТОЛ Онлайн' and not corrected.analysis_required
    assert corrected.task_id == state.task_id


def test_error_code_is_an_independent_parameter_of_the_same_incident():
    manager = DialogueManager()
    state = manager.advance(DialogueState(), 'Эвотор 6, ошибка ФН 234', 1)
    updated = manager.advance(state, 'Теперь ошибка ФН 235', 2)
    assert updated.task_id == state.task_id and updated.transition == 'change_parameter'
    assert updated.entity('equipment') == 'Эвотор 6'
    assert updated.error.value == '235' and '234' not in build_rag_query(updated)


def test_short_model_reply_fills_only_the_expected_equipment_slot():
    manager = DialogueManager()
    state = manager.advance(DialogueState(), 'Эвотор, ошибка ФН 235', 1)
    state = manager.observe_answer(state, scenario='clarify', reason=None,
                                   question='Какая модель Эвотор?', slot='equipment', message_id=2)
    updated = manager.advance(state, '6', 3)
    assert updated.expected is None and updated.transition == 'clarification'
    assert updated.entity('equipment') == 'Эвотор 6'
    fact = updated.entities['equipment'][0]
    assert fact.quote == '6' and fact.message_id == 3
    assert updated.entity('manufacturer') == 'Эвотор' and updated.entity('ofd') is None


def test_general_concept_in_the_same_domain_starts_an_independent_topic():
    manager = DialogueManager()
    state = manager.advance(DialogueState(), QUESTIONS[0], 1)
    explained = manager.advance(state, 'А что такое роль пользователя?', 2)
    assert explained.transition == 'new_task' and explained.operation == 'explain'
    assert explained.entity('service') == 'aQsi Online'
    assert not explained.goals and not explained.constraints
