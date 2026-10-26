import os, json, hashlib, csv
from pathlib import Path
from collections import Counter
from qdrant_client import QdrantClient
# Hard-disable hub/model downloads before any embedding library import.
os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'; os.environ['HF_DATASETS_OFFLINE']='1'
ROOT=Path(r'C:\Users\Shira\Documents\ChatGPT\Rag'); OUT=Path(r'C:\Users\Shira\.codex\experiments\support-rag-retrieval-audit-20261026')
import sys; sys.path.insert(0,str(ROOT))
GOLD=OUT/'questions_gold.jsonl'; expected_sha='e10d518bd6ccc40f94fa1ed767cb1856b0678ce4f204d0ad179fc63eaf285633'
actual_sha=hashlib.sha256(GOLD.read_bytes()).hexdigest()
if actual_sha!=expected_sha: raise RuntimeError('Gold file changed after annotation; stop.')
rows=[json.loads(x) for x in GOLD.read_text(encoding='utf-8').splitlines()]
from app.embeddings import SentenceTransformerEmbedding
from app.vector_store import QdrantStore
from app.retrieval import Retriever, exact_identifiers
from app.retrieval_pipeline import RetrievalPipeline, _state_task_category, _matches_entity, _procedure_matches, normalize_metadata
from app.procedure_policy import operation_compatibility
from app.response_grounding import unsafe_operation_issue
from app.rag import SearchResult
from app.dialogue_state import DialogueState
name='knowledge_stage3_retrieval_20261022'; client=QdrantClient(url='http://127.0.0.1:6333',timeout=15)
# Collection was verified present/green before this run. Bypass QdrantStore.__init__: it has a create-collection fallback if the collection disappears.
embedding=SentenceTransformerEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
store=object.__new__(QdrantStore); store.client=client; store.embedding=embedding; store.collection=name
points=[]; offset=None; scroll_calls=0
while True:
 batch,offset=client.scroll(name,offset=offset,limit=256,with_payload=True,with_vectors=False); scroll_calls+=1; points.extend(batch)
 if offset is None: break
if len(points)!=934: raise RuntimeError(f'Stage3 point count changed since preflight: {len(points)}')
store.all_points=lambda: points
retriever=Retriever(store,demo=False)
by_doc={}; by_sections={}
for p in points:
 x=p.payload or {}; doc=x.get('document_id')
 if doc: by_doc.setdefault(doc,[]).append(x)
 if doc and x.get('status')=='approved': by_sections.setdefault(doc,set()).add(x.get('section'))
# Gold must be present/approved and section labels must exist; this is an annotation integrity check before retrieval.
for row in rows:
 doc=row['gold_document_id']
 if doc is not None:
  if doc not in by_doc or not any(x.get('status')=='approved' for x in by_doc[doc]): raise RuntimeError('Gold doc is absent/unapproved: '+doc)
  if row['gold_section'] not in by_sections.get(doc,set()): raise RuntimeError('Gold section absent from approved Stage3 payload: '+doc+' / '+str(row['gold_section']))
class FixedSource:
 def __init__(self,hits): self.hits=hits
 def search(self,query,top_k=5): return [SearchResult(source=str(h.metadata.get('source') or 'unknown'),text=h.text,score=h.score,semantic_score=h.semantic_score,lexical_score=h.lexical_score,metadata=h.metadata) for h in self.hits[:top_k]]
 def article(self,document_id):
  return [SearchResult(source=str(x.get('source') or 'unknown'),text=str(x.get('text') or ''),score=0,metadata=x) for x in by_doc.get(document_id,[]) if x.get('status')=='approved']
def ranked_doc_ids(hits):
 out=[]; seen=set()
 for h in hits:
  d=(h.metadata or {}).get('document_id')
  if d and d not in seen: seen.add(d); out.append(d)
 return out
def filtered_doc_ids(docs):
 out=[]; seen=set()
 for d in docs:
  md=d.metadata or {}; key=md.get('document_id')
  if key and key not in seen: seen.add(key); out.append(key)
 return out
