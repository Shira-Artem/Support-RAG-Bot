"""Offline P0.2 replay from checked-in reviewed articles; no Qdrant or LLM."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.dialogue_state import DialogueManager, DialogueState
from app.knowledge import Chunker, DocumentLoader
from app.rag import SearchResult
from app.rag_query import build_rag_query
from app.retrieval_pipeline import RetrievalPipeline

ARTICLES = (
    "1c/bank/directbank-all-accounts.md",
    "1c/bank/directbank-other-banks.md",
    "1c/bank/import-file-directbank.md",
)
CASES = (
    ("original", "В 1С перестали загружаться банковские выписки. Как разобраться?"),
    ("paraphrase_missing", "В 1С банковские выписки больше не загружаются. Как разобраться?"),
    ("paraphrase_stale", "Перестала обновляться банковская выписка в 1С. Как выяснить причину?"),
    ("foreign_service", "В aQsi Online перестали загружаться банковские выписки. Как разобраться?"),
    ("older_version", "В 1С:Бухгалтерии 3.0.147 перестали загружаться банковские выписки. Как разобраться?"),
    ("fn_change", "Нужно изменить настройки фискального накопителя. Подскажите порядок действий."),
    ("kkt_reregistration", "Нужно перерегистрировать ККТ после замены ФН. Что делать?"),
)


class MemorySource:
    def __init__(self):
        loader = DocumentLoader(ROOT / "data/knowledge")
        self.articles = {}
        self.hits = []
        for rank, rel in enumerate(ARTICLES):
            doc = loader.load(ROOT / "data/knowledge" / rel)
            chunks = [SearchResult(doc.source, chunk.text, 0.95 - rank * 0.05,
                                   metadata=chunk.metadata)
                      for chunk in Chunker().split(doc)]
            self.articles[doc.document_id] = chunks
            self.hits.extend(chunks)

    def search(self, query, top_k=100):
        return self.hits[:top_k]

    def article(self, document_id):
        return self.articles.get(document_id, [])


def replay():
    source = MemorySource()
    rows = []
    for case_id, question in CASES:
        state = DialogueManager().advance(DialogueState(), question, 1)
        query = build_rag_query(state)
        result = RetrievalPipeline(source).search(state, query)
        rows.append({"id": case_id, "question": question, "rag_query": query,
                     "state": {"intent": state.intent, "operation": state.operation,
                               "routing_slot": state.routing_slot,
                               "routing_service": state.routing_service},
                     "candidate_document_ids": [x.document_id for x in result.candidates],
                     "rejected": [{"document_id": x.document_id, "reasons": x.reasons}
                                  for x in result.rejected],
                     "context_document_ids": list(dict.fromkeys(
                         str((x.metadata or {}).get("document_id")) for x in result.documents)),
                     "context_sections": [(x.metadata or {}).get("section") for x in result.documents],
                     "context": result.context,
                     "supported_steps": result.supported_steps,
                     "evidence_status": result.evidence_status,
                     "evidence_level": result.evidence_level,
                     "insufficiency_reason": result.insufficiency_reason})
    paths = ["app/procedure_policy.py", "app/retrieval_pipeline.py", *(
        f"data/knowledge/{path}" for path in ARTICLES)]
    return {"head": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                              cwd=ROOT, text=True).strip(),
            "sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                       for path in paths},
            "llm_calls": 0, "qdrant_calls": 0, "cases": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in result["cases"]:
        print(json.dumps({k: row[k] for k in (
            "id", "state", "candidate_document_ids", "rejected",
            "context_sections", "evidence_status", "evidence_level")}, ensure_ascii=False))
