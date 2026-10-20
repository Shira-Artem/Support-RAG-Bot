import asyncio
import importlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.answer_service import Answer, AnswerService, _active_request, _validation_issue
from app.conversation_store import ConversationStore
from app.expert_store import ExpertStore
from app.llm_client import Generation
from app.rag import SearchResult
from test_expert import settings


def test_aqsi_employee_permissions_chain_persists_task_and_rejects_invented_role(monkeypatch, tmp_path):
    path = tmp_path / 'chain.sqlite3'
    store = ConversationStore(path)
    cid = store.new(42, 42)
    guide = SearchResult('aqsi_online/account/add-user.md',
        'В разделе «Пользователи» администратор создаёт учётную запись, указывает имя и email '
        'и присваивает заранее созданную роль. Изменение пользователя выполняется через меню этой записи.',
        .9, metadata={'category': 'account', 'title': 'Добавление сотрудника'})
    unrelated = [SearchResult('accounting/usn/guide.md', 'Права на УСН и налоговая инспекция.', 1),
                 SearchResult('atol_online/account/users.md', 'Сотрудники и роли АТОЛ Онлайн.', 1),
                 SearchResult('aqsi_online/taxes/guide.md', 'Права сотрудника на налоговые вычеты.', 1,
                              metadata={'category': 'taxes'})]
    class Rag:
        results = [*unrelated, guide]
        searches = []
        def search_for_service(self, query, service, top_k):
            self.searches.append((query, service))
            return self.results
        def build_context(self, results): return '\n'.join(r.text for r in results)
    rag = Rag()
    prompts = []
    fake_answers = [
        ('answer', 'В разделе «Пользователи» администратор создаёт учётную запись и присваивает заранее созданную роль.'),
        ('clarify', 'Какие задачи будет выполнять сотрудник?'),
        ('answer', 'Назначьте роль «Бухгалтер»: она разрешает просмотр чеков, но не позволяет менять настройки касс.'),
        ('answer', 'В aQsi Online изменение пользователя выполняется через меню его записи в разделе «Пользователи». '
                   'Порядок изменения отдельных прав в документации не указан. Уточните его у администратора сервиса.'),
    ]
    async def generate(messages, config):
        prompts.append(messages[-1]['content'])
        scenario, response = fake_answers[len(prompts) - 1]
        return Generation(json.dumps(dict(scenario=scenario, response=response)), 'model')
    monkeypatch.setattr('app.answer_service.generate', generate)
    service = AnswerService(rag, settings(tmp_path))
    questions = ['Как добавить сотрудника в личный кабинет?', 'aQsi Online',
                 'А какую роль ему назначить',
                 'Он будет бухгалтером, ему нужен просмотр без изменения настроек касс',
                 'А где эти права можно изменить?']
    answers = []
    for index, query in enumerate(questions):
        # Reopen SQLite each turn, including old incorrectly saved boundaries.
        store = ConversationStore(path)
        if index == 4:
            # An answer from before the fix must not become evidence for roles.
            with store.connect() as db:
                db.execute('UPDATE messages SET content=? WHERE id=?', (fake_answers[2][1], pending))
        pending = store.begin(cid, query, index not in {2, 4})
        answer = asyncio.run(service.answer(query, state=store.dialogue_state(cid)))
        store.complete(pending, answer)
        answers.append(answer)
    assert answers[0].scenario == 'clarify'
    assert all(name == 'aQsi Online' and 'сотрудник' in query for query, name in rag.searches)
    assert 'просмотр' in rag.searches[-1][0] and 'изменение прав' in rag.searches[-1][0]
    assert all('УСН' not in prompt and 'АТОЛ Онлайн' not in prompt and 'вычеты' not in prompt for prompt in prompts)
    assert 'просмотр' in prompts[2] and 'изменение прав' in prompts[-1]
    assert fake_answers[2][1] not in prompts[-1]
    assert answers[3].validation_reason == 'unsupported_role_or_permissions'
    assert 'роль «Бухгалтер»' not in answers[3].text and 'aQsi Online' in answers[3].text
    assert answers[4].scenario == 'answer' and 'не указан' in answers[4].text
    with store.connect() as db:
        diagnostic = json.loads(db.execute("SELECT diagnostics_json FROM messages WHERE id=?", (pending,)).fetchone()[0])
    assert diagnostic['rag_query'] == rag.searches[-1][0]
    assert diagnostic['confirmed_service'] == 'aQsi Online'
    assert [r['source'] for r in diagnostic['results']] == [guide.source]
    history = store.history(cid)
    assert history[0]['content'] == questions[0]  # repairs old flags without deleting data
    for followup in ['где эти права', 'а как это сделать', 'не помогло']:
        request, _, continuing = _active_request(followup, history)
        assert continuing and 'aQsi Online' in request and 'сотрудник' in request
    assert _active_request('Что такое маркировка?', history)[2] is False
    rag.results = unrelated
    missing = asyncio.run(service.answer(questions[-1], history))
    assert missing.scenario == 'escalate' and missing.results == []
    assert 'прав сотрудника' in missing.text and 'aQsi Online' in missing.text
    assert missing.rag_query == rag.searches[-1][0] and len(prompts) == 4


