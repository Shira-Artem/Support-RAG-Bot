"""Read-only source/KB/SQLite/Stage3 verification and complete run inventory."""
from collections import Counter
import hashlib
import itertools
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
DEST=ROOT/'reports/b2_2d_20261105'

def main():
    from dotenv import load_dotenv
    from qdrant_client import QdrantClient
    load_dotenv(ROOT/'.env',override=False)
    before=json.loads((DEST/'protected_before.json').read_text(encoding='utf-8'))
    changed=[p for p,h in before.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    assert not [p for p in changed if p!='.env'],changed
    current={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'bot.py',*sorted((ROOT/'app').glob('*.py'))]}
    client=QdrantClient(url=os.getenv('QDRANT_URL','http://127.0.0.1:6333'),timeout=20)
    collection='knowledge_stage3_retrieval_20261022'; info=client.get_collection(collection)
    points=[];offset=None
    while True:
        batch,offset=client.scroll(collection,offset=offset,limit=256,with_payload=True,with_vectors=False)
        points.extend(batch)
        if offset is None: break
    assert len(points)==934 and str(info.status)=='green'
    old=json.loads((ROOT/'reports/b2_2c_20261104/stage3_inventory.json').read_text(encoding='utf-8'))
    by_source={}
    for p in points:
        m=p.payload;s=m['source'];item=by_source.setdefault(s,dict(status=m.get('status'),document_id=m.get('document_id'),model=m.get('model'),chunks=0,content_hash=m.get('content_hash')));item['chunks']+=1
    assert by_source==old['sources'],'Stage3 source/metadata/content-hash inventory changed'
    # Preserve a clearly specified canonical full-payload digest. Also test
    # historical serializations without claiming equality if unknown.
    payloads=[p.payload for p in points]
    digest=hashlib.sha256(json.dumps(payloads,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    matches=[]
    forms={'payloads':payloads,'id_payload':[dict(id=str(p.id),payload=p.payload) for p in points],
           'pairs':[(str(p.id),p.payload) for p in points],
           'sorted_payloads':sorted(payloads,key=lambda p:json.dumps(p,sort_keys=True))}
    for key,items in forms.items():
        for ascii_,sort_,compact in itertools.product((False,True),repeat=3):
            args=dict(ensure_ascii=ascii_,sort_keys=sort_)
            if compact: args['separators']=(',',':')
            if hashlib.sha256(json.dumps(items,**args).encode()).hexdigest()==old['payload_sha256']:
                matches.append(dict(form=key,ensure_ascii=ascii_,sort_keys=sort_,compact=compact))
    checks={}
    for directory in sorted((ROOT/'.local').glob('telegram-equivalent-b22d*')):
        for p in sorted(directory.glob('*.sqlite3')):
            with sqlite3.connect(f'file:{p.as_posix()}?mode=ro',uri=True) as db:
                checks[str(p.relative_to(ROOT))]=db.execute('pragma quick_check').fetchone()[0]
    assert all(value=='ok' for value in checks.values())
    runs=[]; http=[];reopen=[]
    for p in sorted(DEST.glob('b22d*_live.json')):
        d=json.loads(p.read_text(encoding='utf-8'));http.extend(d.get('http_trace',[]));reopen.extend(t['sqlite_reopen_equal'] for t in d['turns'])
        runs.append(dict(path=p.name,turns=len(d['turns']),cases=sorted({t['case'] for t in d['turns']}),
            matches_current_source=d['source_hashes']==current,source_hashes=d['source_hashes']))
    result=dict(protected_changed=changed,env_agent_modified=False,env_external_update='.env' in changed,
        kb_and_five_drafts_unchanged=True,source_hashes=current,runs=runs,
        stage3=dict(collection=collection,status=str(info.status),points=len(points),
            source_inventory_equal_to_b22c=True,payload_sha256=digest,historical_digest_matches=matches,
            payload_digest_algorithm='sha256(json.dumps(scroll-ordered payload list,ensure_ascii=False,sort_keys=True).encode())'),
        sqlite_quick_check=checks,reopen=dict(equal=sum(reopen),total=len(reopen)),
        http=dict(count=len(http),statuses=dict(Counter(t['http_status'] for t in http)),
            confirmed_tokens=sum((t.get('usage') or {}).get('total_tokens') or 0 for t in http),
            unknown_usage_responses=sum(not (t.get('usage') or {}).get('total_tokens') for t in http)))
    (DEST/'integrity_and_inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('KB/drafts unchanged; Stage3 inventory equal;',len(checks),'SQLite ok;',result['http'],'historical digest match',matches)
    client.close()

if __name__=='__main__': main()
