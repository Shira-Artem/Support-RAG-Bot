"""Current B2 corpus contracts, separate from historical replay snapshots."""
import asyncio
import json
from collections import Counter
from pathlib import Path

from app.dialogue_state import DialogueManager, DialogueState, Fact, Observation
from app.llm_client import Generation
from app.knowledge import Chunker, DocumentLoader
from app.response_grounding import claim_supported
from app.source_first_service import SourceFirstService, _sections
from test_source_first_dialogue_contract import OneResult, _retrieval, settings

ROOT = Path(__file__).resolve().parents[1]


def test_current_corpus_loads_without_duplicate_documents_or_chunks():
    loader = DocumentLoader(ROOT / "data/knowledge")
    docs = [loader.load(p) for p in sorted(loader.root.rglob("*.md"))]
    assert len(docs) == 269
    assert Counter(d.status for d in docs) == {"approved": 204, "draft": 65}
    assert len({d.document_id for d in docs}) == len(docs)
    assert len({d.content_hash for d in docs}) == len(docs)
    chunks = [c for d in docs for c in Chunker().split(d)]
    assert len(chunks) == len({c.id for c in chunks}) == 1168
    approved = [c for c in chunks if c.metadata["status"] == "approved"]
    assert len(approved) == 833
    assert all(c.metadata["source_url"].startswith("https://") for c in approved)


def test_current_nested_sections_are_individually_verified():
    loader = DocumentLoader(ROOT / "data/knowledge")
    for path in sorted(loader.root.rglob("*.md")):
        doc = loader.load(path)
        parsed = {h for _, body in doc.pages for h, _ in _sections(body)}
        indexed = {c.section for c in Chunker().split(doc) if c.section}
        assert indexed <= parsed, (doc.source, indexed - parsed)
    doc = loader.load(loader.root / "evotor/ofd/evotor-7-3-ofd-connection.md")
    sections = dict(_sections(doc.pages[0][1]))
    assert '«Выход в интернет»' in sections
    assert '«Приложение EoU»' in sections
    assert 'Сброс' not in sections['«Выход в интернет»']


def test_expanded_ofd_definition_does_not_support_invented_tariff_renewal():
    doc = DocumentLoader(ROOT / "data/knowledge").load(ROOT / "data/knowledge/atol_online/ofd/what-is-ofd.md")
    context = "\n".join(body for _, body in doc.pages)
    assert claim_supported("Получает фискальные документы от кассы в электронной форме.", context)
    assert not claim_supported("ОФД автоматически продлевает тариф кассы.", context)
    assert not claim_supported("Оператор самостоятельно пролонгирует договор.", context)
    assert claim_supported("Оператор продлевает тариф.", "Оператор продлевает тариф.")


def test_current_fn234_publishes_safe_first_check_from_mixed_section(monkeypatch, tmp_path):
    import json
    source = "evotor/fn/fn-234.md"
    question = "На моей кассе Эвотор появилась ошибка ФН 234. Обязательно менять накопитель?"
    body = (ROOT / "data/knowledge" / source).read_text(encoding="utf-8").split("---", 2)[2].strip()
    sections = dict(_sections(body))
    heading = next(h for h in sections if h.startswith("Шаг 1."))
    retrieval = _retrieval(source, "evotor-fn-234-360005580254", heading,
        {"service": "Эвотор", "manufacturer": "Эвотор", "model": None,
         "task_category": "error_diagnosis", "operations": ["diagnose_error"]}, sections[heading])
    answer_state = DialogueManager().advance(DialogueState(), question, 1,
        observation=Observation(intent="device", request_type="diagnosis", operation="diagnose",
            object="касса", evidence=Fact.span(question, 1),
            entities={"manufacturer": [Fact.span(question, 1, question.index("Эвотор"),
                                                  question.index("Эвотор") + 6)]},
            symptom=Fact.span(question, 1, question.index("ошибка ФН 234"),
                              question.index("ошибка ФН 234") + len("ошибка ФН 234")),
            goals=[Fact.span(question, 1, question.index("Обязательно"), len(question))],
            error=Fact.span(question, 1, question.index("234"), question.index("234") + 3,
                            value="234"),
            error_codes=[Fact.span(question, 1, question.index("234"), question.index("234") + 3,
                                   value="234")], relation="new_task"))

    async def select(messages, _settings, *, call_stage="generation"):
        payload = json.loads(messages[-1]["content"])
        candidate = next(item for item in payload["candidate_sections"] if item["section"] == heading)
        return Generation(json.dumps({"mode": "select", "section_id": candidate["id"],
            "applicability_confirmed": True, "source_order_complete": True,
            "reason": "frozen D04 matching incident code"}), "offline")

    monkeypatch.setattr("app.source_first_service.generate", select)
    answer = asyncio.run(SourceFirstService(OneResult(retrieval), settings(tmp_path), ROOT).answer(
        question, state=answer_state,
        coordinator_decision={"route": "technical_action", "current_subgoal": question}))
    assert answer.scenario == "answer"
    assert f"Источник: data/knowledge/{source}" in answer.text
    assert "проверьте дату и время" in answer.text
    assert "Замените ФН" not in answer.text and "Обязательно менять" not in answer.text
