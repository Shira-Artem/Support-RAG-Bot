"""Read-only Stage3 counterfactual; no Groq, no runtime-file modification.

Checks a hypothesis only. This is not a LIVE quality result or an implemented fix.
"""
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['HF_HUB_OFFLINE']='1'
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
from qdrant_client import QdrantClient
from app.embeddings import SentenceTransformerEmbedding
from app.vector_store import QdrantStore
import app.retrieval as module
from b2_2c_live_harness import ReadOnlyQdrant

def main():
 client=QdrantClient(url=os.getenv('QDRANT_URL','http://127.0.0.1:6333'))
 store=QdrantStore(ReadOnlyQdrant(client),SentenceTransformerEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'),'knowledge_stage3_retrieval_20261022')
 original=module.Retriever(store)
 code=inspect.getsource(module)
 needle='if requested_model and point_model != requested_model:'
 assert code.count(needle)==1
 candidate_code=code.replace(needle,'if requested_model and point_model and point_model != requested_model:')
 candidate_module=types.ModuleType('b22c_counterfactual_retrieval')
 sys.modules[candidate_module.__name__]=candidate_module
 exec(compile(candidate_code,'<isolated-counterfactual>','exec'),candidate_module.__dict__)
 candidate=candidate_module.Retriever(store)
 queries=[
  ('baseline_k01','оборудование: Эвотор 7.3 — производитель: Эвотор — На Эвотор 7.3 выскочила ФН 234. Это уже обязательно менять накопитель или можно сначала что-то проверить?','evotor/fn/fn-234.md'),
  ('independent_model_code','На Эвотор 6 ошибка ФН 212. Что означает код?','evotor/fn/fn-212.md'),
  ('independent_model_code2','Эвотор 7.2 ошибка ФН 217. Что проверить?','evotor/fn/fn-217.md'),
  ('wrong_model_control','Эвотор 7.3 повторная печать копии чека по номеру ФД','evotor/cash/evotor-6-receipt-copy.md'),
  ('wrong_code_control','Эвотор 7.3 ошибка ФН 234','evotor/fn/fn-235.md'),
  ('wrong_brand_control','АТОЛ 30Ф ошибка ФН 234','evotor/fn/fn-234.md'),
  ('no_model_control','Эвотор ошибка ФН 234','evotor/fn/fn-234.md'),
 ]
 baseline=json.loads((ROOT/'reports/b2_2c_20261104/baseline_frozen_v2.json').read_text(encoding='utf-8'))
 for case in baseline['cases']:
  if case['coverage']:
   queries.append(('raw_question_'+case['id'],case['turns'][0],case['coverage'][0]['source']))
 def dump(hits): return [{'source':h.metadata.get('source'),'model':h.metadata.get('model'),'section':h.metadata.get('section'),'status':h.metadata.get('status'),'text':h.text,'score':h.score} for h in hits]
 rows=[]
 for name,q,target in queries:
  a,b=original.search(q,30),candidate.search(q,30)
  rows.append({'id':name,'query':q,'target':target,'before':dump(a),'counterfactual':dump(b),'target_before':any(h.metadata.get('source')==target for h in a),'target_counterfactual':any(h.metadata.get('source')==target for h in b)})
  print(name,rows[-1]['target_before'],rows[-1]['target_counterfactual'],flush=True)
 allpoints=store.all_points()
 report={'kind':'offline counterfactual retrieval on real read-only Stage3; no LLM or final answer. Candidate not implemented.','runtime_retrieval_sha256':hashlib.sha256((ROOT/'app/retrieval.py').read_bytes()).hexdigest(),'hypothesis':'Exact requested model early filter rejects model-null manufacturer-wide documents before scope policy. Allow retrieval of null-model candidates while retaining all later applicability/safety/operation/source gates.','points':len(allpoints),'target_points':[p.payload for p in allpoints if p.payload.get('source')=='evotor/fn/fn-234.md'],'cases':rows}
 report['raw_question_limits']='raw_question_* use frozen first-turn text, not generated RAG query/state; they probe retrieval only and are not LIVE or final-answer cross-service validation. Reserved holdout was not probed.'
 (ROOT/'reports/b2_2c_20261104/retrieval_counterfactual_extended.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 client.close()

if __name__=='__main__': main()
