"""Predicate isolation on saved real k02 trace and read-only Stage3 payloads.

No runtime patch, no new LLM call, no claim of an AFTER answer.
"""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qdrant_client import QdrantClient
from app.dialogue_state import DialogueState
from app.rag import SearchResult
from app.retrieval_pipeline import _matches_entity, _state_task_category, _unresolved_task_fallback

def main():
 d=json.loads((ROOT/'reports/b2_2c_20261104/b22c_baseline_v4_live.json').read_text(encoding='utf-8'))
 t=d['turns'][0]; state=DialogueState.from_dict(t['state_after']); query=t['diagnostics']['rag_query']
 candidates=t['diagnostics']['retrieval_diagnostics']['candidates']
 client=QdrantClient(url='http://127.0.0.1:6333'); points=[]; offset=None
 while True:
  batch,offset=client.scroll('knowledge_stage3_retrieval_20261022',offset=offset,limit=256,with_payload=True,with_vectors=False); points.extend(batch)
  if offset is None: break
 rows=[]
 for c in candidates:
  if c['source'] not in {'aqsi_devices/errors/paper-print-retry.md','aqsi_devices/sales/marked-product.md'}: continue
  p=next(p.payload for p in points if p.payload.get('source')==c['source'] and p.payload.get('section')==c['metadata']['section'])
  meta=c['metadata']; scores=c['retrieval']; hit=SearchResult(c['source'],p['text'],scores['rrf'],scores['dense'],scores['bm25'],meta)
  kwargs={'service_match':_matches_entity(state.routing_service,meta.get('manufacturer')),'manufacturer_match':_matches_entity(state.task_entity('manufacturer'),meta.get('manufacturer')),'model_match':_matches_entity(state.task_entity('equipment'),meta.get('model')),'software_match':True,'operation_status':'unknown'}
  actual=_unresolved_task_fallback(state,query,hit,meta,**kwargs)
  counter=_unresolved_task_fallback(state,query,hit,meta,**{**kwargs,'model_match':True})
  rows.append({'source':c['source'],'metadata_model':meta.get('model'),'client_model':state.task_entity('equipment'),'predicate_inputs':kwargs,'fallback_actual':actual,'fallback_if_model_match_only':counter,'saved_rejection':c['reasons'],'saved_selected':c['selected'],'text':p['text']})
 result={'kind':'offline isolation; not a proposed unconditional model bypass, not a LIVE AFTER','state_task_category':_state_task_category(state,query),'state_operation':state.operation,'rows':rows,'conclusion':'Generic physical product-class model fails the legacy entity matcher in unresolved fallback; model_match alone is sufficient for target rejection. The selected adjacent sales article has a numeric-suffix model match. The relationship between 5 and 5Ф is not established here. Need a consistent applicability contract, not arbitrary model=True.'}
 (ROOT/'reports/b2_2c_20261104/fallback_predicate_isolation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False,indent=2)[:2300]); client.close()

if __name__=='__main__': main()
