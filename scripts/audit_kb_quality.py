"""Read-only inventory of KB. Never contacts network or vector stores."""
import argparse, csv, hashlib, re, subprocess, sys
from collections import Counter
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.knowledge import DocumentLoader, Chunker

def write(path, rows, fields):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true');args=parser.parse_args()
    out=ROOT/'reports/kb_review_b2_quality';out.mkdir(parents=True,exist_ok=True)
    baseline=out/'baseline_inventory.csv'
    if args.baseline and baseline.exists(): raise SystemExit('baseline already exists; not overwritten')
    files=sorted((ROOT/'data/knowledge').rglob('*.md')); loader=DocumentLoader(ROOT/'data/knowledge')
    records=[];issues=[]; docs=[];chunk_count=0
    for path in files:
        rel=path.relative_to(ROOT).as_posix(); raw=path.read_bytes(); row={'path':rel,'sha256':hashlib.sha256(raw).hexdigest(),'document_id':'','status':'','service':'','task_category':'','operations':'','chunks':0,'yaml_valid':'unverified','loader':'unverified','markdown_valid':'unverified','chunk_review':'unverified'}
        try:
            text=raw.decode('utf-8'); assert text.startswith('---\n'), 'missing front matter';head=text.split('---',2)[1];meta=yaml.safe_load(head); assert isinstance(meta,dict), 'non-mapping front matter'
            row['yaml_valid']='pass'
            for k in ('document_id','status','service','task_category'):row[k]=str(meta.get(k) or '')
            row['operations']=';'.join(map(str,meta.get('operations') or []))
            for k in ('document_id','title','category','service','task_category','operations','source_url','source_type','status'):
                if not meta.get(k):issues.append((rel,'missing_metadata',k,'warning'))
            if len(re.findall(r'^\s*```',text,re.M))%2: issues.append((rel,'unclosed_fence','code fence','fail'));row['markdown_valid']='fail'
            else:row['markdown_valid']='warning' # full Markdown semantics require manual review
            if re.search(r'\(L\d+(?:\s*[-–]\s*L?\d+)?\)',text):issues.append((rel,'line_reference','unresolved L reference','warning'))
            doc=loader.load(path);row['loader']='pass';chunks=Chunker().split(doc);row['chunks']=len(chunks);chunk_count+=len(chunks);docs.append(doc)
            if not chunks or any(not c.text.strip() for c in chunks):issues.append((rel,'empty_chunks','empty chunk','fail'));row['chunk_review']='fail'
            else:row['chunk_review']='warning' # boundary and semantic review not established
            if len({c.text for c in chunks})<len(chunks):issues.append((rel,'duplicate_chunks','identical chunk text','warning'))
            for page,body in doc.pages:
                for part in re.split(r'\n\s*\n',body):
                    if len(part)>1000:issues.append((rel,'long_paragraph',f'{len(part)} chars; inspect boundary','warning'))
            if set(doc.evidence_coverage)-set(doc.operations):issues.append((rel,'coverage_operation_mismatch',str(set(doc.evidence_coverage)-set(doc.operations)),'warning'))
        except Exception as exc:
            if row['yaml_valid']=='unverified':row['yaml_valid']='fail'
            else:row['loader']='fail'
            issues.append((rel,'load_error',f'{type(exc).__name__}: {exc}','fail'))
        records.append(row)
    for attr in ('document_id','content_hash'):
        cnt=Counter(getattr(d,attr) for d in docs)
        for d in docs:
            if cnt[getattr(d,attr)]>1:issues.append(('data/knowledge/'+d.source,'duplicate_'+attr,getattr(d,attr),'warning'))
    fields=list(records[0]) if records else []
    write(baseline if args.baseline else out/'audit_inventory.csv',records,fields)
    if not args.baseline:write(out/'mechanical_issues.csv',[dict(zip(('path','problem_type','observed','state'),x)) for x in issues],['path','problem_type','observed','state'])
    print(f'files={len(files)} loaded={len(docs)} chunks={chunk_count} issues={len(issues)} statuses={dict(Counter(r["status"] for r in records))}')
if __name__=='__main__':main()
