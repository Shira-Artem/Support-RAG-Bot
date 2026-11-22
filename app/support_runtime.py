"""Build the established RAG pipeline without importing or starting a bot."""
import logging
import os
from types import SimpleNamespace
from app.config import get_settings
from app.compat import build_answer_rag
from app.answer_service import AnswerService
from app.source_first_service import SourceFirstService


def build_support_runtime(store):
    settings = get_settings(require_telegram_allowlist=False)
    if settings.rag_engine != 'source_first':
        raise RuntimeError('CRM API requires the configured source_first pipeline')
    from qdrant_client import QdrantClient
    client = QdrantClient(url=os.getenv('QDRANT_URL', 'http://127.0.0.1:6333'), timeout=5)
    try:
        collection = os.environ['QDRANT_COLLECTION']
        if not client.collection_exists(collection) or not client.get_collection(collection).points_count:
            raise RuntimeError('Reviewed collection missing/empty; refusing to create an index')
    finally:
        client.close()
    rag = build_answer_rag(settings.docs_dir)
    return SimpleNamespace(settings=settings, conversations=store,
        answer_service=AnswerService(rag, settings),
        source_first_service=SourceFirstService(rag, settings, settings.docs_dir.parent.parent),
        logger=logging.getLogger('support.api'))
