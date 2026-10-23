"""Existing AnswerService interface backed by approved hybrid search."""
from __future__ import annotations

import os
from pathlib import Path

from app.rag import SearchResult, SimpleRAG
from app.retrieval import Retriever
from app.retrieval_pipeline import RetrievalPipeline, RetrievalResult
from app.runtime import build_retriever


class RetrieverRAGAdapter:
    def __init__(self, retriever: Retriever):
        self.retriever = retriever
        self.pipeline = RetrievalPipeline(self)
        self._articles = None

    def search_for_state(self, state, query: str) -> RetrievalResult:
        return self.pipeline.search(state, query)

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        return [SearchResult(hit.metadata["source"], hit.text, hit.score,
                             hit.semantic_score, hit.lexical_score, hit.metadata)
                for hit in self.retriever.search(query, top_k)]

    def article(self, document_id: str) -> list[SearchResult]:
        """Read sibling chunks after the article has passed relevance gates."""
        if self._articles is None:
            self._articles = {}
            for point in self.retriever.store.all_points():
                payload = point.payload
                if self.retriever._allowed(payload, {}):
                    self._articles.setdefault(payload.get("document_id"), []).append(point)
            for points in self._articles.values():
                # New indexes preserve source order explicitly.  Legacy
                # collections have no recoverable ordinal, so keep a stable
                # fallback without pretending alphabetical section order is
                # the document order.
                points.sort(key=lambda p: (
                    0 if isinstance(p.payload.get("chunk_index"), int) else 1,
                    p.payload.get("chunk_index") if isinstance(p.payload.get("chunk_index"), int) else 0,
                    p.payload.get("page") or 0,
                    str(p.id),
                ))
        return [SearchResult(str(p.payload.get("source") or ""), p.payload["text"], 0.0,
                             metadata={k: v for k, v in p.payload.items() if k != "text"})
                for p in self._articles.get(document_id, [])]

    def search_for_service(self, query: str, service: str | None, top_k: int = 5) -> list[SearchResult]:
        from app.answer_service import _SERVICE_SOURCE_PREFIXES
        prefixes = _SERVICE_SOURCE_PREFIXES.get(service or '')
        hits = self.retriever.search(query, top_k, source_prefixes=prefixes)
        results = [SearchResult(hit.metadata['source'], hit.text, hit.score,
                             hit.semantic_score, hit.lexical_score, hit.metadata)
                   for hit in hits]
        if not results or not service:
            return results
        return results

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
