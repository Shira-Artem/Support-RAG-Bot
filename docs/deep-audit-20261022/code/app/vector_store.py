"""Qdrant-backed, repeatable chunk indexing."""
from __future__ import annotations

from qdrant_client import QdrantClient, models

from app.embeddings import EmbeddingProvider
from app.knowledge import Chunker, Document


class QdrantStore:
    def __init__(self, client: QdrantClient, embedding: EmbeddingProvider, collection: str = "knowledge"):
        self.client = client
        self.embedding = embedding
        self.collection = collection
        if not client.collection_exists(collection):
            client.create_collection(collection, vectors_config=models.VectorParams(size=embedding.dimension, distance=models.Distance.COSINE))
        else:
            size = client.get_collection(collection).config.params.vectors.size
            if size != embedding.dimension:
                raise ValueError(f"Embedding dimension {embedding.dimension} differs from collection dimension {size}; use a new collection")

    def all_points(self) -> list:
        result = []
        offset = None
        while True:
            batch, offset = self.client.scroll(self.collection, offset=offset, limit=256, with_payload=True, with_vectors=False)
            result.extend(batch)
            if offset is None:
                return result

    def index(self, documents: list[Document], *, remove_missing: bool = False) -> dict[str, int]:
        existing = self.all_points()
        by_document: dict[str, list] = {}
        for point in existing:
            by_document.setdefault(point.payload["document_id"], []).append(point)
        stats = {"indexed": 0, "unchanged": 0, "removed": 0}
        seen = set()
        chunker = Chunker()
        for document in documents:
            if document.document_id in seen:
                raise ValueError(f"Duplicate document_id: {document.document_id}")
            seen.add(document.document_id)
            chunks = chunker.split(document)
            old = by_document.get(document.document_id, [])
            desired = {chunk.id for chunk in chunks}
            desired_payloads = {chunk.id: {**chunk.metadata, "text": chunk.text} for chunk in chunks}
            if len(old) == len(chunks) and all(
                point.id in desired and point.payload == desired_payloads[point.id]
                for point in old
            ):
                stats["unchanged"] += 1
                continue
            if chunks:
                vectors = self.embedding.embed([chunk.text for chunk in chunks])
                self.client.upsert(self.collection, points=[
                    models.PointStruct(id=chunk.id, vector=vector, payload={**chunk.metadata, "text": chunk.text})
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ], wait=True)
            stale = [point.id for point in old if point.id not in desired]
            if stale:
                self.client.delete(self.collection, points_selector=models.PointIdsList(points=stale), wait=True)
                stats["removed"] += len(stale)
            stats["indexed"] += 1
        if remove_missing:
            stale = [point.id for point in existing if point.payload["document_id"] not in seen]
            if stale:
                self.client.delete(self.collection, points_selector=models.PointIdsList(points=stale), wait=True)
                stats["removed"] += len(stale)
        return stats

    def semantic(self, query: str, limit: int, query_filter: models.Filter | None = None) -> list:
        vector = self.embedding.embed([query])[0]
        return self.client.query_points(self.collection, query=vector, limit=limit, query_filter=query_filter, with_payload=True).points
