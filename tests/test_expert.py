from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest

from app.answer_service import Answer, AnswerService
from app.config import Settings
from app.expert_report import export, statistics
from app.expert_report import groq_paid_cost_estimate, token_metrics
from app.expert_store import ExpertStore, load_questions
from app.expert_telegram import ExpertTelegram
from app.llm_client import Generation, GenerationError, generate
from app.rag import SearchResult


def settings(tmp_path: Path, **overrides):
    values = dict(telegram_bot_token="", openrouter_api_key="test", openrouter_model="model",
                  app_name="test", app_url="http://localhost", show_sources=False,
                  docs_dir=tmp_path, expert_telegram_ids=frozenset({42}))
    values.update(overrides)
    return Settings(**values)


def question():
    return dict(id="Q1", category="ОФД", query="Где чек?", expected_topic="ofd",
                expected_behavior="Ответ по источнику", notes="Проверить")


def generated(text="Исходный ответ"):
    return Answer(text=text, raw_text=text,
                  results=[SearchResult("source.md", "Фрагмент", 0.42, 0.81, 2.3,
                                        {"source": "source.md", "status": "approved"})],
                  used_model=True, generation_status="generated", model="openai/gpt-oss-20b",
                  provider="groq", prompt_tokens=10, completion_tokens=5, total_tokens=15,
                  reasoning_tokens=2, cached_tokens=1, api_call_id="call-1",
                  rag_chunks=1, context_chars=42, duration_ms=123)


def test_questions_preserve_old_scenarios_and_have_unique_ids():
    questions = load_questions()
    assert len(questions) == 30
    assert len({q["id"] for q in questions}) == 30
    assert {kind: sum(q["question_type"] == kind for q in questions)
            for kind in ("normal", "technical", "clarification")} == {
                "normal": 15, "technical": 10, "clarification": 5}
    assert all(Path(q["expected_document"]).is_file() for q in questions if q["expected_document"])
    assert questions[6]["question_type"] == "clarification" and questions[6]["expected_document"] is None
    assert questions[29]["question_type"] == "normal" and "aQsi Online" in questions[29]["query"]


def test_resume_double_click_review_and_immutable_answer(tmp_path):
    path = tmp_path / "reviews.sqlite3"
    store = ExpertStore(path)
    sid = store.start(42, [question()])
    assert store.claim(sid, 7, "Q1") is None
    aid = store.claim(sid, 42, "Q1")
    assert aid and store.claim(sid, 42, "Q1") is None
    store.save_answer(aid, generated())
    store.save_answer(aid, generated("Overwritten"))
    assert store.claim(sid, 42, "Q1") is None
    second_attempt = store.claim(sid, 42, "Q1", force=True, provider="groq", model="openai/gpt-oss-20b")
    assert second_attempt and second_attempt != aid
    store.save_answer(second_attempt, generated("Новая версия"))
    assert store.rate(sid, 7, aid, 1) is False
    assert store.rate(sid, 42, aid, 6)
    assert store.reason(sid, 42, aid, "Ответ неполный")
    assert store.rate(sid, 42, aid, 8)
    assert store.request_comment(sid, 42, aid)
    assert store.save_comment(42, "Проверить ссылку")
    reopened = ExpertStore(path)
    assert reopened.active(42)["id"] == sid
    attempt = reopened.latest(sid, "Q1")
    assert attempt["answer_text"] == "Новая версия"
    first_attempt = reopened.rows(42)[0]
    assert first_attempt["answer_text"] == "Исходный ответ"
    assert first_attempt["api_call_id"] == "call-1"
    assert (first_attempt["score"], first_attempt["reason"], first_attempt["comment"]) == (8, "Ответ неполный", "Проверить ссылку")
    assert json.loads(first_attempt["results_json"])[0]["semantic_score"] == 0.81
    row = first_attempt
    assert (row["prompt_tokens"], row["completion_tokens"], row["total_tokens"]) == (10, 5, 15)
    assert (row["reasoning_tokens"], row["cached_tokens"], row["api_call_id"]) == (2, 1, "call-1")
    assert (row["provider"], row["rag_chunks"], row["context_chars"]) == ("groq", 1, 42)
    assert reopened.progress(sid, 42) == (1, 1)
    specialist_id = reopened.rows(42)[0]["specialist_id"]
    assert reopened.rows(42)[0]["telegram_id"] == 42
    assert reopened.start(42, [question()]) != sid
    assert {row["specialist_id"] for row in reopened.rows(42)} == {specialist_id}


