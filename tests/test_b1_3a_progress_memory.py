"""B1.3a independent controls for client-reported diagnostic outcomes."""
from copy import deepcopy

from app.dialogue_state import DialogueManager, DialogueState, Fact, Observation, TaskContext


def _state(*labels):
    manager = DialogueManager()
    state = DialogueState(task_context=TaskContext(task_id="task:1", intent="receipt",
        operation="diagnose"))
    units = [{"unit_id": f"u{index}", "label": label, "source_verified": True,
              "source": "approved/example.md", "section": "Проверки", "model_scope": []}
             for index, label in enumerate(labels, 1)]
    state = manager.observe_answer(state, scenario="answer", reason="source_first_exact_section",
        question="\n".join(labels), message_id=1,
        progress_update={"procedure_id": "approved-example", "shown_units": units,
                         "eligible_units": units})
    return manager, state


def _client(manager, state, text, mid):
    obs = Observation(evidence=Fact.span(text, mid), relation="continue",
        intent="unknown", operation="unknown", request_type="feedback")
    return manager.advance(state, text, mid, observation=obs)


def _checks(state):
    return {item["unit_id"]: item for item in state.task_context.checks}


def test_asked_action_and_uninformative_completion_do_not_pass():
    manager, state = _state("Проверьте подключение к интернету")
    assert _checks(state)["u1"]["status"] == "asked"
    assert _checks(state)["u1"]["task_id"] == "task:1"
    assert _checks(state)["u1"]["source"] == "approved/example.md"
    assert _checks(state)["u1"]["label"] == "Проверьте подключение к интернету"
    assert _checks(state)["u1"]["source_verified"] is True
    assert _checks(state)["u1"]["asked_message_id"] == 1
    checked = _client(manager, state, "Проверил", 2)
    assert _checks(checked)["u1"]["status"] != "passed"
    assert not _checks(checked)["u1"].get("result_span")


def test_explicit_outcome_unknown_not_done_and_contradiction_history():
    manager, state = _state("Проверьте подключение к интернету")
    for mid, text, expected in [
        (2, "Интернет пока не проверял", "not_done"),
        (3, "Интернет не знаю", "unknown"),
        (4, "Интернет работает", "passed"),
        (5, "Интернет то работает, то пропадает", "failed"),
    ]:
        state = _client(manager, state, text, mid)
        check = _checks(state)["u1"]
        assert check["status"] == expected
        assert check["result_span"]["message_id"] == mid
        assert check["result_span"]["quote"] == text
    assert _checks(state)["u1"]["contradictions"][-1]["after"]["quote"] == "Интернет то работает, то пропадает"


def test_report_print_correction_changes_status_and_preserves_history():
    manager, state = _state("Напечатайте диагностический отчёт")
    state = _client(manager, state, "Диагностический отчёт напечатал", 2)
    assert _checks(state)["u1"]["status"] == "passed"
    state = _client(manager, state, "Я ошибся: диагностический отчёт не напечатался", 3)
    check = _checks(state)["u1"]
    assert check["status"] == "failed"
    assert [item["status"] for item in check["observations"]] == ["passed", "failed"]
    assert check["contradictions"][-1]["after"]["message_id"] == 3


def test_two_results_in_one_sentence_bind_to_distinct_units():
    manager, state = _state("Проверьте подключение к интернету",
                            "Посмотрите очередь документов")
    state = _client(manager, state,
        "Интернет работает, очередь документов не уменьшается", 2)
    assert _checks(state)["u1"]["status"] == "passed"
    assert _checks(state)["u2"]["status"] == "failed"
    assert "не уменьшается" not in _checks(state)["u1"]["result_span"]["quote"]
    assert "Интернет работает" not in _checks(state)["u2"]["result_span"]["quote"]


def test_one_result_does_not_complete_broad_procedure():
    manager, state = _state("Проверьте подключение к интернету",
        "Проверьте подключение к интернету, затем посмотрите очередь документов")
    state = _client(manager, state, "Интернет работает", 2)
    assert _checks(state)["u1"]["status"] == "passed"
    assert _checks(state)["u2"]["status"] != "passed"


def test_reprocessing_same_client_event_is_idempotent():
    manager, state = _state("Проверьте подключение к интернету")
    state = _client(manager, state, "Интернет работает", 2)
    before = deepcopy(_checks(state)["u1"])
    again = _client(manager, state, "Интернет работает", 2)
    assert _checks(again)["u1"] == before


