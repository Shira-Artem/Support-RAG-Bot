import asyncio

from app.answer_service import Answer
from app.dialogue_state import DialogueState, ExpectedClarification, Fact, TaskContext
from app.source_first_service import (
    _next_unasked_clarification,
    _resolve_planner_section_reference,
    _technical_section_covers_observed_subject,
    SourceFirstService,
)


def candidate(section, *, document_id="doc-1"):
    return {"id": f"{document_id}::{section}", "document_id": document_id,
            "source": "approved.md", "section": section, "title": section,
            "text": "Подтверждённый текст", "scope": {"task_category": "integration"}}


def test_incomplete_document_reference_resolves_only_one_vetted_section():
    first = candidate("Первичная проверка")
    selected, reason = _resolve_planner_section_reference("doc-1", [first])
    assert selected is first
    assert reason == "unique_candidate_document_id"


def test_incomplete_document_reference_does_not_choose_between_sections():
    first = candidate("Первичная проверка")
    second = candidate("Следующая проверка")
    assert _resolve_planner_section_reference("doc-1", [first, second]) == (None, None)
    assert _resolve_planner_section_reference("unvetted", [first]) == (None, None)


def test_clarification_fallback_uses_new_question_then_stops_repeats():
    history = [{"role": "assistant", "scenario": "clarify",
                "content": "Что именно происходит с кассой?"}]
    options = ["Что именно происходит с кассой?", "Какой результат вы хотите получить?"]
    assert _next_unasked_clarification(history, options, expected=options[0]) == options[1]
    history.append({"role": "assistant", "scenario": "clarify", "content": options[1]})
    assert _next_unasked_clarification(history, options, expected=options[1]) is None


def test_final_answer_boundary_replaces_retained_expected_question():
    first = "Что именно происходит с кассой? Напишите, пожалуйста, текст ошибки или какой результат вы видите."
    state = DialogueState(expected=ExpectedClarification("task", first, 1, "incomplete"))
    service = SourceFirstService(None, None, None)

    async def repeated(*_args, **_kwargs):
        return Answer(first, scenario="clarify", scenario_reason="dialogue_state_task_incomplete")

    service._answer = repeated
    answer = asyncio.run(service.answer("Не знаю", state=state, history=[]))
    assert answer.scenario == "clarify"
    assert answer.text == "Какой результат вы хотите получить?"


def test_workflow_relevance_uses_confirmed_task_evidence_without_system_name_only():
    task = TaskContext(task_id="task:test", intent="integration", operation="diagnose",
        task_fact=Fact.span("Поставщик отправил документ через Диадок, в 1С документ не появился", 1),
        symptom=Fact.span("в 1С документ не появился", 1))
    state = DialogueState(task_context=task)
    state.symptom = task.symptom
    unrelated = candidate("Различие между ЭПД и ЭДО")
    unrelated["text"] = "ЭПД отправляется адресату; правила обычного ЭДО отличаются."
    related = candidate("Поставщик отправил документ")
    related["text"] = "Проверьте, что поставщик отправил документ."

    assert not _technical_section_covers_observed_subject(state, unrelated)
    assert _technical_section_covers_observed_subject(state, related)
