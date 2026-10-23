"""Read-only Stage3 candidate source and auditable model-context selection.

No collection creation, indexing, dialogue routing, or network LLM calls occur here.
The dense strategy preserves the old top-six behaviour for paired diagnostics.
"""
from __future__ import annotations

import re
import time

from qdrant_client import QdrantClient, models

from app.embeddings import SentenceTransformerEmbedding
from app.retrieval import EXPANSIONS, Retriever, lexical_token, tokens

COLLECTION = "knowledge_stage3_retrieval_20261022"
MAX_DOCUMENTS = 8
MAX_CHUNKS_PER_DOCUMENT = 2
MAX_CONTEXT_CHARS = 16000
MAX_FRAGMENT_CHARS = 1400
SKIP_SECTIONS = {"вопрос", "вопрос клиента", "вопрос пользователя", "симптомы"}
TOPIC_SYNONYMS = {**EXPANSIONS, "искать": ["поиск", "найти"]}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("ё", "е")).strip()


def scope_compatible(candidate: dict, task: list[str]) -> tuple[bool, str]:
    """Post-retrieval service/model check; no early task or operation gate."""
    context = _norm(" ".join(task))
    service = _norm(str(candidate.get("service") or ""))
    model = _norm(str(candidate.get("model") or ""))
    named_services = (
        ("платформа офд", ("платформа офд", "платформе офд", "платформы офд")),
        ("aqsi online", ("aqsi online", "акси онлайн")),
        ("aqsi", ("aqsi", "акси")),
        ("атол онлайн", ("атол онлайн",)),
        ("атол", ("атол",)),
        ("эвотор", ("эвотор",)),
        ("первый офд", ("первый офд",)),
        ("штрих", ("штрих",)),
    )
    for name, aliases in named_services:
        if name in service:
            if not any(alias in context for alias in aliases):
                return False, "service_unconfirmed_or_other"
            break
    if model and any(ch.isdigit() for ch in model) and not ("1с" in model and "1с" in context):
        digits = re.findall(r"\d+(?:\.\d+)?", model)
        if digits and not any(d in context for d in digits):
            return False, "equipment_model_unconfirmed"
    return True, "scope_compatible"


def title_topic_match(candidate: dict, task: list[str]) -> tuple[bool, list[str]]:
    """Conservative *post-retrieval* relation check using the source title.

    This does not map a task to an operation enum. It prevents nearby articles
    about a different procedure from becoming instructions in the model prompt.
    """
    words = tokens(" ".join(task))
    query = {lexical_token(x) for x in words}
    # Lexical variants are symmetric for a title check: "создать пользователя"
    # must still relate to an article titled "добавление сотрудника".
    for source, synonyms in TOPIC_SYNONYMS.items():
        family = {lexical_token(x) for x in tokens(" ".join([source, *synonyms]))}
        if family & query:
            query |= family
    service_words = {lexical_token(x) for x in tokens(str(candidate.get("service") or ""))}
    query -= service_words
    title = {lexical_token(x) for x in tokens(str(candidate.get("title") or ""))}
    common = sorted(query & title)
    return len(common) >= 2, common


class ReadOnlyStore:
    """The small store protocol consumed by the existing production Retriever."""
    def __init__(self, client, embedding):
        self.client = client
        self.embedding = embedding
        self.last_dense = []
        self._all_points = None

    def all_points(self):
        if self._all_points is None:
            offset, points = None, []
            while True:
                batch, offset = self.client.scroll(
                    COLLECTION, offset=offset, limit=256,
                    with_payload=True, with_vectors=False)
                points.extend(batch)
                if offset is None:
                    break
            self._all_points = points
        return self._all_points

    def semantic(self, query, limit, query_filter=None):
        vector = self.embedding.embed([query])[0]
        self.last_dense = self.client.query_points(
            COLLECTION, query=vector, limit=limit,
            query_filter=query_filter, with_payload=True).points
        return self.last_dense


