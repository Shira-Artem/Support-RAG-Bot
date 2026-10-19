"""Existing AnswerService interface backed by approved hybrid search."""
from __future__ import annotations

import os
from pathlib import Path

from app.rag import SearchResult, SimpleRAG
from app.retrieval import Retriever
from app.runtime import build_retriever


class RetrieverRAGAdapter:
    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        return [SearchResult(hit.metadata["source"], hit.text, hit.score,
                             hit.semantic_score, hit.lexical_score, hit.metadata)
                for hit in self.retriever.search(query, top_k)]

    def build_context(self, results: list[SearchResult]) -> str:
        return SimpleRAG.build_context(self, results)

    def list_sources(self) -> list[str]:
        return sorted({point.payload["source"] for point in self.retriever.store.all_points()
                       if self.retriever.demo or point.payload.get("status") == "approved"})

    def reload(self) -> None:
        # Indexing is an operator action; a public Telegram command must not approve or import documents.
        pass

    @property
    def chunks(self) -> list:
        return [point for point in self.retriever.store.all_points()
                if self.retriever.demo or point.payload.get("status") == "approved"]


def build_answer_rag(docs_dir: Path):
    if os.getenv("RAG_BACKEND", "qdrant") == "legacy_demo":
        return SimpleRAG(docs_dir)
    return RetrieverRAGAdapter(build_retriever())