def test_model_switch_and_new_task_do_not_reuse_old_checks():
    manager, state = _state("Проверьте подключение к интернету")
    state.task_context.shown_units[0]["model_value"] = "Эвотор 7.3"
    state.task_context.eligible_units[0]["model_value"] = "Эвотор 7.3"
    state.task_context.entities = {"equipment": [Fact.span("Эвотор 7.3", 1)]}
    correction = "Я ошибся с моделью: Эвотор 6"
    model = Fact.span(correction, 2, correction.index("Эвотор"))
    state = manager.advance(state, correction, 2, observation=Observation(
        evidence=Fact.span(correction, 2), relation="contradiction", intent="receipt",
        operation="diagnose", entities={"equipment": [model]}))
    assert not state.task_context.shown_units and not state.task_context.eligible_units
    assert _checks(state)["u1"]["status"] == "asked"
    other = "В Saby не вижу входящий УПД"
    state = manager.advance(state, other, 3, observation=Observation(
        evidence=Fact.span(other, 3), relation="new_task", intent="delivery_document",
        operation="diagnose", symptom=Fact.span(other, 3),
        entities={"service": [Fact.span(other, 3, other.index("Saby"), other.index("Saby") + 4)]}))
    assert state.task_id != "task:1"
    assert state.task_context.checks == state.task_context.shown_units == state.task_context.eligible_units == []


def test_failed_or_unpublished_answer_never_records_proposed_unit():
    manager, state = _state()
    unit = {"unit_id": "u1", "label": "Проверьте подключение к интернету",
            "source_verified": True, "source": "approved/example.md"}
    failure = manager.observe_answer(state, scenario="escalate", reason="understanding_error",
        question="Ошибка модели", progress_update={"shown_units": [unit]})
    assert failure.task_context.shown_units == failure.task_context.checks == []
    incomplete = manager.observe_answer(state, scenario="answer", reason="source_first_exact_section",
        question="Ответ не был опубликован", progress_update=None)
    assert incomplete.task_context.shown_units == incomplete.task_context.checks == []


def test_short_result_requires_one_unambiguous_shown_check():
    manager, state = _state("Проверьте подключение к интернету")
    result = _client(manager, state, "Работает", 2)
    assert _checks(result)["u1"]["status"] == "passed"
    manager, multiple = _state("Проверьте подключение к интернету", "Посмотрите очередь документов")
    ambiguous = _client(manager, multiple, "Работает", 2)
    assert all(check["status"] == "asked" for check in _checks(ambiguous).values())
    unclear = _client(manager, state, "Не помогло", 3)
    assert _checks(unclear)["u1"]["status"] != "passed"


def test_sqlite_reopen_and_failed_answer_do_not_publish_check(tmp_path):
    from app.answer_service import Answer
    from app.conversation_store import ConversationStore
    from app.dialogue_understanding import Understanding, understanding_to_dict

    store = ConversationStore(tmp_path / "progress.sqlite3")
    cid = store.new(42, 42)
    text = "Эвотор не отправляет чеки"
    obs = Observation(evidence=Fact.span(text, "current"), relation="new_task",
        intent="receipt", operation="diagnose", request_type="diagnosis",
        symptom=Fact.span(text, "current", text.index("не отправляет")))
    pending = store.begin(cid, text, semantic_mode=True,
        understanding=understanding_to_dict(Understanding("diagnosis", False, (), obs, {}, "test", 0)))
    assert store.dialogue_state(cid).task_context.shown_units == []
    unit = {"unit_id": "internet", "label": "Проверьте подключение к интернету",
            "source_verified": True, "source": "approved/example.md", "section": "Проверки"}
    store.complete(pending, Answer("Ошибка генерации", generation_status="error",
        scenario="answer", scenario_reason="source_first_exact_section",
        validation_status="exact_source_copy", progress_update={"shown_units": [unit]}))
    assert ConversationStore(store.path).dialogue_state(cid).task_context.shown_units == []


