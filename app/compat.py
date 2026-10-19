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

    def search_for_service(self, query: str, service: str | None, top_k: int = 5) -> list[SearchResult]:
        from app.answer_service import _SERVICE_SOURCE_PREFIXES
        prefixes = _SERVICE_SOURCE_PREFIXES.get(service or '')
        hits = self.retriever.search(query, top_k, source_prefixes=prefixes)
        results = [SearchResult(hit.metadata['source'], hit.text, hit.score,
                             hit.semantic_score, hit.lexical_score, hit.metadata)
                   for hit in hits]
        if not results or not service:
            return results
        # Retrieve the article, not just its question heading. Existing metadata
        # identifies adjacent sections, so this needs no reindex or model call.
        best = results[0]
        same_article = [r for r in results if r.source == best.source]
        known = {r.text for r in same_article}
        for point in self.retriever.store.all_points():
            payload = point.payload
            if payload.get('source') == best.source and payload['text'] not in known and self.retriever._allowed(payload, {}):
                same_article.append(SearchResult(best.source, payload['text'], best.score,
                                                metadata={k: v for k, v in payload.items() if k != 'text'}))
        return (same_article + [r for r in results if r.source != best.source])[:top_k]

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
