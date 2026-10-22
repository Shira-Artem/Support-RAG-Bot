"""Compare real hybrid retrieval on CURRENT and a cloned, patched STAGING.

No generator, Telegram or SQLite imports/calls. Never indexes CURRENT.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path

from qdrant_client import QdrantClient, models

from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueManager, DialogueState
from app.embeddings import SentenceTransformerEmbedding
from app.knowledge import DocumentLoader
from app.rag_query import QueryNeedsClarification, build_rag_query
from app.retrieval import Retriever
from app.vector_store import QdrantStore


def read_points(client, collection, *, vectors=False):
    points, offset = [], None
    while True:
        batch, offset = client.scroll(collection, offset=offset, limit=256,
                                      with_payload=True, with_vectors=vectors)
        points.extend(batch)
        if offset is None:
            return points


def fingerprint(points):
    values = sorted(({'id': str(p.id), 'payload': p.payload} for p in points), key=lambda x: x['id'])
    return sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staging-collection', required=True)
    parser.add_argument('--create-staging', action='store_true', help='Create a NEW clone; refuses existing collections')
    parser.add_argument('--clone-collection', help='Read-only source for a new STAGING; defaults to CURRENT')
    parser.add_argument('--baseline-report', type=Path, help='Attach per-case deltas against a previous comparison')
    parser.add_argument('--current-collection', default=os.getenv('QDRANT_COLLECTION', 'knowledge_demo'))
    parser.add_argument('--manifest', type=Path, default=Path('docs/knowledge-sprint-v1/manifest.json'))
    parser.add_argument('--cases', type=Path, default=Path('docs/knowledge-sprint-v1/cases.json'))
    parser.add_argument('--output', type=Path, default=Path('docs/knowledge-sprint-v1/retrieval.json'))
    args = parser.parse_args()
    active = os.getenv('QDRANT_COLLECTION', 'knowledge_demo')
    if args.staging_collection in {args.current_collection, active, 'knowledge_demo', 'knowledge_v1'}:
        parser.error('STAGING must differ from CURRENT and reserved working collections')
    if not args.staging_collection.startswith('knowledge_sprint_v1_'):
        parser.error('Use a dedicated knowledge_sprint_v1_ collection name')

    client = QdrantClient(url=os.getenv('QDRANT_URL', 'http://127.0.0.1:6333'), timeout=30)
    before = read_points(client, args.current_collection, vectors=args.create_staging)
    before_hash = fingerprint(before)
    info = client.get_collection(args.current_collection)
    clone_name = args.clone_collection or args.current_collection
    if args.clone_collection and not args.create_staging:
        parser.error('--clone-collection requires --create-staging')
    if clone_name == args.staging_collection:
        parser.error('Cannot clone a collection onto itself')
    clone_points = (read_points(client, clone_name, vectors=True) if clone_name != args.current_collection
                    and args.create_staging else before)
    clone_hash = fingerprint(clone_points)
    model = os.getenv('EMBEDDING_MODEL', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    embedding = SentenceTransformerEmbedding(model)
    if embedding.dimension != info.config.params.vectors.size:
        raise ValueError('Embedding dimension differs from CURRENT')

    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    loader = DocumentLoader(Path('data/knowledge'))
    documents = [loader.load(loader.root / item['path']) for item in manifest if item.get('path')]
    for item, doc in zip((i for i in manifest if i.get('path')), documents, strict=True):
        if doc.document_id != item['document_id'] or doc.status != item['proposed_status']:
            raise ValueError('Card differs from manifest')
    stats = None
    if args.create_staging:
        if client.collection_exists(args.staging_collection):
            parser.error('STAGING already exists; use another name or omit --create-staging for read-only comparison')
        client.create_collection(args.staging_collection, vectors_config=info.config.params.vectors)
        for start in range(0, len(clone_points), 128):
            client.upsert(args.staging_collection, points=[models.PointStruct(id=p.id, payload=p.payload, vector=p.vector)
                          for p in clone_points[start:start+128]], wait=True)
        if fingerprint(read_points(client, args.staging_collection)) != clone_hash:
            raise RuntimeError('Clone payload verification failed')
        staging = QdrantStore(client, embedding, args.staging_collection)
        stats = staging.index(documents, remove_missing=False)
    if not client.collection_exists(args.staging_collection):
        parser.error('STAGING does not exist; specify --create-staging')
    stores = {label: QdrantStore(client, embedding, name) for label, name in
              [('CURRENT', args.current_collection), ('STAGING', args.staging_collection)]}
    adapters = {label: RetrieverRAGAdapter(Retriever(store, demo=True)) for label, store in stores.items()}
    # Reuse each backend's candidate results between the raw-rank trace and pipeline.
    for adapter in adapters.values():
        original = adapter.search
        cache = {}
        def cached(query, top_k=5, original=original, cache=cache):
            key = (query, top_k)
            if key not in cache:
                cache[key] = original(query, top_k)
            return cache[key]
        adapter.search = cached

    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    baseline = (json.loads(args.baseline_report.read_text(encoding='utf-8')) if args.baseline_report else None)
    previous_rows = {str(row['id']): row for row in baseline['rows']} if baseline else {}
    manager, states, rows = DialogueManager(), {}, []
    for case in cases:
        state = manager.advance(states.get(case['conversation'], DialogueState()), case['message'], case['id'])
        states[case['conversation']] = state
        try:
            query = build_rag_query(state)
        except QueryNeedsClarification as exc:
            rows.append({**case, 'state': state.to_dict(), 'query': None, 'query_error': str(exc)})
            continue
        row = {**case, 'state': state.to_dict(), 'query': query, 'collections': {}}
        for label, adapter in adapters.items():
            raw = adapter.search(query, top_k=adapter.pipeline.candidate_k)
            result = adapter.search_for_state(state, query)
            trace = result.diagnostics()
            ranked = []
            for hit in raw:
                if hit.metadata.get('document_id') in {x['document_id'] for x in ranked}:
                    continue
                ranked.append(dict(document_id=hit.metadata.get('document_id'), source=hit.source,
                                   rrf=hit.score, dense=hit.semantic_score, bm25=hit.lexical_score))
            selected = list(dict.fromkeys(hit.metadata.get('document_id') for hit in result.documents))
            # Keep enough evidence for review without duplicating every rejected row.
            evaluations = {x['document_id']: x for x in trace['candidates']}
            for hit in ranked[:10]:
                evaluation = evaluations.get(hit['document_id'])
                if evaluation:
                    hit.update(rejection_reasons=evaluation['reasons'], selected=evaluation['selected'],
                               task_category=evaluation['metadata'].get('task_category'))
            row['collections'][label] = dict(top_candidates=ranked[:10], chosen_document=selected[0] if selected else None,
                selected_documents=selected, sufficient_evidence=result.sufficient,
                rejection_counts=dict(Counter(reason for item in result.rejected for reason in item.reasons)),
                selected=trace['selected'], rejected=[dict(document_id=x.document_id, source=x.source,
                    task_category=x.metadata.get('task_category'), reasons=x.reasons) for x in result.rejected],
                insufficiency_reason=result.insufficiency_reason, context=result.context)
            row['collections'][label].update(evidence_status=result.evidence_status,
                missing_evidence=result.missing_evidence, supported_steps=result.supported_steps)
            previous = previous_rows.get(str(case['id']), {}).get('collections', {}).get(label)
            if previous:
                data = row['collections'][label]
                prior_rejected = {x['document_id']: x['reasons'] for x in previous['rejected']}
                now_rejected = {x['document_id']: x['reasons'] for x in data['rejected']}
                data['change_from_previous'] = dict(
                    previous_chosen=previous['chosen_document'], current_chosen=data['chosen_document'],
                    previous_sufficient=previous['sufficient_evidence'], current_sufficient=data['sufficient_evidence'],
                    added_selected=sorted(set(selected)-set(previous['selected_documents'])),
                    removed_selected=sorted(set(previous['selected_documents'])-set(selected)),
                    changed_rejections={doc:dict(before=prior_rejected.get(doc),after=now_rejected.get(doc))
                        for doc in sorted(prior_rejected.keys() | now_rejected.keys())
                        if prior_rejected.get(doc)!=now_rejected.get(doc)})
        rows.append(row)
        print(f"case={case['id']} operation={state.operation} " + ' '.join(
            f"{label}={data['chosen_document']} sufficient={data['sufficient_evidence']}"
            for label, data in row['collections'].items()), flush=True)

    after_hash = fingerprint(read_points(client, args.current_collection))
    if after_hash != before_hash:
        raise RuntimeError('CURRENT changed during comparison; investigate external indexing')
    if args.clone_collection and fingerprint(read_points(client, clone_name)) != clone_hash:
        raise RuntimeError('Source STAGING changed during comparison')
    report = dict(embedding_model=model, dense_retrieval=True, llm_calls=0,
        method='Client-only state replay; no generated assistant turns. sufficient_evidence is the existing pipeline flag, not a human verdict.',
        current_collection=args.current_collection, staging_collection=args.staging_collection,
        current_payload_hash_before=before_hash,current_payload_hash_after=after_hash,
        current_documents=len({p.payload['document_id'] for p in before}),current_chunks=len(before),
        staging_chunks=client.get_collection(args.staging_collection).points_count,
        staging_documents=len({p.payload['document_id'] for p in read_points(client,args.staging_collection)}),
        overlay_stats=stats,rows=rows)
    report.update(clone_collection=clone_name if args.create_staging else None,
                  clone_payload_hash=clone_hash if args.create_staging else None,
                  baseline_report=str(args.baseline_report) if args.baseline_report else None)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
