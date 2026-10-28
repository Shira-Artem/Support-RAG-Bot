from __future__ import annotations
import json
from dataclasses import replace
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qdrant_client import QdrantClient
from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueManager, DialogueState
from app.embeddings import SentenceTransformerEmbedding
from app.knowledge import DocumentLoader
from app.rag_query import QueryNeedsClarification, build_rag_query
from app.retrieval import Retriever
from app.vector_store import QdrantStore

CAND=ROOT/'reports/kb_quality_sprint_20261028/candidates'
SELECTED=['03-evotor-fn-231.md','04-evotor-fn-234.md','05-evotor-fn-235.md','08-platformaofd-receipt-status.md','09-aqsi-scanner-hub.md']
CASES=[
 ('evotor_fn231','Эвотор ошибка ФН 231 -3975 при продаже, ФН-М 36 месяцев, ОСН и продажи услуг.','candidate-kbqs-20261028-evotor-fn-231'),
 ('evotor_fn234','На Эвоторе ошибка ФН 234, хочу проверить дату и время.','candidate-kbqs-20261028-evotor-fn-234'),
 ('evotor_fn235','Эвотор показывает ФН 235 -3979, в ОФД есть неотправленные документы.','candidate-kbqs-20261028-evotor-fn-235'),
 ('platform_receipt','Как найти конкретный чек в личном кабинете Платформы ОФД и что означает карантин?','candidate-kbqs-20261028-platformaofd-receipt-status'),
 ('aqsi_scanner','Внешний сканер не читает DataMatrix на физической кассе aQsi, подключен через Hub.','candidate-kbqs-20261028-aqsi-scanner-hub'),
 ('negative_fn_pair','На Эвоторе ошибка ФН 234, проверка даты и времени.','candidate-kbqs-20261028-evotor-fn-234'),
 ('negative_aqsi_online','aQsi Online: как оформить частичный возврат по исходному чеку?','candidate-kbqs-20261028-aqsi-scanner-hub'),
 ('negative_evotor_queue','На Эвоторе очередь чеков не передается в ОФД.','candidate-kbqs-20261028-evotor-no-receipt-transmission'),
 ('negative_atol','АТОЛ Онлайн: API-чек не найден после платежа, какой статус запроса?','candidate-kbqs-20261028-evotor-fn-231'),
 ('negative_receipt_diag','Платформа ОФД: ошибка ФН 235 и очередь неотправленных документов.','candidate-kbqs-20261028-platformaofd-receipt-status'),
 ('generic_evotor','Эвотор не работает, помогите.','candidate-kbqs-20261028-evotor-no-receipt-transmission'),
]

# Add exact, already-anonymized client questions from the local evaluation set.
_eval_path=ROOT/'reports/kb_quality_sprint_20261028/sprint2_evaluation_dataset.jsonl'
_eval_rows={row['case_id']:row for row in (json.loads(line) for line in _eval_path.read_text(encoding='utf-8').splitlines())}
for _name,_ref in [('real_ofd_unscoped','KBQS2-23'),('real_scanner_unscoped','KBQS2-38'),('real_edo_marking_unscoped','KBQS2-50'),('real_fn_expiry_unscoped','KBQS2-10')]:
    CASES.append((_name,_eval_rows[_ref]['text'],None))

FORBIDDEN={'evotor_fn231':['candidate-kbqs-20261028-evotor-fn-234','candidate-kbqs-20261028-evotor-fn-235'],'evotor_fn234':['candidate-kbqs-20261028-evotor-fn-231','candidate-kbqs-20261028-evotor-fn-235'],'evotor_fn235':['candidate-kbqs-20261028-evotor-fn-231','candidate-kbqs-20261028-evotor-fn-234'],'aqsi_scanner':['aqsi-online-receipts-full-refund','aqsi-online-receipts-partial-refund'],'negative_fn_pair':['candidate-kbqs-20261028-evotor-fn-231','candidate-kbqs-20261028-evotor-fn-235'],'negative_aqsi_online':['candidate-kbqs-20261028-aqsi-scanner-hub'],'negative_atol':['candidate-kbqs-20261028-evotor-fn-231','candidate-kbqs-20261028-evotor-fn-234','candidate-kbqs-20261028-evotor-fn-235'],'negative_receipt_diag':['candidate-kbqs-20261028-platformaofd-receipt-status']}