def test_two_configured_reviewers_have_separate_sessions_and_scores(tmp_path):
    first, second = 829300186, 1098858360
    store = ExpertStore(tmp_path / "two-reviewers.sqlite3")
    first_sid = store.start(first, [question()])
    second_sid = store.start(second, [question()])
    first_attempt = store.claim(first_sid, first, "Q1")
    second_attempt = store.claim(second_sid, second, "Q1")
    store.save_answer(first_attempt, generated("Ответ первого"))
    store.save_answer(second_attempt, generated("Ответ второго"))
    assert not store.rate(first_sid, second, first_attempt, 1)
    assert store.rate(first_sid, first, first_attempt, 8)
    assert store.rate(second_sid, second, second_attempt, 5)
    assert store.current(first_sid, second) is None
    assert store.current(second_sid, first) is None
    assert [(r["telegram_id"], r["answer_text"], r["score"]) for r in store.rows()] == [
        (first, "Ответ первого", 8), (second, "Ответ второго", 5)]


def test_errors_unavailable_and_export_are_separate_from_ratings(tmp_path):
    store = ExpertStore(tmp_path / "reviews.sqlite3")
    sid = store.start(42, [question()])
    aid = store.claim(sid, 42, "Q1")
    store.save_error(aid)
    assert not store.rate(sid, 42, aid, 1)
    assert store.latest(sid, "Q1")["total_tokens"] is None
    retry = store.claim(sid, 42, "Q1")
    assert retry != aid
    store.save_answer(retry, Answer("fallback", generation_status="unavailable"))
    assert not store.rate(sid, 42, retry, 1)
    third = store.claim(sid, 42, "Q1")
    store.save_answer(third, generated())
    assert store.rate(sid, 42, third, 5)
    csv_path, sessions_csv, json_path = export(store, tmp_path / "exports")
    assert "Исходный ответ" in csv_path.read_text(encoding="utf-8-sig")
    assert "llm_calls" in sessions_csv.read_text(encoding="utf-8-sig")
    exported = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(exported["questions"]) == 3
    assert exported["questions"][-1]["results"][0]["text"] == "Фрагмент"
    assert exported["questions"][-1]["total_tokens"] == 15
    assert exported["sessions"][0]["total_tokens_total"] == 15
    stats = statistics(store.rows())
    assert stats["reviewed_questions"] == 1 and stats["below_7"] == 1
    assert stats["technical_errors"] == 1 and stats["generation_unavailable"] == 1


def test_pending_request_is_recoverable_after_restart(tmp_path):
    path = tmp_path / "reviews.sqlite3"
    store = ExpertStore(path)
    sid = store.start(42, [question()])
    pending = store.claim(sid, 42, "Q1")
    restarted = ExpertStore(path)
    assert restarted.recover_pending() == 1
    assert restarted.latest(sid, "Q1")["generation_status"] == "error"
    assert restarted.claim(sid, 42, "Q1") != pending


