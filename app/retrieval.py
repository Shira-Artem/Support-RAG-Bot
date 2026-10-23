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
              "касса": ["ккт"], "ккт": ["касса"], "найти": ["поиск"],
              "сотрудника": ["пользователя"], "добавить": ["добавление", "создать"]}
FILTER_FIELDS = {"category", "manufacturer", "model", "version", "source_type", "document_id"}
_ERROR_CODE = re.compile(
    r"\b(?:(?:ошибк\w*|код\w*)\s*(?:фн|флк|ккт)?|(?:фн|флк))"
    r"\s*[:№#-]?\s*(-?\d{2,5})\b",
    re.I,
)
_TECHNICAL_VERSION = re.compile(r"\b(?:ффд)\s*(\d+(?:[.,]\d+)?)\b", re.I)


def tokens(text: str) -> list[str]:
    return [item for item in re.findall(r"[a-zа-яё0-9]+(?:[.,][0-9]+)?", text.lower().replace("ё", "е"))
            if item not in STOP and (len(item) > 1 or item.isdigit())]


def lexical_token(word: str) -> str:
    # Small lexical normalization only; exact codes/models still use tokens().
    if re.fullmatch(r'чек[а-я]*', word):
        return 'чек'
    return word[:5] if len(word) > 5 and re.fullmatch(r'[а-я]+', word) else word


def error_codes(text: str) -> set[str]:
    codes = set()
    for match in _ERROR_CODE.finditer(text):
        # «номер ФН 123...» identifies a particular fiscal drive/document; it
        # is not error code 123 and therefore is not an exact retrieval guard.
        if re.search(r"номер\s+$", text[max(0, match.start() - 12):match.start()], re.I):
            continue
        codes.add(match.group(1).lstrip("-").replace(",", "."))
    return codes


def exact_identifiers(text: str) -> set[str]:
    """Extract only identifiers whose mismatch changes the technical answer.

    Plain numbers are intentionally excluded: quantities, money, dates and
    document numbers improve lexical ranking but must not remove a relevant
    procedure that does not repeat the client's values.
    """
    identifiers = error_codes(text)
    identifiers.update(match.group(1).replace(",", ".")
                       for match in _TECHNICAL_VERSION.finditer(text))
    return identifiers


def _normalize_model(value: str) -> str:
    normalized = []
    for token in tokens(value.replace("-", " ")):
        if token.startswith("эвотор"):
            token = "эвотор"
        elif token.startswith("атол"):
            token = "атол"
        normalized.append(token)
    return " ".join(normalized)


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

    def search(self, query: str, top_k: int = 5, filters: dict | None = None,
               source_prefixes: tuple[str, ...] | None = None) -> list[Hit]:
        query = query.strip()
        if not query or top_k < 1 or top_k > 100 or len(query) > 500:
            raise ValueError("query must contain 1-500 characters and top_k must be 1-100")
        filters = filters or {}
        if set(filters) - FILTER_FIELDS or any(not isinstance(value, str) or not value.strip() for value in filters.values()):
            raise ValueError("Unsupported or empty metadata filter")
        conditions = [models.FieldCondition(key=key, match=models.MatchValue(value=value)) for key, value in filters.items()]
        if not self.demo:
            conditions.append(models.FieldCondition(key="status", match=models.MatchValue(value="approved")))
        points = [point for point in self.store.all_points() if self._allowed(point.payload, filters)]
        if source_prefixes:
            points = [point for point in points if str(point.payload.get('source', '')).replace('\\', '/').removeprefix('data/knowledge/').startswith(source_prefixes)]
            conditions.append(models.HasIdCondition(has_id=[point.id for point in points]))
        qfilter = models.Filter(must=conditions) if conditions else None
        if not points:
            return []
        dense = self.store.semantic(query, min(max(top_k * 8, 30), 100), qfilter)
        dense_scores = {str(point.id): float(point.score) for point in dense}
        # Numbered Telegram test questions are not error codes. Keep numbers
        # inside the actual task (ФН 235, ФФД 1.2) subject to the exact guard.
        lexical_query = re.sub(r'(^|запрос клиента:\s*)\d{1,2}[.)]\s+',
                               lambda match: match.group(1), query, flags=re.I)
        query_tokens = tokens(lexical_query)
        expanded = query_tokens + [syn for token in query_tokens for syn in EXPANSIONS.get(token, [])]
        query_counts = Counter(lexical_token(word) for word in expanded)
        corpus = [Counter(lexical_token(word) for word in tokens(point.payload["text"] + ' ' + str(point.payload.get('title') or ''))) for point in points]
        df = Counter(token for counts in corpus for token in counts)
        avgdl = sum(sum(counts.values()) for counts in corpus) / len(corpus) or 1
        required_identifiers = exact_identifiers(lexical_query)
        required_error_codes = error_codes(lexical_query)
        brands = set(_normalize_model(query).split()) & {
            "атол", "штрих", "эвотор", "1с", "aqsi", "акси",
        }
        normalized_query = _normalize_model(query)
        known_models = sorted({
            _normalize_model(str(point.payload.get("model") or ""))
            for point in points if point.payload.get("model")
        }, key=len, reverse=True)
        requested_model = next((model for model in known_models
                                if re.search(rf"(?:^|\s){re.escape(model)}(?:$|\s)", normalized_query)), None)
        scored = []
        for point, counts in zip(points, corpus, strict=True):
            text = point.payload["text"]
            point_model = _normalize_model(str(point.payload.get("model") or ""))
            if requested_model and point_model != requested_model:
                continue
            brand_text = " ".join((text, str(point.payload.get("title") or ""),
                                   str(point.payload.get("manufacturer") or ""), point_model))
            if brands and not brands.issubset(set(tokens(brand_text))):
                continue
            # Technical numeric codes and model numbers must match exactly.
            section = point.payload.get("section") or ""
            code_text = text
            if text.startswith(section + "\n") and len({token for token in tokens(section) if any(c.isdigit() for c in token)}) > 1:
                code_text = text[len(section) + 1:]
            title = str(point.payload.get('title') or '')
            # A section of a dedicated error article inherits its title's code.
            # A multi-code reference does not: it must match in this chunk.
            title_codes = {
                match.group(1).lstrip("-") for match in _ERROR_CODE.finditer(title)
            }
            if required_error_codes and len(title_codes) == 1 and title_codes <= required_error_codes:
                code_text += ' ' + title
            identifier_text = " ".join((code_text, str(point.payload.get("model") or ""),
                                         str(point.payload.get("version") or "")))
            if required_identifiers and not required_identifiers.issubset(
                    {token.replace(",", ".") for token in tokens(identifier_text)}):
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
            score = (2 / (60 + lexical_rank[point_id]) if point_id in lexical_rank else 0) + (1 / (60 + dense_rank[point_id]) if point_id in dense_rank else 0)
            hits.append(Hit(point.payload["text"], round(score, 6), semantic, round(bm25, 5) if bm25 else None,
                            {k: v for k, v in point.payload.items() if k != "text"}))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:top_k]

    def _allowed(self, payload: dict, filters: dict) -> bool:
        return (self.demo or payload.get("status") == "approved") and all(payload.get(key) == value for key, value in filters.items())