def soft_ranking(state,query,hits):
 if unsafe_operation_issue(query): return []
 expected=_state_task_category(state,query); out=[]
 for original_rank,h in enumerate(hits,1):
  m=normalize_metadata({**(h.metadata or {}),'source':(h.metadata or {}).get('source') or '','text':h.text})
  if m.get('status')!='approved': continue
  # Hard gates: explicit service/manufacturer/model/procedure conflicts are never softened.
  route=state.routing_service or state.task_entity('ofd')
  if route and m.get('service') and not _matches_entity(route,m.get('service')): continue
  manufacturer=state.entity('manufacturer') or state.task_entity('manufacturer')
  if manufacturer and m.get('manufacturer') and not _matches_entity(manufacturer,m.get('manufacturer')): continue
  equipment=state.entity('equipment') or state.task_entity('equipment')
  if equipment and m.get('model') and not _matches_entity(equipment,m.get('model')): continue
  software=state.task_entity('software')
  if software and m.get('software') and not _matches_entity(software,m.get('software')): continue
  if not _procedure_matches(state,m): continue
  # Retriever already enforces exact requested error/version identifiers before this stage.
  if exact_identifiers(query):
   codes={str(z).lstrip('-').replace(',','.') for z in exact_identifiers(query)}
   corpus=' '.join([h.text,str(m.get('title') or ''),str(m.get('model') or ''),str(m.get('version') or '')])
   from app.retrieval import tokens
   if not codes.issubset({z.replace(',','.') for z in tokens(corpus)}): continue
  cat=m.get('task_category'); cat_bonus=.020 if expected and cat==expected else -.012 if expected and cat else -.004 if expected else 0
  op_status=operation_compatibility(state.operation,m,query,task_category=expected)
  explicit_ops=bool(m.get('_operations_explicit'))
  op_bonus=.012 if op_status=='match' else -.010 if op_status=='mismatch' and explicit_ops else -.003 if op_status=='mismatch' or not m.get('operations') else 0
  out.append((h.score+cat_bonus+op_bonus,original_rank,h))
 # Collapse chunks by document, keeping its highest soft score.
 best={}
 for score,rank,h in out:
  doc=(h.metadata or {}).get('document_id')
  if doc and (doc not in best or score>best[doc][0]): best[doc]=(score,rank,h)
 return sorted(best.values(),key=lambda z:(z[0],-z[1]),reverse=True)
