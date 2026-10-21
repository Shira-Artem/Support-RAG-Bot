"""Persistence and Telegram navigation: temp databases, no network or LLM."""
import asyncio
from types import SimpleNamespace

from app.answer_service import Answer
from app.expert_store import ExpertStore
from app.expert_telegram import ExpertTelegram
from app.expert_report import export, statistics
import json


def questions():
    return [dict(id=f"Q{i}", category="ККТ", query=f"Вопрос {i}", expected_topic=None,
                 expected_behavior="Подтверждённый ответ", notes="") for i in range(1, 4)]


def harness(tmp_path):
    store = ExpertStore(tmp_path / "human.sqlite3")
    sid = store.start(42, questions())
    messages = []

    class Message:
        text = "Исправьте этот шаг"
        async def reply_text(self, text, reply_markup=None):
            messages.append((text, reply_markup))

    class Query:
        data = ""
        async def answer(self, *args, **kwargs):
            pass

    update = SimpleNamespace(effective_user=SimpleNamespace(id=42), effective_message=Message(),
                             message=Message(), callback_query=Query())
    ui = ExpertTelegram(SimpleNamespace(expert_telegram_ids=frozenset({42})), None, store)
    return store, sid, update, ui, messages


def callback(ui, update, data):
    update.callback_query.data = data
    asyncio.run(ui.callback(update, None))


def test_partial_feedback_is_committed_before_leaving_or_finishing(tmp_path):
    store, sid, update, ui, messages = harness(tmp_path)
    aid = store.claim(sid, 42, "Q1")
    store.save_answer(aid, Answer("Полезная часть и ограничение", generation_status="rejected",
                                reasoning_effort="medium", llm_call_attempted=True,
                                rag_query="Проверка ККТ", response_repair={"removed": ["выдумка"]}))
    callback(ui, update, f"ex:rate:{sid}:{aid}:6")
    callback(ui, update, f"ex:tag:{sid}:{aid}:refusal")
    callback(ui, update, f"ex:tag:{sid}:{aid}:incomplete")
    callback(ui, update, f"ex:comment:{sid}:{aid}")
    assert asyncio.run(ui.comment_message(update))

    reopened = ExpertStore(store.path)
    row = reopened.latest(sid, "Q1")
    assert row["score"] == 6 and row["comment"] == "Исправьте этот шаг"
    assert row["generation_status"] == "rejected"
    assert row["reasoning_effort"] == "medium" and row["llm_call_attempted"] == 1
    assert reopened.tags(aid) == ["incomplete", "refusal"]
    assert reopened.active(42)["id"] == sid  # The session was never finished.
    assert reopened.progress(sid, 42) == (1, 3)


def test_skip_jump_and_return_do_not_generate_or_erase_answers(tmp_path):
    store, sid, update, ui, messages = harness(tmp_path)
    callback(ui, update, f"ex:skip:{sid}")
    assert store.current(sid, 42)["question_id"] == "Q2"
    assert store.questions(sid, 42)[0]["skipped_at"]
    callback(ui, update, f"ex:select:{sid}:2")
    assert store.current(sid, 42)["question_id"] == "Q3"
    callback(ui, update, f"ex:prev:{sid}")
    assert store.current(sid, 42)["question_id"] == "Q2"
    callback(ui, update, f"ex:list:{sid}:0")
    assert "оценено 0/3" in messages[-1][0]
    assert not [r for r in store.rows() if r["attempt_id"]]
    assert not store.select(sid, 999, 0)


def test_tags_toggle_and_cannot_modify_another_testers_review(tmp_path):
    store, sid, update, ui, messages = harness(tmp_path)
    aid = store.claim(sid, 42, "Q1")
    store.save_answer(aid, Answer("Ответ", generation_status="generated"))
    store.rate(sid, 42, aid, 7)
    store.reason(sid, 42, aid, "Старый комментарий о причине")
    assert not store.toggle_tag(sid, 999, aid, "wrong")
    assert store.toggle_tag(sid, 42, aid, "wrong")
    assert store.toggle_tag(sid, 42, aid, "wrong")
    assert store.tags(aid) == []
    assert store.latest(sid, "Q1")["reason"] == "Старый комментарий о причине"


def test_technical_failure_can_be_reviewed_but_keeps_technical_status(tmp_path):
    store, sid, update, ui, messages = harness(tmp_path)
    aid = store.claim(sid, 42, "Q1")
    store.save_error(aid)
    asyncio.run(ui.show_answer(update, sid, "Q1"))
    assert "Технический сбой" in messages[-1][0]
    assert store.rate(sid, 42, aid, 1)
    assert store.latest(sid, "Q1")["generation_status"] == "error"
    assert store.latest(sid, "Q1")["total_tokens"] is None


def test_reviewing_two_attempts_counts_as_one_reviewed_question(tmp_path):
    store, sid, update, ui, messages = harness(tmp_path)
    for i in range(2):
        aid = store.claim(sid, 42, "Q1", force=True)
        store.save_answer(aid, Answer(f"Ответ {i}", generation_status="generated"))
        assert store.rate(sid, 42, aid, 8)
    assert store.progress(sid, 42) == (1, 3)
    report = statistics(store.rows())
    assert report['reviewed_questions'] == 1 and report['reviewed_attempts'] == 2
    callback(ui, update, f"ex:finish:{sid}")
    assert not store.active(42)
    assert len([r for r in store.rows() if r["attempt_id"]]) == 2


def test_telegram_callbacks_fit_byte_limit(tmp_path):
    store, sid, update, ui, messages = harness(tmp_path)
    aid = store.claim(sid, 42, "Q1")
    store.save_answer(aid, Answer("Ответ", generation_status="generated"))
    store.rate(sid, 42, aid, 9)
    asyncio.run(ui.feedback(update, sid, aid))
    asyncio.run(ui.question_list(update, sid, 0))
    for _, markup in messages:
        if markup:
            assert all(len(b.callback_data.encode("utf-8")) <= 64
                       for row in markup.inline_keyboard for b in row)


def test_reports_include_refusals_and_tags_but_separate_technical_feedback(tmp_path):
    store, sid, update, ui, messages = harness(tmp_path)
    rejected = store.claim(sid, 42, "Q1")
    store.save_answer(rejected, Answer("Общий отказ", generation_status="rejected", llm_call_attempted=True))
    store.rate(sid, 42, rejected, 2)
    store.toggle_tag(sid, 42, rejected, "refusal")
    store.select(sid, 42, 1)
    failed = store.claim(sid, 42, "Q2")
    store.save_answer(failed, Answer("Ошибка API", generation_status="error", llm_call_attempted=True))
    store.rate(sid, 42, failed, 1)
    report = statistics(store.rows())
    assert report["reviewed_questions"] == 1 and report["average_score"] == 2
    assert report["common_error_tags"] == {"refusal": 1}
    assert report["technical_feedback_count"] == 1
    assert report["technical_feedback_average_score"] == 1
    assert report["token_usage"]["llm_calls"] == 2
    _, _, path = export(store, tmp_path / "report")
    exported = json.loads(path.read_text(encoding="utf-8"))
    assert exported["questions"][0]["error_tags"] == "refusal"
