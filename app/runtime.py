"""Shared construction for indexer, API, CLI and optional bot integration."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient

from app.embeddings import SentenceTransformerEmbedding
from app.retrieval import Retriever
from app.vector_store import QdrantStore


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def build_store(*, demo: bool = False) -> QdrantStore:
    model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    embedding = SentenceTransformerEmbedding(model)
    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), timeout=15)
    collection = os.getenv("QDRANT_COLLECTION", "knowledge_demo" if demo else "knowledge_v1")
    return QdrantStore(client, embedding, collection)


def build_retriever(*, demo: bool | None = None) -> Retriever:
    if demo is None:
        demo = os.getenv("RAG_DEMO_MODE", "0") == "1"
    return Retriever(build_store(demo=demo), demo=demo)
