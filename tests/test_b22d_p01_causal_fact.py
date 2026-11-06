"""Safety boundaries for the incomplete-order factual answer."""
from hashlib import sha256
from pathlib import Path

import pytest
import yaml

from app.dialogue_state import DialogueState, Fact, TaskContext
from app.source_first_service import _incomplete_order_causal_fact

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "На терминале Эвотор появилась ошибка ФН 234. Это точно означает, что накопитель надо заменить?"
SOURCE = ROOT / "data/knowledge/evotor/fn/fn-234.md"


def candidate(tmp_path, *, model=None, edit=None):
    raw = SOURCE.read_text(encoding="utf-8")
    if model:
        raw = raw.replace("model:\n", f'model: "{model}"\n', 1)
    if edit:
        raw = edit(raw)
    path = tmp_path / "source.md"
    path.write_text(raw, encoding="utf-8")
    _, front, body = raw.split("---", 2)
    scope = yaml.safe_load(front)
    section = body.split("## Первое различение причины", 1)[1].split("\n## ", 1)[0].strip()
    return {"source": "source.md", "source_sha256": sha256(path.read_bytes()).hexdigest(),
            "document_id": scope["document_id"], "section": "Первое различение причины",
            "text": section, "scope": scope, "indexed_section_match": True}


def state(manufacturer="Эвотор", model=None, service=None):
    entities = {"manufacturer": [Fact.span(manufacturer, 1)]}
    if model:
        entities["equipment"] = [Fact.span(model, 1)]
    if service:
        entities["service"] = [Fact.span(service, 1)]
    task = TaskContext(intent="unknown", operation="diagnose", entities=entities)
    return DialogueState(intent="unknown", operation="diagnose", entities=entities, task_context=task)


def test_control_independent_scope_and_exact_evidence(tmp_path):
    section = candidate(tmp_path)
    result = _incomplete_order_causal_fact(QUESTION, state(), section, tmp_path)
    assert result is not None
    units, boundary = result
    assert boundary == "До вывода о замене"
    assert len(units) == 2 and "ложное впечатление" in units[1].text
    assert _incomplete_order_causal_fact(QUESTION, state("АТОЛ"), section, tmp_path) is None
    assert _incomplete_order_causal_fact(QUESTION, state(service="aQsi Online"), section, tmp_path) is None


def test_question_about_certainty_without_meaning_verb_is_factual(tmp_path):
    question = 'Эвотор показывает ошибку ФН 234. По этому коду уже точно нужна замена накопителя?'
    assert _incomplete_order_causal_fact(question, state(), candidate(tmp_path), tmp_path) is not None


def test_wrong_model_is_not_transferred(tmp_path):
    section = candidate(tmp_path, model="Эвотор 5")
    assert _incomplete_order_causal_fact(QUESTION, state(model="Эвотор 7"), section, tmp_path) is None


@pytest.mark.parametrize("question", [
    "На терминале Эвотор ошибка ФН 234. Это означает, что надо заменить? Покажите как заменить ФН?",
    "На терминале Эвотор ошибка ФН 234. Замените ФН, это означает его окончание?",
    "На терминале Эвотор ошибка ФН 234. Это означает окончание срока, и можно ли заменить накопитель?",
])
def test_action_request_is_not_fact_only_permission(tmp_path, question):
    assert _incomplete_order_causal_fact(question, state(), candidate(tmp_path), tmp_path) is None


@pytest.mark.parametrize("edit", [
    lambda text: text.replace("неверное время может создать ложное впечатление, что срок ФН завершился.",
                              "обратитесь к специалисту."),
    lambda text: text.replace("предлагается проверить, правильно ли", "предлагается проверить, только если смена закрыта и правильно ли"),
    lambda text: text.replace("что срок ФН завершился.", "что срок ФН завершился. Только специалист может подтвердить причину."),
    lambda text: text.replace("что срок ФН завершился.", "что выключите кассу."),
])
def test_no_fact_or_detached_important_condition_is_rejected(tmp_path, edit):
    assert _incomplete_order_causal_fact(QUESTION, state(), candidate(tmp_path, edit=edit), tmp_path) is None


def test_index_disagreement_and_changed_source_are_rejected(tmp_path):
    section = candidate(tmp_path)
    section["indexed_section_match"] = False
    assert _incomplete_order_causal_fact(QUESTION, state(), section, tmp_path) is None
    section["indexed_section_match"] = True
    (tmp_path / "source.md").write_text("changed", encoding="utf-8")
    assert _incomplete_order_causal_fact(QUESTION, state(), section, tmp_path) is None