all_results=[]; loss_rows=[]; reason_totals=Counter(); query_cat=Counter(); query_op=Counter(); raw_gold_present=0; post_gold_present=0; soft_gold_present=0
for idx,row in enumerate(rows,1):
 q=row['question']; state=DialogueState.from_dict(row['state'])
 hits=retriever.search(q,top_k=100)
 raw_ids=ranked_doc_ids(hits)
 source=FixedSource(hits)
 pipeline=RetrievalPipeline(source,candidate_k=100,max_documents=100,max_context_chars=50000,expand_chunks=True)
 filtered=pipeline.search(state,q)
 after_ids=filtered_doc_ids(filtered.documents)
 soft=soft_ranking(state,q,hits); soft_ids=[]; soft_sections=[]
 for _,_,h in soft:
  d=(h.metadata or {}).get('document_id')
  if d: soft_ids.append(d); soft_sections.append((d,(h.metadata or {}).get('section')))
 gold=row['gold_document_id']; raw_rank=raw_ids.index(gold)+1 if gold in raw_ids else None; after_rank=after_ids.index(gold)+1 if gold in after_ids else None; soft_rank=soft_ids.index(gold)+1 if gold in soft_ids else None
 gold_section=row['gold_section']; raw_sec_rank=next((i+1 for i,h in enumerate(hits) if (h.metadata or {}).get('document_id')==gold and (h.metadata or {}).get('section')==gold_section),None) if gold else None
 # Keep no-approved-evidence outcomes out of Recall denominators.
 if gold:
  raw_gold_present+=int(gold in raw_ids); post_gold_present+=int(gold in after_ids); soft_gold_present+=int(gold in soft_ids)
  hit_meta=(by_doc.get(gold) or [{}])[0]
  for key in ['task_category','operations','service','software','manufacturer','model']:
   val=hit_meta.get(key)
   if key=='operations': val=bool(val)
   query_cat[key+('_missing' if not val else '_present')]+=1
  reasons=[]
  if gold not in raw_ids: cause='not_in_raw_top100'
  elif gold not in after_ids:
   rej=next((x for x in filtered.rejected if x.document_id==gold),None)
   reasons=rej.reasons if rej else []
   if not reasons: cause='selection_policy_or_document_cap'
   else:
    for r in reasons: reason_totals[r]+=1
    tags=[]
    for r in reasons:
     if r.startswith(('task_mismatch','task_unconfirmed')): tags.append('task')
     elif 'operation_' in r: tags.append('operation')
     elif 'service_' in r or 'procedure_service' in r: tags.append('service')
     elif 'manufacturer_' in r: tags.append('manufacturer')
     elif 'equipment_' in r: tags.append('model')
     elif 'ofd_' in r: tags.append('ofd')
     elif 'applicability_' in r: tags.append('applicability')
     else: tags.append('other')
    cause='filtered_by_'+'|'.join(sorted(set(tags)))
  else: cause='retained'
  if gold not in after_ids: loss_rows.append({'query_id':row['query_id'],'question':q,'gold_document_id':gold,'raw_rank':raw_rank,'filtered_rank':after_rank,'cause':cause,'filter_reasons':reasons,'gold_section':gold_section})
 else: cause='no_approved_evidence'
 result={'query_id':row['query_id'],'conversation_id':row['conversation_id'],'question':q,'gold_document_id':gold,'gold_section':gold_section,'gold_label':row['gold_label'],'expected_task_category':_state_task_category(state,q),'operation':state.operation,'routing_service':state.routing_service,'manufacturer':state.entity('manufacturer') or state.task_entity('manufacturer'),'equipment_model':state.entity('equipment') or state.task_entity('equipment'),'raw_top5':raw_ids[:5],'filtered_top5':after_ids[:5],'soft_ranked_top5':soft_ids[:5],'raw_gold_rank':raw_rank,'filtered_gold_rank':after_rank,'soft_gold_rank':soft_rank,'raw_gold_section_rank':raw_sec_rank,'loss_cause':cause,'filter_reasons':(next((x.reasons for x in filtered.rejected if x.document_id==gold),[]) if gold else []),'rejected_candidates':[{'document_id':x.document_id,'reasons':x.reasons,'metadata':x.metadata,'rrf':x.retrieval.get('rrf')} for x in filtered.rejected[:15]],'raw_candidates':[{'document_id':(h.metadata or {}).get('document_id'),'source':(h.metadata or {}).get('source'),'section':(h.metadata or {}).get('section'),'task_category':(h.metadata or {}).get('task_category'),'operation':(h.metadata or {}).get('operation'),'operations':(h.metadata or {}).get('operations'),'service':(h.metadata or {}).get('service'),'model':(h.metadata or {}).get('model'),'status':(h.metadata or {}).get('status'),'score':h.score,'dense':h.semantic_score,'bm25':h.lexical_score} for h in hits[:15]],'selected_candidates':[{'document_id':x.document_id,'source':x.source,'reasons':x.reasons,'relevance':x.relevance.score,'rrf':x.retrieval.get('rrf')} for x in filtered.candidates]}
 filtered_sections=[]; seen_sec=set()
 for doc in filtered.documents:
  md=doc.metadata or {}; pair=(md.get('document_id'),md.get('section'))
  if pair[0] and pair not in seen_sec: seen_sec.add(pair); filtered_sections.append(pair)
 result['filtered_gold_section_rank']=next((i+1 for i,pair in enumerate(filtered_sections) if pair==(gold,gold_section)),None) if gold else None
 result['soft_gold_section_rank']=next((i+1 for i,pair in enumerate(soft_sections) if pair==(gold,gold_section)),None) if gold else None
 result['filtered_sections_top10']=filtered_sections[:10]
 result['soft_sections_top10']=soft_sections[:10]
 all_results.append(result)
 print(f'processed {idx}/{len(rows)}: {row["query_id"]}')