def test_telegram_send_failure_does_not_mark_check_as_shown(monkeypatch, tmp_path):
    import asyncio
    import importlib
    import sys
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from pathlib import Path

    from app.answer_service import Answer
    from app.config import Settings
    from app.conversation_store import ConversationStore
    from app.dialogue_understanding import Understanding, validate_response
    from app.expert_store import ExpertStore

    store = ConversationStore(tmp_path / "delivery.sqlite3")
    cid = store.new(42, 42)
    settings = Settings(telegram_bot_token="offline-token", openrouter_api_key="",
        openrouter_model="offline", app_name="offline", app_url="http://localhost",
        show_sources=True, docs_dir=Path(__file__).resolve().parents[1] / "data/docs",
        llm_provider="groq", groq_api_key="offline-key", groq_model="openai/gpt-oss-20b",
        groq_reasoning_effort="medium", rag_engine="source_first",
        source_first_telegram_ids=frozenset({42}), ai_coordinator_enabled=False)

    class ReadOnlyCheck:
        def __init__(self, **kwargs): pass
        def collection_exists(self, name): return True
        def get_collection(self, name): return SimpleNamespace(points_count=1)

    monkeypatch.setenv("RAG_BACKEND", "qdrant")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.compat.build_answer_rag", lambda docs: SimpleNamespace())
    monkeypatch.setattr("app.conversation_store.ConversationStore", lambda: store)
    monkeypatch.setattr("app.expert_store.ExpertStore", lambda: ExpertStore(tmp_path / "expert.sqlite3"))
    monkeypatch.setattr("qdrant_client.QdrantClient", ReadOnlyCheck)
    sys.modules.pop("bot", None)
    bot = importlib.import_module("bot")
    try:
        async def understanding(text, message_id, history, state, config):
            raw = {"request_type": "diagnosis", "relation": "new_task", "intent": "receipt",
                "operation": "diagnose", "object": None, "object_evidence": None,
                "goal": None, "symptom": {"quote": "не уходят чеки"}, "entities": [],
                "unknown_facts": [], "specialist_requested": False,
                "specialist_evidence": None, "confidence": 0.9}
            kind, specialist, unknown, obs = validate_response(raw, text, message_id, state)
            return Understanding(kind, specialist, unknown, obs, {}, "offline", 0, raw,
                                 obs.validation_diagnostics)

        unit = {"unit_id": "internet", "label": "Проверьте подключение к интернету",
                "source_verified": True, "source": "approved/example.md", "section": "Проверки"}
        async def answer(*args, **kwargs):
            return Answer("Проверьте подключение к интернету", rag_engine="source_first",
                scenario="answer", scenario_reason="source_first_exact_section",
                generation_status="generated", validation_status="exact_source_copy",
                progress_update={"procedure_id": "approved-example", "shown_units": [unit],
                                 "eligible_units": [unit]})

        monkeypatch.setattr(bot, "understand_message", understanding)
        monkeypatch.setattr(bot.source_first_service, "answer", answer)
        reply = AsyncMock(side_effect=RuntimeError("Telegram send failed"))
        message = SimpleNamespace(text="Эвотор не уходят чеки", reply_text=reply,
            chat=SimpleNamespace(send_action=AsyncMock()))
        update = SimpleNamespace(message=message, effective_message=message,
            effective_user=SimpleNamespace(id=42), effective_chat=SimpleNamespace(id=42))
        import pytest
        with pytest.raises(RuntimeError, match="Telegram send failed"):
            asyncio.run(bot.handle_message(update, None))
        reopened = ConversationStore(store.path)
        assert reopened.dialogue_state(cid).task_context.shown_units == []
        with reopened.connect() as db:
            assert db.execute("SELECT status FROM messages WHERE role='assistant' ORDER BY id DESC LIMIT 1").fetchone()[0] == "failed"
        assert all(item["role"] != "assistant" for item in reopened.history(cid))
        # Failed delivery is terminal for that assistant event, not a pending
        # turn that blocks the customer's next message.
        reopened.begin(cid, "Продолжаю", semantic_mode=True, understanding_error="offline")
    finally:
        sys.modules.pop("bot", None)


def test_two_outcomes_and_source_metadata_survive_sqlite_reopen(tmp_path):
    from app.answer_service import Answer
    from app.conversation_store import ConversationStore
    from app.dialogue_understanding import Understanding, understanding_to_dict

    store = ConversationStore(tmp_path / "two-results.sqlite3")
    cid = store.new(42, 42)
    opening = "Эвотор не отправляет чеки"
    obs = Observation(evidence=Fact.span(opening, "current"), relation="new_task",
        intent="receipt", operation="diagnose", request_type="diagnosis",
        symptom=Fact.span(opening, "current", opening.index("не отправляет")))
    pending = store.begin(cid, opening, semantic_mode=True,
        understanding=understanding_to_dict(Understanding("diagnosis", False, (), obs, {}, "test", 0)))
    units = [{"unit_id": "internet", "label": "Проверьте подключение к интернету",
              "source_verified": True, "source": "approved/example.md", "section": "Проверки"},
             {"unit_id": "queue", "label": "Посмотрите очередь документов",
              "source_verified": True, "source": "approved/example.md", "section": "Проверки"}]
    store.complete(pending, Answer("Проверьте подключение к интернету. Посмотрите очередь документов.",
        scenario="answer", scenario_reason="source_first_exact_section",
        generation_status="generated", validation_status="exact_source_copy",
        progress_update={"procedure_id": "approved-example", "shown_units": units,
                         "eligible_units": units}))
    state = ConversationStore(store.path).dialogue_state(cid)
    assert [c["status"] for c in state.task_context.checks] == ["asked", "asked"]
    text = "Интернет работает, очередь документов не уменьшается"
    feedback = Observation(evidence=Fact.span(text, "current"), relation="continue",
        intent="unknown", operation="unknown", request_type="feedback")
    pending = store.begin(cid, text, semantic_mode=True,
        understanding=understanding_to_dict(Understanding("feedback", False, (), feedback, {}, "test", 0)))
    store.complete(pending, Answer("Результаты сохранены", scenario="clarify",
        generation_status="clarification"))
    reopened = ConversationStore(store.path)
    state = reopened.dialogue_state(cid)
    assert state.to_dict() == reopened.dialogue_state(cid).to_dict()
    checks = _checks(state)
    assert checks["internet"]["status"] == "passed"
    assert checks["queue"]["status"] == "failed"
    for check in checks.values():
        assert check["task_id"] == state.task_id
        assert check["source_verified"] is True
        assert check["source"] == "approved/example.md"
        assert check["label"]
        assert check["asked_message_id"] == 2
        assert check["result_span"]["message_id"] == 3
        assert text[check["result_span"]["start"]:check["result_span"]["end"]] == check["result_span"]["quote"]