def test_durable_history_new_dialog_and_diagnostics(tmp_path):
    path = tmp_path / 'chat.sqlite3'
    store = ConversationStore(path)
    first = store.new(1, 1)
    pending = store.begin(first, 'Как добавить сотрудника?', False)
    answer = Answer('Текст' * 1000, scenario='clarify', model='openai/gpt-oss-20b', provider='groq',
                    prompt_tokens=12, raw_model_text='raw', validation_reason='reason',
                    results=[SearchResult('source', 'evidence', .5)])
    store.complete(pending, answer)
    restarted = ConversationStore(path)
    assert restarted.state(1, 1)['conversation_id'] == first
    assert restarted.history(first)[-1]['content'] == answer.text
    with store.connect() as db:
        diagnostic = json.loads(db.execute('SELECT diagnostics_json FROM messages WHERE id=?', (pending,)).fetchone()[0])
    assert diagnostic['prompt_tokens'] == 12 and diagnostic['results'][0]['text'] == 'evidence'
    assert diagnostic['model'] == answer.model and diagnostic['validation_reason'] == 'reason'
    second = restarted.new(1, 1)
    assert first != second and restarted.history(second) == [] and len(restarted.history(first)) == 2
    assert restarted.state(2, 1)['conversation_id'] is None
    pending = restarted.begin(second, 'вопрос', False)
    ConversationStore(path).recover_pending()
    with store.connect() as db:
        row = db.execute('SELECT * FROM messages WHERE id=?', (pending,)).fetchone()
    assert json.loads(row['diagnostics_json'])['generation_reason'] == 'process_interrupted'


def test_clarification_and_followup_keep_bot_questions_but_topic_switch_does_not(monkeypatch, tmp_path):
    history = [dict(role='user', content='Как добавить сотрудника?', clarification_reply=False),
               dict(role='assistant', content='В каком сервисе вы используете личный кабинет?', scenario='clarify')]
    captured = []
    class Rag:
        def search(self, query, top_k):
            captured.append(query)
            return [SearchResult('aqsi_online/account/add-user.md', 'В разделе «Пользователи» создаётся учётная запись.', .9)]
        def build_context(self, results): return '\n'.join(r.text for r in results)
    async def generate(messages, config):
        captured.append(messages[-1]['content'])
        return Generation(json.dumps(dict(scenario='answer', response='В разделе «Пользователи» создаётся учётная запись.')), 'model')
    monkeypatch.setattr('app.answer_service.generate', generate)
    result = asyncio.run(AnswerService(Rag(), settings(tmp_path)).answer('В aQsi Online', history))
    assert result.scenario == 'answer'
    assert 'добавление сотрудника' in captured[0]
    assert 'добавление сотрудника' in captured[1]
    history += [dict(role='user', content='В aQsi Online', clarification_reply=True),
                dict(role='assistant', content=result.text, scenario='answer')]
    assert _active_request('Не получилось', history)[2]
    assert _active_request('Эвотор ФН 235', history) == ('Эвотор ФН 235', [], False)
    assert _active_request('Что такое маркировка?', history) == ('Что такое маркировка?', [], False)