def main():
    loader=DocumentLoader(ROOT/'data/knowledge')
    baseline=[d for d in loader.load_all() if d.status=='approved']
    cand_loader=DocumentLoader(CAND)
    candidates=[replace(cand_loader.load(CAND/name),status='approved') for name in SELECTED]
    # Isolated embedded Qdrant memory; no URL, collection, or production Qdrant access.
    client=QdrantClient(':memory:')
    embedding=SentenceTransformerEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    stores={}
    for name,docs in [('baseline',baseline),('staging',baseline+candidates)]:
        store=QdrantStore(client,embedding,'sprint2_'+name)
        store.index(docs,remove_missing=True)
        stores[name]=RetrieverRAGAdapter(Retriever(store,demo=False))
    manager=DialogueManager(); results=[]
    for case_id,message,expected in CASES:
        state=manager.advance(DialogueState(),message,case_id)
        row={'case_id':case_id,'expected_candidate':expected,'message':message,'collections':{}}
        try: query=build_rag_query(state)
        except QueryNeedsClarification as exc:
            row['query_error']=str(exc); results.append(row); continue
        row['query']=query
        for label,adapter in stores.items():
            raw=adapter.search(query,top_k=adapter.pipeline.candidate_k)
            result=adapter.search_for_state(state,query)
            row['collections'][label]={'top_k_document_ids':list(dict.fromkeys(h.metadata.get('document_id') for h in raw))[:10],
              'selected_document_ids':list(dict.fromkeys(d.metadata.get('document_id') for d in result.documents)),
              'sufficient_evidence':result.sufficient,'evidence_status':result.evidence_status,
              'missing_evidence':result.missing_evidence,'insufficiency_reason':result.insufficiency_reason}
        stage=row['collections']['staging']
        if expected is not None:
            row['expected_top_k_hit']=expected in stage['top_k_document_ids']
            row['expected_final_evidence']=expected in stage['selected_document_ids'] and stage['sufficient_evidence']
        else:
            row['expected_top_k_hit']=None
            row['unexpected_candidate_in_final']=any(str(x).startswith('candidate-kbqs-') for x in stage['selected_document_ids'])
        row['forbidden_candidate_ids']=FORBIDDEN.get(case_id,[]) if expected is not None else [d.document_id for d in candidates]
        row['forbidden_in_top_k']=bool(set(row['forbidden_candidate_ids']) & set(stage['top_k_document_ids']))
        row['forbidden_in_final_evidence']=bool(set(row['forbidden_candidate_ids']) & set(stage['selected_document_ids']))
        results.append(row)
    out={'mode':'qdrant_client_in_memory_only','llm_calls':0,'production_qdrant_access':False,'production_kb_write':False,
      'baseline_approved_documents':len(baseline),'candidate_overlay_documents':len(candidates),'cases':results,
      'summary':{'cases':len(results),'expected_cases':sum(r.get('expected_candidate') is not None for r in results),'expected_top_k_hits':sum(r.get('expected_top_k_hit') is True for r in results),
        'expected_final_evidence':sum(r.get('expected_final_evidence') is True for r in results),'forbidden_final_evidence_hits':sum(r.get('forbidden_in_final_evidence',False) for r in results),'real_unscoped_cases':sum(r.get('expected_candidate') is None for r in results),'real_unscoped_new_candidate_hits':sum(r.get('unexpected_candidate_in_final',False) for r in results)}}
    p=ROOT/'reports/kb_quality_sprint_20261028/sprint2_staging_results.json'
    p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out['summary'],ensure_ascii=False))
if __name__=='__main__':main()
