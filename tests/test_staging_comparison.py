import json
import sys

import pytest
from qdrant_client import QdrantClient

from app.knowledge import DocumentLoader
from app.vector_store import QdrantStore
from scripts import compare_knowledge_staging as comparison


class Embedding:
    dimension = 2

    def __init__(self, *args):
        pass

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def test_staging_clones_and_overlays_without_removing_unrelated_documents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('QDRANT_COLLECTION', raising=False)
    root = tmp_path / 'data/knowledge'
    root.mkdir(parents=True)
    path = root / 'guide.md'
    path.write_text('---\ndocument_id: guide\n---\nOld instruction.', encoding='utf-8')
    unrelated = root / 'other.md'
    unrelated.write_text('---\ndocument_id: other\n---\nOther instruction.', encoding='utf-8')
    client = QdrantClient(':memory:')
    current = QdrantStore(client, Embedding(), 'knowledge_demo')
    current.index(DocumentLoader(root).load_all())
    before = comparison.fingerprint(current.all_points())
    vectors = comparison.read_points(client, 'knowledge_demo', vectors=True)
    path.write_text('---\ndocument_id: guide\nservice: Example\noperations: [inspect]\n---\nUpdated instruction.', encoding='utf-8')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps([dict(path='guide.md', document_id='guide', proposed_status='draft')]), encoding='utf-8')
    cases = tmp_path / 'cases.json'
    cases.write_text('[]', encoding='utf-8')
    output = tmp_path / 'out.json'
    monkeypatch.setattr(comparison, 'QdrantClient', lambda **kwargs: client)
    monkeypatch.setattr(comparison, 'SentenceTransformerEmbedding', Embedding)
    args = ['compare', '--staging-collection', 'knowledge_sprint_v1_test', '--create-staging',
            '--manifest', str(manifest), '--cases', str(cases), '--output', str(output)]
    monkeypatch.setattr(sys, 'argv', args)
    comparison.main()
    assert comparison.fingerprint(current.all_points()) == before
    assert comparison.read_points(client, 'knowledge_demo', vectors=True) == vectors
    staged = comparison.read_points(client, 'knowledge_sprint_v1_test')
    assert {p.payload['document_id'] for p in staged} == {'guide', 'other'}
    assert next(p for p in staged if p.payload['document_id'] == 'guide').payload['service'] == 'Example'
    # Existing staging and production names are rejected before mutations.
    with pytest.raises(SystemExit):
        comparison.main()
    monkeypatch.setattr(sys, 'argv', ['compare', '--staging-collection', 'knowledge_demo'])
    with pytest.raises(SystemExit):
        comparison.main()
