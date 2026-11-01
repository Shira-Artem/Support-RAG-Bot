"""Frozen-candidate, single-factor retrieval counterfactuals; no writes to live systems."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient
from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueManager, DialogueState
from app.dialogue_understanding import observation_from_dict
from app.embeddings import SentenceTransformerEmbedding
from app.retrieval import Retriever
from app.retrieval_pipeline import RetrievalPipeline, _state_task_category
from app.source_first_service import (_conceptually_answering_sentence,
                                      _focused_approved_sentence, _sections)
from app.vector_store import QdrantStore

OUT = Path(__file__).resolve().parent / "causal_replay.json"
COLLECTION = "knowledge_stage3_retrieval_20261022"
GOLD = "evotor/ofd/evotor-7-3-ofd-connection.md"


class FixedSource:
    def __init__(self, hits, adapter):
        self.hits = hits
        self.adapter = adapter

    def search(self, query, top_k=5):
        return self.hits[:top_k]

    def article(self, document_id):
        return self.adapter.article(document_id)


def compact(result, state, query):
    candidates = result.diagnostics()["candidates"]
    gold = next((x for x in candidates if x["source"].endswith(GOLD)), None)
    return {"expected_task": _state_task_category(state, query),
            "evidence_status": result.evidence_status,
            "sufficient": result.sufficient,
            "reason": result.insufficiency_reason,
            "selected_sources": [x.source for x in result.candidates if x.selected],
            "gold_candidate": ({"selected": gold["selected"], "reasons": gold["reasons"]}
                               if gold else None)}


def main():
    con = sqlite3.connect(f"file:{(ROOT / 'data/conversations.sqlite3').as_posix()}?mode=ro", uri=True)
    client = QdrantClient(url="http://127.0.0.1:6333", timeout=15)
    info = client.get_collection(COLLECTION)
    assert info.status.value == "green" and info.points_count == 934
    embedding = SentenceTransformerEmbedding("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    store = object.__new__(QdrantStore)
    store.client, store.embedding, store.collection = client, embedding, COLLECTION
    adapter = RetrieverRAGAdapter(Retriever(store, demo=False))
    cases = []
    for mid in (557, 559, 561, 565, 569):
        u = con.execute("SELECT content,diagnostics_json FROM messages WHERE id=?", (mid,)).fetchone()
        a = con.execute("SELECT diagnostics_json FROM messages WHERE id=?", (mid + 1,)).fetchone()
        ad = json.loads(a[0])
        query = ad.get("rag_query")
        if not query:
            continue
        state = DialogueState.from_dict(ad["dialogue_state"])
        hits = adapter.search(query, top_k=100)
        frozen = RetrievalPipeline(FixedSource(hits, adapter))
        baseline = compact(frozen.search(state, query), state, query)
        row = {"message_id": mid, "raw_hits": len(hits), "baseline": baseline}
        if mid in (557, 559):
            candidate = deepcopy(state)
            candidate.intent = "receipt"
            row["intent_receipt_only"] = compact(frozen.search(candidate, query), candidate, query)
        if mid == 565:
            validated = json.loads(u[1])["understanding"]
            isolated = DialogueManager().advance(DialogueState(), u[0], mid,
                                                  observation=observation_from_dict(validated, u[0], mid)[0])
            row["same_observation_empty_prior_state"] = compact(
                frozen.search(isolated, query), isolated, query)
            row["empty_prior_state_task_start"] = isolated.topic_start_message_id
        cases.append(row)
    question = con.execute("SELECT content FROM messages WHERE id=569").fetchone()[0]
    answer = json.loads(con.execute("SELECT diagnostics_json FROM messages WHERE id=570").fetchone()[0])
    wrong = answer["retrieval_diagnostics"]["coordinator_evidence"]["sentence"]
    source = (ROOT / "data/knowledge/atol_online/ofd/what-is-ofd.md").read_text(encoding="utf-8")
    right = dict(_sections(source.split("---", 2)[2]))["Что проверено по инструкции производителя"].split(".", 1)[0] + "."
    sections = [
        {"source": "aqsi_online/receipts/partial-refund.md", "section": "Когда нужен специалист", "text": wrong},
        {"source": "atol_online/ofd/what-is-ofd.md", "section": "Что проверено по инструкции производителя", "text": right},
    ]
    focus = answer["coordinator_decision"]["current_subgoal"]
    none_match = _focused_approved_sentence(sections, focus, conceptual_question=question)
    scoped_match = _focused_approved_sentence(sections, focus, conceptual_question=question,
                                              conceptual_subject="ОФД")
    conceptual = {
        "message_id": 569,
        "question_subject_in_validated_state": None,
        "wrong_sentence_accepted_without_subject": _conceptually_answering_sentence(wrong, question),
        "wrong_sentence_accepted_with_subject": _conceptually_answering_sentence(wrong, question, "ОФД"),
        "right_sentence_accepted_with_subject": _conceptually_answering_sentence(right, question, "ОФД"),
        "two_section_choice_without_subject": none_match[0]["source"] if none_match else None,
        "two_section_choice_with_subject": scoped_match[0]["source"] if scoped_match else None,
    }
    result = {"method": "read-only Stage3; fixed raw hit list per saved RAG query; one state factor changed at a time",
              "collection_points": info.points_count, "cases": cases, "conceptual_gate": conceptual}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