def test_additive_migration_preserves_existing_answers_and_reviews(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE sessions(id TEXT PRIMARY KEY, expert_id INTEGER NOT NULL, started_at TEXT NOT NULL,
                finished_at TEXT, position INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE items(session_id TEXT NOT NULL, ordinal INTEGER NOT NULL, question_id TEXT NOT NULL,
                category TEXT NOT NULL, query TEXT NOT NULL, expected_topic TEXT,
                expected_behavior TEXT NOT NULL, notes TEXT NOT NULL,
                PRIMARY KEY(session_id, question_id), UNIQUE(session_id, ordinal));
            CREATE TABLE attempts(id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, question_id TEXT NOT NULL,
                attempt_no INTEGER NOT NULL, created_at TEXT NOT NULL, completed_at TEXT,
                generation_status TEXT NOT NULL, answer_text TEXT, results_json TEXT NOT NULL,
                model TEXT, provider TEXT, duration_ms INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER);
            CREATE TABLE reviews(attempt_id INTEGER PRIMARY KEY, score INTEGER NOT NULL,
                reason TEXT, comment TEXT, updated_at TEXT NOT NULL);
            INSERT INTO sessions VALUES('legacy', 42, '2026-10-01T00:00:00+00:00', NULL, 0);
            INSERT INTO items VALUES('legacy', 0, 'Q1', 'ОФД', 'Где чек?', 'ofd', 'Ответить', 'Заметка');
            INSERT INTO attempts VALUES(7, 'legacy', 'Q1', 1, '2026-10-01T00:00:00+00:00',
                '2026-10-01T00:00:01+00:00', 'generated', 'Сохранённый ответ', '[]', 'model',
                'groq', 1000, 12, 4);
            INSERT INTO reviews VALUES(7, 8, 'Всё корректно', 'Комментарий оставить', '2026-10-01T00:00:02+00:00');
        """)
    store = ExpertStore(path)
    row = store.rows(42)[0]
    assert row["answer_text"] == "Сохранённый ответ"
    assert (row["score"], row["reason"], row["comment"]) == (8, "Всё корректно", "Комментарий оставить")
    assert row["prompt_tokens"] == 12 and row["completion_tokens"] == 4
    assert row["total_tokens"] is None and row["specialist_id"]


def test_answer_service_isolated_and_generation_failure(monkeypatch, tmp_path):
    class Rag:
        def search(self, query, top_k):
            return [SearchResult("source.md", query, 0.5)]
        def build_context(self, results):
            return results[0].text

    prompts = []
    async def fake_generate(messages, config):
        prompts.append(messages)
        if "ошибка" in messages[-1]["content"]:
            raise GenerationError("secret provider response")
        return Generation("Ответ", "model", 7, 3)

    monkeypatch.setattr("app.answer_service.generate", fake_generate)
    service = AnswerService(Rag(), settings(tmp_path))
    first = asyncio.run(service.answer("первый", history=None))
    second = asyncio.run(service.answer("второй", history=None))
    assert first.generation_status == second.generation_status == "generated"
    assert first.rag_chunks == 1 and first.context_chars > 0
    assert len(prompts[0]) == len(prompts[1]) == 2
    assert "первый" not in str(prompts[1])
    failed = asyncio.run(service.answer("ошибка", history=None))
    assert failed.generation_status == "error" and not failed.used_model
    assert "secret provider response" not in failed.text
    unavailable = asyncio.run(AnswerService(Rag(), settings(tmp_path, openrouter_api_key="")).answer("вопрос"))
    assert unavailable.generation_status == "unavailable"
    assert unavailable.total_tokens is None and unavailable.prompt_tokens is None
    class EmptyRag(Rag):
        def search(self, query, top_k):
            return []
    no_context = asyncio.run(AnswerService(EmptyRag(), settings(tmp_path)).answer("вопрос"))
    assert no_context.generation_status == "no_context" and not no_context.used_model
    assert "подтверждённого решения" in no_context.text
    assert no_context.text.count("?") == 1


def test_client_answer_is_short_and_keeps_rag_details_separate(monkeypatch, tmp_path):
    fragment = "СЕКРЕТНЫЙ RAG-ФРАГМЕНТ С ТЕХНИЧЕСКИМИ ШАГАМИ"
    result = SearchResult("ofd/guide.md", fragment, 0.91, 0.82, 3.1,
                          {"source": "ofd/guide.md", "status": "draft",
                           "source_url": "https://example.test/guide"})

    class Rag:
        def search(self, query, top_k):
            assert top_k == 5
            return [result]
        def build_context(self, results):
            return results[0].text

    async def fake_generate(messages, config):
        assert "300–500" in messages[0]["content"]
        assert "СЕКРЕТНЫЙ RAG-ФРАГМЕНТ" in messages[-1]["content"]
        return Generation("Проверьте подключение кассы к интернету. Если ошибка останется, пришлите её текст.",
                          "openai/gpt-oss-20b", 40, 19, 59, finish_reason="stop")

    monkeypatch.setattr("app.answer_service.generate", fake_generate)
    answer = asyncio.run(AnswerService(Rag(), settings(tmp_path)).answer("Вопрос клиента"))
    assert answer.text == answer.raw_text
    assert "СЕКРЕТНЫЙ RAG-ФРАГМЕНТ" not in answer.text
    assert "semantic" not in answer.text and "score" not in answer.text
    assert answer.results[0].text == fragment

    store = ExpertStore(tmp_path / "answers.sqlite3")
    sid = store.start(42, [question()])
    attempt = store.claim(sid, 42, "Q1")
    store.save_answer(attempt, answer)
    row = store.rows(42)[0]
    assert row["answer_text"] == answer.text
    assert json.loads(row["results_json"])[0]["text"] == fragment
    assert row["prompt_tokens"] == 40 and row["total_tokens"] == 59


def test_expert_sources_button_opens_saved_rag_details_separately(tmp_path):
    store = ExpertStore(tmp_path / "sources.sqlite3")
    sid = store.start(42, [question()])
    attempt = store.claim(sid, 42, "Q1")
    store.save_answer(attempt, Answer(
        text="Проверьте соединение кассы с интернетом.", raw_text="Проверьте соединение кассы с интернетом.",
        generation_status="generated", model="openai/gpt-oss-20b", provider="groq",
        prompt_tokens=10, completion_tokens=5, total_tokens=15, duration_ms=1200,
        rag_chunks=1, context_chars=80,
        results=[SearchResult("ofd/guide.md", "Сохранённый RAG-фрагмент", 0.91, 0.82, 3.1,
                              {"source": "ofd/guide.md", "status": "draft",
                               "source_url": "https://example.test/guide"})]))
    sent = []

    class Message:
        async def reply_text(self, text, reply_markup=None):
            sent.append((text, reply_markup))

    class Query:
        data = f"ex:sources:{sid}:Q1"
        async def answer(self, *args, **kwargs):
            pass

    update = SimpleNamespace(effective_user=SimpleNamespace(id=42), effective_message=Message(),
                             message=Message(), callback_query=Query())
    telegram = ExpertTelegram(settings(tmp_path), None, store)
    asyncio.run(telegram.show_answer(update, sid, "Q1"))
    answer_text, markup = sent[0]
    assert answer_text == "Проверьте соединение кассы с интернетом."
    assert "Сохранённый RAG-фрагмент" not in answer_text
    assert "score" not in answer_text and "semantic" not in answer_text
    labels = {button.text for row in markup.inline_keyboard for button in row}
    assert "Источники RAG" in labels
    assert len(sent) == 1

    asyncio.run(telegram.callback(update, None))
    sources_text = sent[1][0]
    assert "Источники RAG" in sources_text
    assert "Сохранённый RAG-фрагмент" in sources_text
    assert "https://example.test/guide" in sources_text
    assert "Оценка поиска: 0.91" in sources_text


def test_simple_question_rating_and_next_flow(tmp_path):
    store = ExpertStore(tmp_path / "flow.sqlite3")
    sid = store.start(42, [question(), {**question(), "id": "Q2", "query": "Следующий вопрос?"}])
    sent = []

    class Message:
        async def reply_text(self, text, reply_markup=None):
            sent.append((text, reply_markup))

    class Query:
        data = ""
        async def answer(self, *args, **kwargs): pass

    update = SimpleNamespace(effective_user=SimpleNamespace(id=42), effective_message=Message(),
                             message=Message(), callback_query=Query())
    telegram = ExpertTelegram(settings(tmp_path), None, store)
    asyncio.run(telegram.question(update, sid))
    text, markup = sent[-1]
    assert "Вопрос 1/30" in text and "Где чек?" in text
    assert "Ожидаемое поведение" not in text and "Заметка" not in text
    assert [b.text for row in markup.inline_keyboard for b in row] == ["Получить ответ"]

    attempt_id = store.claim(sid, 42, "Q1")
    store.save_answer(attempt_id, generated("Короткий ответ клиенту"))
    update.callback_query.data = f"ex:rate:{sid}:{attempt_id}:9"
    asyncio.run(telegram.callback(update, None))
    assert store.latest(sid, "Q1")["score"] == 9
    assert sent[-1][0] == "Оценка 9/10 сохранена."
    assert [b.text for row in sent[-1][1].inline_keyboard for b in row] == ["Следующий вопрос"]

    update.callback_query.data = f"ex:next:{sid}"
    asyncio.run(telegram.callback(update, None))
    assert store.current(sid, 42)["query"] == "Следующий вопрос?"
    assert "Вопрос 2/30" in sent[-1][0]


def test_start_offers_resume_for_an_existing_session(tmp_path):
    store = ExpertStore(tmp_path / "resume-menu.sqlite3")
    sid = store.start(42, [question()])
    sent = []

    class Message:
        async def reply_text(self, text, reply_markup=None):
            sent.append((text, reply_markup))

    update = SimpleNamespace(effective_user=SimpleNamespace(id=42), effective_message=Message(),
                             message=Message())
    telegram = ExpertTelegram(settings(tmp_path), None, store)
    asyncio.run(telegram.command(update, None))
    assert "незавершённое тестирование" in sent[0][0]
    assert [b.text for row in sent[0][1].inline_keyboard for b in row] == [
        "Продолжить тестирование", "Начать новую сессию"]


def test_ambiguous_account_action_asks_before_rag_or_llm(tmp_path, monkeypatch):
    class Rag:
        def search(self, query, top_k):
            raise AssertionError("RAG results must not guess the client's service")

    async def fake_generate(*args, **kwargs):
        raise AssertionError("An ambiguous question must not call the LLM")

    monkeypatch.setattr("app.answer_service.generate", fake_generate)
    service = AnswerService(Rag(), settings(tmp_path))
    answer = asyncio.run(service.answer("Как добавить ещё одного сотрудника в личный кабинет?"))
    assert answer.generation_status == "clarification"
    assert answer.text == "В каком сервисе нужно выполнить это действие?"
    assert answer.results == [] and answer.prompt_tokens is None and answer.total_tokens is None
    assert answer.used_model is False and answer.model is None and answer.provider is None


@pytest.mark.parametrize("service_name", ["aQsi Online", "АТОЛ Онлайн", "Эвотор", "1С"])
def test_explicit_service_is_in_search_and_generation_context(tmp_path, monkeypatch, service_name):
    source_prefix = {"aQsi Online": "aqsi_online", "АТОЛ Онлайн": "atol_online",
                     "Эвотор": "evotor", "1С": "1c"}[service_name]
    result = SearchResult(f"{source_prefix}/users.md", "Подтверждённая инструкция.", 0.8)

    class Rag:
        query = None
        def search(self, query, top_k):
            self.query = query
            return [result]
        def build_context(self, results):
            return results[0].text

    rag = Rag()
    captured = []
    async def fake_generate(messages, config):
        captured.extend(messages)
        return Generation("Уточнённый ответ.", "model", 11, 7, 18)

    monkeypatch.setattr("app.answer_service.generate", fake_generate)
    answer = asyncio.run(AnswerService(rag, settings(tmp_path)).answer(
        f"Как добавить сотрудника в {service_name}?"))
    assert answer.generation_status == "generated"
    assert service_name.casefold() in rag.query.casefold()
    assert service_name.casefold() in captured[0]["content"].casefold()
    prompt = captured[0]["content"].casefold()
    assert "клиент явно назвал" in prompt
    assert "документы rag — справочные материалы" in prompt


def test_only_client_history_confirms_service_and_is_used_in_search(tmp_path, monkeypatch):
    result = SearchResult("aqsi_online/account/add-user.md", "Раздел «Пользователи» создаёт учётную запись.", 0.8)

    class Rag:
        query = None
        def search(self, query, top_k):
            self.query = query
            return [result]
        def build_context(self, results): return results[0].text

    rag = Rag()
    captured = []
    async def fake_generate(messages, config):
        captured.extend(messages)
        return Generation("В aQsi Online в разделе «Пользователи» создаётся учётная запись.", "model", 12, 9, 21)
    monkeypatch.setattr("app.answer_service.generate", fake_generate)
    service = AnswerService(rag, settings(tmp_path))

    resolved = asyncio.run(service.answer("Как добавить сотрудника?", history=[
        {"role": "user", "content": "Мы работаем в aQsi Online."},
        {"role": "assistant", "content": "Для aQsi Online откройте выдуманный раздел."},
    ]))
    assert resolved.generation_status == "generated"
    assert "aQsi Online" in rag.query and "Мы работаем в aQsi Online" in captured[1]["content"]

    clarified_after_question = asyncio.run(service.answer("aQsi Online", history=[
        {"role": "user", "content": "Как добавить ещё одного сотрудника в личный кабинет?"},
    ]))
    assert clarified_after_question.generation_status == "generated"
    assert "добавить ещё одного сотрудника" in rag.query.casefold()
    assert "Сервис, названный клиентом: aQsi Online" in rag.query

    clarification = asyncio.run(service.answer("Как добавить сотрудника?", history=[
        {"role": "assistant", "content": "Похоже, это aQsi Online."},
    ]))
    assert clarification.generation_status == "clarification"


def test_generic_question_answers_immediately_and_unverified_ui_steps_are_removed(tmp_path, monkeypatch):
    result = SearchResult("ofd/overview.md", "ОФД принимает и передаёт фискальные документы.", 0.8)

    class Rag:
        def search(self, query, top_k): return [result]
        def build_context(self, results): return results[0].text

    async def fake_generate(messages, config):
        assert "Не определяй продукт клиента" in messages[0]["content"]
        return Generation("ОФД принимает фискальные документы. Откройте раздел «Управление пользователями» и нажмите кнопку «Добавить».",
                          "model", 20, 15, 35)

    monkeypatch.setattr("app.answer_service.generate", fake_generate)
    answer = asyncio.run(AnswerService(Rag(), settings(tmp_path)).answer("Что такое ОФД?"))
    assert answer.generation_status == "generated"
    assert answer.text == "В найденной инструкции нет подтверждённых точных шагов. Какой раздел или сообщение вы видите в сервисе?"
    assert answer.prompt_tokens == 20 and answer.total_tokens == 35


def test_clarification_answer_can_be_rated_without_counting_llm_usage(tmp_path):
    store = ExpertStore(tmp_path / "clarification.sqlite3")
    sid = store.start(42, [question()])
    attempt = store.claim(sid, 42, "Q1")
    store.save_answer(attempt, Answer("В каком сервисе?", generation_status="clarification"))
    assert store.rate(sid, 42, attempt, 10)
    rows = store.rows(42)
    assert rows[0]["score"] == 10 and rows[0]["total_tokens"] is None
    report = token_metrics(rows)
    assert report["llm_calls"] == 0 and report["total_tokens_total"] is None
    assert statistics(rows)["reviewed_questions"] == 1


def test_truncated_generation_is_not_shown_as_a_complete_answer(monkeypatch, tmp_path):
    class Rag:
        def search(self, query, top_k):
            return [SearchResult("source.md", "подтверждённый контекст", 0.7)]
        def build_context(self, results):
            return results[0].text

    async def fake_generate(messages, config):
        return Generation("Обрезанный фрагмент ответа", "openai/gpt-oss-20b",
                          80, 2048, 2128, 1000, None, "call-truncated", "length")

    monkeypatch.setattr("app.answer_service.generate", fake_generate)
    answer = asyncio.run(AnswerService(Rag(), settings(tmp_path)).answer("вопрос"))
    assert answer.generation_status == "truncated"
    assert "Обрезанный фрагмент" not in answer.text
    assert "ограничения длины" in answer.text
    assert (answer.prompt_tokens, answer.completion_tokens, answer.total_tokens) == (80, 2048, 2128)


def test_expert_access_and_isolated_telegram_questions(tmp_path):
    store = ExpertStore(tmp_path / "reviews.sqlite3")
    sid = store.start(42, [question(), {**question(), "id": "Q2", "query": "Второй вопрос"}])
    calls = []
    class Service:
        async def answer(self, query, history=None):
            calls.append((query, history))
            return generated(query)
    sent = []
    class Message:
        async def reply_text(self, text, reply_markup=None):
            sent.append(text)
    def update(user_id):
        return SimpleNamespace(effective_user=SimpleNamespace(id=user_id),
                               effective_message=Message(), message=Message())
    telegram = ExpertTelegram(settings(tmp_path), Service(), store)
    assert telegram.allowed(update(42)) and not telegram.allowed(update(7))
    asyncio.run(telegram.command(update(7), None))
    assert sent[-1] == "Тестирование доступно только приглашённым экспертам."
    alerts = []
    class Query:
        data = f"ex:answer:{sid}:Q1"
        async def answer(self, text=None, show_alert=False):
            alerts.append((text, show_alert))
    intruder = update(7)
    intruder.callback_query = Query()
    asyncio.run(telegram.callback(intruder, None))
    assert alerts == [("Доступ запрещён", True)]
    assert store.latest(sid, "Q1") is None
    asyncio.run(telegram.answer(update(42), sid, "Q1"))
    store.move(sid, 42, 1)
    asyncio.run(telegram.answer(update(42), sid, "Q2"))
    assert calls == [("Где чек?", None), ("Второй вопрос", None)]
    assert store.latest(sid, "Q1")["answer_text"] == "Где чек?"
    assert store.latest(sid, "Q2")["answer_text"] == "Второй вопрос"


def test_groq_provider_uses_shared_generation_interface(monkeypatch, tmp_path):
    calls = []
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"message": {"content": "Ответ Groq"}, "finish_reason": "length"}],
                    "id": "chatcmpl-test", "model": "actual-model", "usage": {
                        "prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18,
                        "completion_tokens_details": {"reasoning_tokens": 2},
                        "prompt_tokens_details": {"cached_tokens": 3}}}
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, headers, json):
            calls.append((url, headers, json))
            return Response()
    monkeypatch.setattr("app.llm_client.httpx.AsyncClient", Client)
    result = asyncio.run(generate([{"role": "user", "content": "Вопрос"}],
                                  settings(tmp_path, llm_provider="groq", groq_api_key="test-groq")))
    assert calls[0][0].startswith("https://api.groq.com/")
    assert calls[0][2]["model"] == "openai/gpt-oss-20b"
    assert calls[0][2]["max_completion_tokens"] == 2048
    assert calls[0][2]["reasoning_effort"] == "low"
    assert result.text == "Ответ Groq" and result.prompt_tokens == 11
    assert (result.completion_tokens, result.total_tokens) == (7, 18)
    assert (result.reasoning_tokens, result.cached_tokens) == (2, 3)
    assert result.api_call_id == "chatcmpl-test"
    assert result.finish_reason == "length"


def test_usage_fields_missing_from_provider_remain_null(monkeypatch, tmp_path):
    class Response:
        payload = {"choices": [{"message": {"content": "Ответ"}}], "usage": {"prompt_tokens": 12}}
        def raise_for_status(self):
            pass
        def json(self):
            return self.payload
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.llm_client.httpx.AsyncClient", Client)
    result = asyncio.run(generate([], settings(tmp_path, llm_provider="groq", groq_api_key="key")))
    assert result.prompt_tokens == 12
    assert result.completion_tokens is None and result.total_tokens is None
    assert result.reasoning_tokens is None and result.cached_tokens is None
    assert result.api_call_id is None
    Response.payload = {"choices": [{"message": {"content": "Ответ"}}]}
    absent = asyncio.run(generate([], settings(tmp_path, llm_provider="groq", groq_api_key="key")))
    assert absent.prompt_tokens is None and absent.completion_tokens is None
    assert absent.total_tokens is None and absent.reasoning_tokens is None and absent.cached_tokens is None


def test_openrouter_remains_compatible_and_returns_usage(monkeypatch, tmp_path):
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"id": "or-call", "model": "router-model",
                    "choices": [{"message": {"content": "Ответ OR"}}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28,
                              "completion_tokens_details": {"reasoning_tokens": 4},
                              "prompt_tokens_details": {"cached_tokens": 6}}}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, headers, json):
            calls.append((url, headers, json))
            return Response()
    monkeypatch.setattr("app.llm_client.httpx.AsyncClient", Client)
    result = asyncio.run(generate([], settings(tmp_path, llm_provider="openrouter",
                                               openrouter_api_key="or-key")))
    assert calls[0][0] == "https://openrouter.ai/api/v1/chat/completions"
    assert calls[0][1]["Authorization"] == "Bearer or-key"
    assert result.api_call_id == "or-call"
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (20, 8, 28)
    assert (result.reasoning_tokens, result.cached_tokens) == (4, 6)


def test_token_reports_and_paid_groq_estimates(tmp_path):
    store = ExpertStore(tmp_path / "tokens.sqlite3")
    sid = store.start(42, [question()])
    aid = store.claim(sid, 42, "Q1")
    answer = generated()
    store.save_answer(aid, answer)
    store.rate(sid, 42, aid, 9)
    row = store.rows(42)[0]
    report = token_metrics([row])
    assert report["llm_calls"] == 1 and report["calls_with_usage"] == 1
    assert report["prompt_tokens_total"] == 10
    assert report["completion_tokens_total"] == 5 and report["total_tokens_total"] == 15
    assert report["reasoning_tokens_total"] == 2 and report["cached_tokens_total"] == 1
    assert report["projection_100_calls_per_day"]["total_tokens_per_100_calls"] == 1500
    # (9 uncached input * $0.075 + 1 cached input * $0.037 + 5 output * $0.30) / 1M
    assert groq_paid_cost_estimate(row) == 0.00000221

    no_usage = {**row, "prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    empty = token_metrics([no_usage])
    assert empty["llm_calls"] == 1 and empty["calls_with_usage"] == 0
    assert empty["total_tokens_total"] is None


def test_session_comparison_reports_question_change(tmp_path):
    store = ExpertStore(tmp_path / "reviews.sqlite3")
    for score in (5, 8):
        sid = store.start(42, [question()])
        aid = store.claim(sid, 42, "Q1")
        store.save_answer(aid, generated())
        store.rate(sid, 42, aid, score)
    comparison = statistics(store.rows())["session_comparisons"][0]
    assert comparison["same_questions"][0]["change"] == 3
    assert comparison["average_score_change"] == 3
