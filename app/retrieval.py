"""BM25 + dense retrieval with conservative abstention and exact-code guards."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re

from qdrant_client import models

from app.vector_store import QdrantStore


STOP = {"и", "в", "на", "по", "с", "не", "как", "что", "у", "для", "а", "или", "это", "мне", "из", "при", "ли", "the"}
EXPANSIONS = {"пробивает": ["печать", "фискального", "документа"], "пробить": ["печать", "чек"],
              "чеки": ["чек", "документы"], "уходят": ["передача", "отправка"],
              "касса": ["ккт"], "ккт": ["касса"]}
FILTER_FIELDS = {"category", "manufacturer", "model", "version", "source_type", "document_id"}


def tokens(text: str) -> list[str]:
    return [item for item in re.findall(r"[a-zа-яё0-9]+", text.lower().replace("ё", "е")) if item not in STOP and len(item) > 1]


@dataclass(frozen=True)
class Hit:
    text: str
    score: float
    semantic_score: float | None
    lexical_score: float | None
    metadata: dict


class Retriever:
    def __init__(self, store: QdrantStore, *, demo: bool = False, min_semantic_score: float = 0.75):
        self.store = store
        self.demo = demo
        self.min_semantic_score = min_semantic_score

    def search(self, query: str, top_k: int = 5, filters: dict | None = None) -> list[Hit]:
        query = query.strip()
        if not query or top_k < 1 or top_k > 20 or len(query) > 500:
            raise ValueError("query must contain 1-500 characters and top_k must be 1-20")
        filters = filters or {}
        if set(filters) - FILTER_FIELDS or any(not isinstance(value, str) or not value.strip() for value in filters.values()):
            raise ValueError("Unsupported or empty metadata filter")
        conditions = [models.FieldCondition(key=key, match=models.MatchValue(value=value)) for key, value in filters.items()]
        if not self.demo:
            conditions.append(models.FieldCondition(key="status", match=models.MatchValue(value="approved")))
        qfilter = models.Filter(must=conditions) if conditions else None
        points = [point for point in self.store.all_points() if self._allowed(point.payload, filters)]
        if not points:
            return []
        dense = self.store.semantic(query, min(max(top_k * 8, 30), 100), qfilter)
        dense_scores = {str(point.id): float(point.score) for point in dense}
        query_tokens = tokens(query)
        expanded = query_tokens + [syn for token in query_tokens for syn in EXPANSIONS.get(token, [])]
        query_counts = Counter(expanded)
        corpus = [Counter(tokens(point.payload["text"])) for point in points]
        df = Counter(token for counts in corpus for token in counts)
        avgdl = sum(sum(counts.values()) for counts in corpus) / len(corpus) or 1
        codes = {token for token in query_tokens if any(char.isdigit() for char in token)}
        scored = []
        for point, counts in zip(points, corpus, strict=True):
            text = point.payload["text"]
            # Technical numeric codes and model numbers must match exactly.
            section = point.payload.get("section") or ""
            code_text = text
            if text.startswith(section + "\n") and len({token for token in tokens(section) if any(c.isdigit() for c in token)}) > 1:
                code_text = text[len(section) + 1:]
            if codes and not codes.issubset(set(tokens(code_text + " " + str(point.payload.get("model") or "")))):
                continue
            dl = sum(counts.values())
            bm25 = 0.0
            for token, qfreq in query_counts.items():
                freq = counts[token]
                if not freq:
                    continue
                idf = math.log(1 + (len(points) - df[token] + 0.5) / (df[token] + 0.5))
                bm25 += idf * freq * 2.2 / (freq + 1.2 * (0.25 + 0.75 * dl / avgdl)) * min(qfreq, 2)
            semantic = dense_scores.get(str(point.id))
            if bm25 <= 0 and (semantic is None or semantic < self.min_semantic_score):
                continue
            scored.append((point, bm25, semantic))
        if not scored:
            return []
        lexical_rank = {str(item[0].id): i for i, item in enumerate(sorted(scored, key=lambda item: item[1], reverse=True)) if item[1] > 0}
        dense_rank = {str(point.id): i for i, point in enumerate(dense)}
        hits = []
        for point, bm25, semantic in scored:
            point_id = str(point.id)
            score = (1 / (60 + lexical_rank[point_id]) if point_id in lexical_rank else 0) + (1 / (60 + dense_rank[point_id]) if point_id in dense_rank else 0)
            hits.append(Hit(point.payload["text"], round(score, 6), semantic, round(bm25, 5) if bm25 else None,
                            {k: v for k, v in point.payload.items() if k != "text"}))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:top_k]

    def _allowed(self, payload: dict, filters: dict) -> bool:
        return (self.demo or payload.get("status") == "approved") and all(payload.get(key) == value for key, value in filters.items())
