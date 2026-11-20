"""Read-only health and KB identity check; no Telegram polling or Qdrant writes."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.knowledge import DocumentLoader, Chunker
from qdrant_client import QdrantClient


def check():
    receipt = json.loads((ROOT/'.local/kb-integration-20261119/manual/runtime.json').read_text(encoding='utf-8'))
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    docs = DocumentLoader(ROOT/'data/knowledge').load_all()
    expected = {c.id: {**c.metadata, 'text': c.text} for d in docs if d.status=='approved' for c in Chunker().split(d)}
    client = QdrantClient(url='http://127.0.0.1:6333')
    try:
        info = client.get_collection(receipt['collection'])
        actual, offset = {}, None
        while True:
            points, offset = client.scroll(receipt['collection'], limit=256, offset=offset, with_payload=True, with_vectors=False)
            actual.update({str(p.id): p.payload for p in points})
            if offset is None: break
        collections = [{ 'name': c.name, 'points': client.get_collection(c.name).points_count }
            for c in client.get_collections().collections if c.name in {
                receipt['collection'], 'knowledge_kb_b2_base_20261119', 'knowledge_stage3_retrieval_20261022'}]
    finally:
        client.close()
    events = [json.loads(line) for line in (ROOT/'.local/kb-integration-20261119/manual/telegram-http.jsonl').read_text().splitlines()]
    last = {}
    for e in events:
        last[e['method']] = e
    mismatches = [path for path,h in receipt['source_sha256'].items() if sha256((ROOT/path).read_bytes()).hexdigest()!=h]
    result = dict(checked_at=datetime.now(timezone.utc).isoformat(), head=git('rev-parse','HEAD'),
        branch=git('branch','--show-current'), origin_main_cached=git('rev-parse','origin/main'),
        feature=git('rev-parse','origin/feature/kb-review-b2'),
        feature_is_ancestor=subprocess.run(['git','merge-base','--is-ancestor','origin/feature/kb-review-b2','HEAD'],cwd=ROOT).returncode==0,
        runtime={k:receipt[k] for k in ('pid','started_at','commit','collection','points','provider','model','reasoning_effort','rag_engine','semantic_composer_enabled','ai_coordinator_enabled','handoff_enabled')},
        runtime_source_mismatches=mismatches, source_file_count=len(receipt['source_sha256']),
        kb=dict(approved=sum(d.status=='approved' for d in docs),draft=sum(d.status=='draft' for d in docs),
            expected_points=len(expected),actual_points=len(actual),status=str(info.status),exact_payload_match=expected==actual),
        collections=collections, latest_transport=last,
        limitations=['Cached origin/main is not a fresh remote ref proof.', 'No getUpdates call was made by this check.',
            'Process liveness is verified separately via Windows process inventory.'])
    return result


if __name__=='__main__':
    result=check()
    out=ROOT/'reports/manual_checkpoint_20261120/runtime_before.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('head','feature_is_ancestor','runtime_source_mismatches','kb')}))