class ReadOnlyStage3:
    def __init__(self, url: str, embedding_name: str):
        client = QdrantClient(url=url, timeout=15)
        info = client.get_collection(COLLECTION)
        if info.points_count != 934 or info.config.params.vectors.size != 384:
            raise RuntimeError("Stage3 inventory differs from verified receipt")
        embedding = SentenceTransformerEmbedding(embedding_name)
        if embedding.dimension != 384:
            raise RuntimeError("Embedding dimension mismatch")
        self.store = ReadOnlyStore(client, embedding)
        self.retriever = Retriever(self.store, demo=False)
        approved = client.count(COLLECTION, count_filter=self.approved_filter, exact=True).count
        if approved != 672:
            raise RuntimeError("Approved inventory differs from verified receipt")
        self.receipt = {"collection": COLLECTION, "points": info.points_count,
                        "approved_points": approved, "embedding": embedding_name,
                        "retriever": "app.retrieval.Retriever BM25+Dense+RRF",
                        "context_limits": {"documents": MAX_DOCUMENTS,
                                           "chunks_per_document": MAX_CHUNKS_PER_DOCUMENT,
                                           "characters": MAX_CONTEXT_CHARS}}

    @property
    def approved_filter(self):
        return models.Filter(must=[models.FieldCondition(
            key="status", match=models.MatchValue(value="approved"))])

    def _siblings(self, doc_id: str):
        chunks = [p for p in self.store.all_points()
                  if (p.payload or {}).get("status") == "approved"
                  and str((p.payload or {}).get("document_id") or "") == doc_id]
        return sorted(chunks, key=lambda p: (
            p.payload.get("chunk_index") if isinstance(p.payload.get("chunk_index"), int) else 999,
            str(p.id)))

    def _ranked_documents(self, query: str, strategy: str):
        if strategy == "dense":
            dense = self.store.semantic(query[:500], 40, self.approved_filter)
            ranked = []
            seen = set()
            for rank, point in enumerate(dense, 1):
                doc = str((point.payload or {}).get("document_id") or "")
                if doc and doc not in seen:
                    seen.add(doc)
                    ranked.append({"document_id": doc, "score": float(point.score),
                                   "dense_chunk_rank": rank, "hybrid_chunk_rank": None,
                                   "lexical_score": None, "semantic_score": float(point.score)})
                if len(ranked) == 6:
                    break
            return ranked, dense, []
        if strategy != "hybrid":
            raise ValueError("strategy must be dense or hybrid")
        hits = self.retriever.search(query[:500], top_k=100)
        dense = self.store.last_dense
        point_ids = {}
        for point in self.store.all_points():
            payload = point.payload or {}
            point_ids.setdefault((str(payload.get("document_id") or ""),
                                  payload.get("chunk_index"),
                                  str(payload.get("text") or "")), str(point.id))
        raw_hits = []
        for rank, hit in enumerate(hits, 1):
            doc = str(hit.metadata.get("document_id") or "")
            raw_hits.append({"rank": rank, "chunk_id": point_ids.get((
                                 doc, hit.metadata.get("chunk_index"), hit.text)),
                             "document_id": doc, "title": hit.metadata.get("title"),
                             "section": hit.metadata.get("section"),
                             "service": hit.metadata.get("service"),
                             "model": hit.metadata.get("model"),
                             "operations": hit.metadata.get("operations"),
                             "status": hit.metadata.get("status"),
                             "rrf_score": hit.score,
                             "semantic_score": hit.semantic_score,
                             "bm25_score": hit.lexical_score})
        dense_doc_ranks = {}
        for i, point in enumerate(dense, 1):
            dense_doc_ranks.setdefault(str((point.payload or {}).get("document_id") or ""), i)
        ranked = []
        seen = set()
        for rank, hit in enumerate(hits, 1):
            doc = str(hit.metadata.get("document_id") or "")
            if doc and doc not in seen:
                seen.add(doc)
                ranked.append({"document_id": doc, "score": hit.score,
                               "dense_chunk_rank": dense_doc_ranks.get(doc),
                               "hybrid_chunk_rank": rank, "lexical_score": hit.lexical_score,
                               "semantic_score": hit.semantic_score})
        return ranked, dense, raw_hits

    def search_with_trace(self, query: str, task_messages: list[str], *,
                          strategy: str = "hybrid", query_origin: str = "llm_generated"):
        """Return exact model fragments plus candidate/rejection/context trace."""
        start = time.perf_counter()
        ranked, dense, raw_hits = self._ranked_documents(query, strategy)
        candidate_retrieval_ms = round((time.perf_counter() - start) * 1000)
        candidates = []
        context = []
        used_chars = 0
        accepted_docs = 0
        for doc_rank, row in enumerate(ranked, 1):
            doc_id = row["document_id"]
            siblings = self._siblings(doc_id)
            representative = (siblings[0].payload or {}) if siblings else {}
            compatible, reason = scope_compatible(representative, task_messages)
            topical, topic_tokens = title_topic_match(representative, task_messages)
            item = {**row, "document_rank": doc_rank,
                    "title": representative.get("title"), "topic_tokens": topic_tokens,
                    "status": representative.get("status"),
                    "service": representative.get("service"),
                    "model": representative.get("model"),
                    "operations": representative.get("operations"),
                    "chunk_ids": [str(p.id) for p in siblings],
                    "selected_chunk_ids": [], "decision": "rejected", "reason": reason}
            if representative.get("status") != "approved":
                item["reason"] = "status_not_approved"
            elif not compatible:
                pass
            elif not topical:
                item["reason"] = "title_topic_mismatch"
            elif accepted_docs >= MAX_DOCUMENTS:
                item["reason"] = "document_limit"
            else:
                useful = [p for p in siblings if _norm(str((p.payload or {}).get("section") or ""))
                          not in SKIP_SECTIONS]
                if not useful:
                    item["reason"] = "no_procedure_fragment"
                else:
                    # One fragment per document first, so late-ranked relevant
                    # documents cannot be starved by earlier sibling chunks.
                    first = useful[0]
                    text = str(first.payload.get("text") or "")[:MAX_FRAGMENT_CHARS]
                    if used_chars + len(text) <= MAX_CONTEXT_CHARS and text:
                        context.append(self._fragment(first, row, text))
                        used_chars += len(text)
                        accepted_docs += 1
                        item["selected_chunk_ids"].append(str(first.id))
                        item["decision"] = "context"
                        item["reason"] = "selected"
                    else:
                        item["reason"] = "context_character_limit"
            candidates.append(item)
        # A second pass includes the procedural sibling of each accepted doc.
        for item in candidates:
            if item["decision"] != "context":
                continue
            siblings = self._siblings(item["document_id"])
            useful = [p for p in siblings if _norm(str((p.payload or {}).get("section") or ""))
                      not in SKIP_SECTIONS and str(p.id) not in item["selected_chunk_ids"]]
            for point in useful[:MAX_CHUNKS_PER_DOCUMENT - 1]:
                text = str(point.payload.get("text") or "")[:MAX_FRAGMENT_CHARS]
                if text and used_chars + len(text) <= MAX_CONTEXT_CHARS:
                    context.append(self._fragment(point, item, text))
                    used_chars += len(text)
                    item["selected_chunk_ids"].append(str(point.id))
        for item in candidates:
            item["chunk_decisions"] = []
            for point in self._siblings(item["document_id"]):
                section = _norm(str((point.payload or {}).get("section") or ""))
                if str(point.id) in item["selected_chunk_ids"]:
                    reason = "selected"
                elif section in SKIP_SECTIONS:
                    reason = "question_or_symptom_section"
                elif item["decision"] != "context":
                    reason = item["reason"]
                elif len(item["selected_chunk_ids"]) >= MAX_CHUNKS_PER_DOCUMENT:
                    reason = "chunk_limit"
                else:
                    reason = "context_character_limit"
                item["chunk_decisions"].append({"id": str(point.id),
                                                "section": (point.payload or {}).get("section"),
                                                "reason": reason})
        trace = {"input_question": task_messages[-1] if task_messages else "",
                 "task_messages": list(task_messages), "search_query": query,
                 "query_origin": query_origin, "strategy": strategy,
                 "candidate_retrieval_ms": candidate_retrieval_ms,
                 "retrieval_ms": round((time.perf_counter() - start) * 1000),
                 "approved_filter": {"status": "approved", "excluded_points_by_status":
                                     self.receipt["points"] - self.receipt["approved_points"]},
                 "dense_raw_candidates": [{"chunk_id": str(p.id),
                                        "document_id": str((p.payload or {}).get("document_id") or ""),
                                        "rank": i, "score": float(p.score)}
                                       for i, p in enumerate(dense, 1)],
                 "hybrid_raw_candidates": raw_hits,
                 "candidates": candidates,
                 "context": context, "context_document_ids": list(dict.fromkeys(
                     c["document_id"] for c in context)),
                 "context_chars": used_chars}
        return context, trace

    @staticmethod
    def _fragment(point, rank: dict, text: str):
        x = point.payload or {}
        return {"id": str(point.id), "document_id": str(x.get("document_id") or ""),
                "title": x.get("title"), "section": x.get("section"),
                "service": x.get("service"), "model": x.get("model"),
                "operations": x.get("operations"), "status": x.get("status"),
                "text": text, "score": round(rank["score"], 6)}

    def search(self, query: str, task_messages: list[str] | None = None):
        return self.search_with_trace(query, task_messages or [query])[0]
