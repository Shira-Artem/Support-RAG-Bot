from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import math
import re
from typing import Iterable

SUPPORTED_EXTENSIONS = {".txt", ".md"}


@dataclass
class Chunk:
    id: str
    source: str
    text: str
    vector: Counter[str]
    norm: float


@dataclass
class SearchResult:
    source: str
    text: str
    score: float


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_into_chunks(text: str, max_chars: int = 1300, overlap: int = 180) -> list[str]:
    text = _clean_text(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph) <= max_chars:
            current = paragraph
        else:
            start = 0
            while start < len(paragraph):
                end = start + max_chars
                chunks.append(paragraph[start:end].strip())
                if end >= len(paragraph):
                    break
                start = max(0, end - overlap)

    if current:
        chunks.append(current)

    return chunks


def _normalize_for_search(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _char_ngrams(text: str, min_n: int = 3, max_n: int = 5) -> Counter[str]:
    text = _normalize_for_search(text)
    if not text:
        return Counter()

    padded_words = [f" {word} " for word in text.split() if word]
    grams: Counter[str] = Counter()

    for word in padded_words:
        for n in range(min_n, max_n + 1):
            if len(word) < n:
                continue
            for i in range(0, len(word) - n + 1):
                grams[word[i : i + n]] += 1

    return grams


def _norm(vector: Counter[str]) -> float:
    return math.sqrt(sum(value * value for value in vector.values()))


def _cosine(left: Counter[str], left_norm: float, right: Counter[str], right_norm: float) -> float:
    if not left or not right or left_norm == 0 or right_norm == 0:
        return 0.0

    if len(left) > len(right):
        left, right = right, left
        left_norm, right_norm = right_norm, left_norm

    dot = sum(value * right.get(key, 0) for key, value in left.items())
    return dot / (left_norm * right_norm)


class SimpleRAG:
    def __init__(self, docs_dir: Path):
        self.docs_dir = docs_dir
        self.chunks: list[Chunk] = []
        self.reload()

    def reload(self) -> None:
        self.chunks = self._load_chunks()

    def _load_chunks(self) -> list[Chunk]:
        docs: list[Chunk] = []

        if not self.docs_dir.exists():
            return docs

        for path in sorted(self.docs_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")

            for i, chunk_text in enumerate(_split_into_chunks(text)):
                rel = path.relative_to(self.docs_dir).as_posix()
                vector = _char_ngrams(chunk_text)

                docs.append(
                    Chunk(
                        id=f"{rel}:{i + 1}",
                        source=rel,
                        text=chunk_text,
                        vector=vector,
                        norm=_norm(vector),
                    )
                )

        return docs

    def search(self, query: str, top_k: int = 5, min_score: float = 0.03) -> list[SearchResult]:
        query = query.strip()

        if not query or not self.chunks or top_k <= 0:
            return []

        query_vector = _char_ngrams(query)
        query_norm = _norm(query_vector)

        scored: list[tuple[float, Chunk]] = []

        for chunk in self.chunks:
            score = _cosine(query_vector, query_norm, chunk.vector, chunk.norm)
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)

        results: list[SearchResult] = []

        for score, chunk in scored[: top_k * 3]:
            if score < min_score:
                continue

            results.append(
                SearchResult(
                    source=chunk.source,
                    text=chunk.text,
                    score=float(score),
                )
            )

            if len(results) >= top_k:
                break

        return results

    def build_context(self, results: Iterable[SearchResult]) -> str:
        blocks = []

        for i, item in enumerate(results, 1):
            blocks.append(
                f"[Источник {i}: {item.source}; score={item.score:.3f}]\n{item.text}"
            )

        return "\n\n---\n\n".join(blocks)

    def list_sources(self) -> list[str]:
        if not self.docs_dir.exists():
            return []

        return [
            path.relative_to(self.docs_dir).as_posix()
            for path in sorted(self.docs_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
