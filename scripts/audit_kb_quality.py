"""Read-only inventory of KB. Never contacts network or vector stores."""
import argparse, csv, hashlib, re, sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.knowledge import DocumentLoader, Chunker
from app.procedure_policy import normalize_operation

class UniqueKeyLoader(yaml.SafeLoader):
    """Safe loader which rejects duplicate YAML mapping keys."""

def _construct_unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f'duplicate YAML key: {key!r}')
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping

UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)

def valid_date(value):
    if value in (None, '') or isinstance(value, (date, datetime)):
        return True
    if isinstance(value, str):
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False
    return False

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
            text=raw.decode('utf-8'); assert text.startswith('---\n'), 'missing front matter';head=text.split('---',2)[1];meta=yaml.load(head,Loader=UniqueKeyLoader); assert isinstance(meta,dict), 'non-mapping front matter'
            row['yaml_valid']='pass'
            for k in ('document_id','status','service','task_category'):row[k]=str(meta.get(k) or '')
            row['operations']=';'.join(map(str,meta.get('operations') or []))
            for k in ('document_id','title','category','service','task_category','operations','source_url','source_type','status'):
                if not meta.get(k):issues.append((rel,'missing_metadata',k,'warning'))
            for k in ('operations','search_fields'):
                if k in meta and meta[k] is not None and (not isinstance(meta[k],list) or any(not isinstance(v,str) for v in meta[k])):
                    issues.append((rel,'wrong_type_metadata',f'{k} must be list[str]','fail'))
            coverage=meta.get('evidence_coverage')
            if coverage is not None and (not isinstance(coverage,dict) or any(not isinstance(k,str) or not isinstance(v,str) or v not in ('full','partial') for k,v in coverage.items())):
                issues.append((rel,'wrong_type_metadata','evidence_coverage must map operation keys to full/partial','fail'))
            for k in ('published_at','collected_at','source_checked_at','verified_at'):
                if k in meta and not valid_date(meta[k]):issues.append((rel,'invalid_date_metadata',f'{k}={meta[k]!r}','fail'))
            if meta.get('status') not in ('approved','draft'):issues.append((rel,'invalid_status',repr(meta.get('status')),'fail'))
            if meta.get('status')=='approved' and meta.get('verified_at') in (None,''):
                issues.append((rel,'approved_missing_verified_at',repr(meta.get('verified_at')),'fail'))
            if meta.get('status')=='draft' and meta.get('verified_at') not in (None,''):
                issues.append((rel,'draft_has_verified_at',repr(meta.get('verified_at')),'warning'))
            url=meta.get('source_url'); parsed=urlparse(url) if isinstance(url,str) else None
            if not parsed or parsed.scheme not in ('http','https') or not parsed.netloc:
                issues.append((rel,'invalid_source_url',repr(url),'fail'))
            if meta.get('status')=='draft' and not isinstance(meta.get('review_note'),str):
                issues.append((rel,'draft_missing_review_note','review_note missing or not string','warning'))
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
            normalized_coverage={normalize_operation(str(x),doc.task_category,text) for x in doc.evidence_coverage}
            normalized_operations={normalize_operation(str(x),doc.task_category,text) for x in doc.operations}
            if normalized_coverage-normalized_operations:issues.append((rel,'coverage_operation_mismatch',str(normalized_coverage-normalized_operations),'warning'))
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