# Aggregate unique exact questions separately; keep the first occurrence per exact raw question.
def recalls(field,subset):
 denom=sum(1 for r in subset if r['gold_document_id'])
 return {f'R@{k}': (sum(1 for r in subset if r['gold_document_id'] and r[field] and r[field]<=k)/denom if denom else None) for k in (1,3,5)} | {'n_answerable':denom}
by_id={r['query_id']:r for r in all_results}
metric_rows=[]
for field in ['raw_gold_rank','filtered_gold_rank','soft_gold_rank']:
 metric_rows.append({'method':field.replace('_gold_rank',''),'turn_level':recalls(field,all_results)})
seen=set(); unique=[]
for r in all_results:
 if r['question'] not in seen: seen.add(r['question']); unique.append(r)
for m in metric_rows: m['exact_text_unique']=recalls(m['method']+'_gold_rank',unique)
section_metrics=[]
for field in ['raw_gold_section_rank','filtered_gold_section_rank','soft_gold_section_rank']:
 section_metrics.append({'method':field.replace('_gold_section_rank',''),'turn_level':recalls(field,all_results),'exact_text_unique':recalls(field,unique)})
section_raw=sum(1 for r in all_results if r['gold_document_id'] and r['raw_gold_section_rank'] and r['raw_gold_section_rank']<=5)
meta_counts=Counter();
for p in points:
 x=p.payload or {}
 if x.get('status')!='approved': continue
 for key in ['task_category','operations','service','software','manufacturer','model','procedure_service']:
  value=x.get(key)
  missing=(not value)
  meta_counts[key+('_missing' if missing else '_present')]+=1
status_docs=Counter()
for doc,items in by_doc.items():
 status_docs[next((x.get('status') for x in items if x.get('status')),'<missing>')]+=1
summary={'gold_file_sha256':actual_sha,'n_query_turns':len(rows),'n_distinct_exact_question_strings':len(unique),'gold_answerable_rows':sum(r['gold_document_id'] is not None for r in rows),'no_approved_evidence_rows':sum(r['gold_document_id'] is None for r in rows),'metrics':metric_rows,'section_metrics':section_metrics,'raw_section_recall_at5':section_raw/sum(1 for r in all_results if r['gold_document_id'] is not None),'qdrant_collection':name,'qdrant_point_count':len(points),'approved_only':True,'qdrant_scroll_requests':scroll_calls,'dense_query_requests':len(rows),'qdrant_writes':0,'groq_calls':0,'embedding_model':'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2','embedding_mode':'local / HF_HUB_OFFLINE=1','approved_metadata_point_coverage':dict(meta_counts),'status_document_counts':dict(status_docs),'filter_rejection_reasons':dict(reason_totals),'method':'Current app.Retriever (top100 approved, exact identifiers and brand/model guards) + current RetrievalPipeline; soft ranking is analytic and preserves all hard safety/applicability/entity/code gates.'}
(OUT/'retrieval_results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in all_results),encoding='utf-8')
(OUT/'loss_reasons.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in loss_rows),encoding='utf-8')
(OUT/'metrics.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'soft_ranking_formula.json').write_text(json.dumps({'raw_rrf_score':'unchanged current hybrid RRF','task_category':'match +0.020; unlabeled -0.004; explicit mismatch -0.012','operation':'match +0.012; unlabeled/incompatible but not explicit -0.003; explicit mismatch -0.010','hard_rejects':['status != approved','unsafe query','explicit service conflict','explicit manufacturer conflict','explicit model conflict','procedure_service conflict','exact code/version conflict'],'notes':'Fixed analytic weights selected before outcomes; not tuned; no production pipeline changes.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
