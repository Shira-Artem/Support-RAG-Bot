from __future__ import annotations
import json, sys
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from qdrant_client import QdrantClient
from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueManager, DialogueState
from app.embeddings import SentenceTransformerEmbedding
from app.knowledge import DocumentLoader
from app.rag_query import QueryNeedsClarification, build_rag_query
from app.retrieval import Retriever
from app.vector_store import QdrantStore
from app.retrieval_pipeline import normalize_metadata
CAND=ROOT/'reports/kb_quality_sprint_20261028/sprint3_candidates'
FILES=sorted(CAND.glob('*.md'))
CASES=[
 ('bifit_terminal','В БИФИТ Касса подключён банковский терминал, но карта не проходит.','candidate-kbqs3-bifit-pos-terminal-scope'),
 ('bifit_tables','В БИФИТ Касса Общепит нужно проверить тестирование столов.','candidate-kbqs3-bifit-horeca-tables-scope'),
 ('diadoc_status','Диадок: контрагент не видит отправленный УПД, хочу проверить статус.','candidate-kbqs3-diadoc-outgoing-status'),
 ('saby_incoming','В Saby не могу найти входящий документ.','candidate-kbqs3-saby-incoming-status'),
 ('evotor_marking','Эвотор отклонил код маркировки при онлайн-проверке.','candidate-kbqs3-evotor-marking-refusal'),
 ('evotor_combo','Эвотор: как работает комбинированная оплата?','candidate-kbqs3-evotor-combined-payment'),
 ('tspiot_generic','Как диагностировать ошибку ТС ПиОТ?','candidate-kbqs3-tspiot-api-scope'),
 ('atol_api','АТОЛ Онлайн: после подтверждённой оплаты API чек не найден.','candidate-kbqs3-atol-api-receipt-not-found'),
 ('negative_atol_evotor','Эвотор: как работает комбинированная оплата?','candidate-kbqs3-atol-api-receipt-not-found'),
 ('negative_bifit_evotor','Эвотор отклонил код маркировки.','candidate-kbqs3-bifit-pos-terminal-scope'),
 ('negative_diadoc_saby','В Saby не могу найти входящий документ.','candidate-kbqs3-diadoc-outgoing-status'),
 ('negative_status_atol','АТОЛ Онлайн: как посмотреть статус подписания УПД?','candidate-kbqs3-atol-api-receipt-not-found'),
 ('real_bifit','Здравствуйте. Нам нужно протестировать в программе БИФИТ систему общепит со столами.',None),
 ('real_marking','При пробитии чека не считался код маркировки и эта позиция исчезла из чека.',None),
 ('real_edo','Не получаем документы по ЭДО в Честный ЗНАК.',None),
 ('real_terminal','В приложении не подключен ни один банковский терминал.',None),
]

def main():
 loader=DocumentLoader(ROOT/'data/knowledge'); baseline=[d for d in loader.load_all() if d.status=='approved']
 c_loader=DocumentLoader(CAND); candidates=[replace(c_loader.load(p),status='approved') for p in FILES]
 meta=[]
 for d in candidates:
  n=normalize_metadata({'document_id':d.document_id,'source':d.source,'category':d.category,'title':d.title,'service':d.service,'task_category':d.task_category,'operations':d.operations,'manufacturer':d.manufacturer,'model':d.model,'version':d.version,'status':d.status,'_operations_explicit':True})
  meta.append({'document_id':d.document_id,'source':d.source,'task_category':n['task_category'],'operations':n['operations'],'service':n['service'],'model':n['model'],'version':n['version']})
 client=QdrantClient(':memory:'); emb=SentenceTransformerEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'); stores={}
 for name,docs in [('baseline',baseline),('staging',baseline+candidates)]:
  store=QdrantStore(client,emb,'sprint3_'+name); store.index(docs,remove_missing=True); stores[name]=RetrieverRAGAdapter(Retriever(store,demo=False))
 manager=DialogueManager(); results=[]
 for cid,msg,exp in CASES:
  state=manager.advance(DialogueState(),msg,cid); row={'case_id':cid,'message':msg,'expected_candidate':exp,'collections':{}}
  try: q=build_rag_query(state)
  except QueryNeedsClarification as e: row['query_error']=str(e); results.append(row); continue
  row['query']=q
  for label,a in stores.items():
   raw=a.search(q,top_k=a.pipeline.candidate_k); res=a.search_for_state(state,q)
   row['collections'][label]={'top_k':list(dict.fromkeys(h.metadata.get('document_id') for h in raw))[:10], 'final':list(dict.fromkeys(d.metadata.get("document_id") for d in res.documents)), 'sufficient':res.sufficient,'evidence_status':res.evidence_status,'reason':res.insufficiency_reason}
  stage=row['collections']['staging']; row['top_k_expected']=bool(exp and exp in stage['top_k']); row['final_expected']=bool(exp and exp in stage['final'] and stage['sufficient'])
  row['unexpected_candidate_final']=bool(exp is None and any(x.startswith('candidate-kbqs3-') for x in stage['final']))
  results.append(row)
 positive_ids={'bifit_terminal','bifit_tables','diadoc_status','saby_incoming','evotor_marking','evotor_combo','tspiot_generic','atol_api'}; negative_ids={'negative_atol_evotor','negative_bifit_evotor','negative_diadoc_saby','negative_status_atol'}
 candidate_ids={d.document_id for d in candidates}
 summary={'cases':len(results),'positive_cases':len(positive_ids),'negative_pairs':len(negative_ids),'real_prompts':sum(r['case_id'].startswith('real_') for r in results),
  'positive_cases_resolved_by_state':sum('query_error' not in r for r in results if r['case_id'] in positive_ids),
  'positive_expected_raw_top_k_hits':sum(r.get('top_k_expected',False) for r in results if r['case_id'] in positive_ids),
  'positive_expected_final_evidence_hits':sum(r.get('final_expected',False) for r in results if r['case_id'] in positive_ids),
  'negative_target_candidate_top_k_hits':sum(r.get('expected_candidate') in r.get('collections',{}).get('staging',{}).get('top_k',[]) for r in results if r['case_id'] in negative_ids),
  'negative_target_candidate_final_hits':sum(r.get('expected_candidate') in r.get('collections',{}).get('staging',{}).get('final',[]) for r in results if r['case_id'] in negative_ids),
  'negative_cross_candidate_final_hits':sum(bool((candidate_ids-{r.get('expected_candidate')}) & set(r.get('collections',{}).get('staging',{}).get('final',[]))) for r in results if r['case_id'] in negative_ids),
  'real_prompts_with_new_candidate_final_evidence':sum(r.get('unexpected_candidate_final',False) for r in results if r['case_id'].startswith('real_')),
  'baseline_staging_same_final_selection_real':sum(r.get('collections',{}).get('baseline',{}).get('final')==r.get('collections',{}).get('staging',{}).get('final') for r in results if r['case_id'].startswith('real_')),
  'llm_quality_evaluated':False}
 out={'mode':'qdrant_client_in_memory_only','llm_calls':0,'production_qdrant_access':False,'production_kb_write':False,'approved_baseline_documents':len(baseline),'candidate_overlay_documents':len(candidates),'metadata_normalization':meta,'cases':results,'summary':summary}
 (ROOT/'reports/kb_quality_sprint_20261028/sprint3_staging_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(out['summary'],ensure_ascii=False)); print('metadata',json.dumps(meta,ensure_ascii=False))
if __name__=='__main__': main()