@pytest.mark.parametrize('code,bad', [('235', 'Это проблема с фискальной подписью.'),
                                     ('234', 'Причина — недоступен ФН-сервер.')])
def test_wrong_code_diagnoses_are_rejected(monkeypatch, tmp_path, code, bad):
    class Rag:
        def search(self, query, top_k):
            return [SearchResult(f'evotor/fn/fn-{code}.md', 'Эвотор: проверьте дату и время.', .9,
                                 metadata={'title': f'Эвотор: ошибка ФН {code}'})]
        def build_context(self, results): return '\n'.join(r.text for r in results)
    async def generate(*args): return Generation(json.dumps(dict(scenario='answer', response=bad)), 'model')
    monkeypatch.setattr('app.answer_service.generate', generate)
    answer = asyncio.run(AnswerService(Rag(), settings(tmp_path)).answer(f'Эвотор ФН {code}'))
    assert answer.scenario == 'escalate' and answer.generation_status == 'rejected'
    assert bad not in answer.text and answer.validation_reason == 'unsupported_technical_claim'
    assert bad in answer.raw_model_text or '\\u' in answer.raw_model_text


def test_wrong_error_document_abstains_without_model(monkeypatch, tmp_path):
    class Rag:
        def search(self, query, top_k): return [SearchResult('evotor/fn/fn-234.md', 'Эвотор: ошибка ФН 234.', .9)]
    async def unexpected(*args): raise AssertionError('No call without matching code documentation')
    monkeypatch.setattr('app.answer_service.generate', unexpected)
    answer = asyncio.run(AnswerService(Rag(), settings(tmp_path)).answer('Эвотор ФН 235'))
    assert answer.scenario == 'escalate' and answer.generation_reason == 'exact_error_document_missing'


def test_danger_takes_priority_over_ui_and_known_service_is_not_asked_again():
    issue = _validation_issue('Откройте раздел «Неизвестный». Закройте архив ФН.', '')
    assert issue.startswith('unsupported_dangerous_operation:')
    assert _validation_issue('Нажмите «Выполнить».', '', 'Как закрыть архив ФН?').startswith('unsupported_dangerous_operation:')
    assert _validation_issue('Какой сервис вы используете?', '', 'В aQsi Online', 'aQsi Online') == 'repeated_service_clarification'


def test_telegram_modes_are_isolated_and_clear_starts_new_dialog(monkeypatch, tmp_path):
    store = ConversationStore(tmp_path / 'free.sqlite3')
    expert_store = ExpertStore(tmp_path / 'expert.sqlite3')
    monkeypatch.setattr('app.compat.build_answer_rag', lambda _: SimpleNamespace())
    monkeypatch.setattr('app.expert_store.ExpertStore', lambda: expert_store)
    monkeypatch.setattr('app.conversation_store.ConversationStore', lambda: store)
    sys.modules.pop('bot', None)
    bot = importlib.import_module('bot')
    reply = AsyncMock()
    message = SimpleNamespace(text='', reply_text=reply, chat=SimpleNamespace(send_action=AsyncMock()))
    update = SimpleNamespace(message=message, effective_message=message,
                             effective_user=SimpleNamespace(id=42), effective_chat=SimpleNamespace(id=42))
    monkeypatch.setattr(bot.expert, 'allowed', lambda _: True)
    monkeypatch.setattr(bot.expert, 'command', AsyncMock())
    monkeypatch.setattr(bot.answer_service, 'answer', AsyncMock(return_value=Answer('Свободный ответ')))
    async def run():
        await bot.start(update, None)
        for text in ['Свободный диалог', 'Вопрос', 'Экспертное тестирование', 'Текст эксперта']:
            message.text = text
            await bot.handle_message(update, None)
        assert bot.answer_service.answer.await_count == 1
        old = store.state(42, 42)['conversation_id']
        assert [m['content'] for m in store.history(old)] == ['Вопрос', 'Свободный ответ']
        await bot.clear(update, None)
        assert store.state(42, 42)['conversation_id'] != old
        assert len(store.history(old)) == 2
        assert store.state(42, 42)['mode'] == 'free'
    asyncio.run(run())
    sys.modules.pop('bot', None)
