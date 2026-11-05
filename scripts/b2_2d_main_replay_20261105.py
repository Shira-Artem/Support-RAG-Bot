"""Replay saved provider JSON through candidate validation/reducer and Stage3.

This is offline counterfactual evidence, never a new independent LIVE result.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['HF_HUB_OFFLINE']='1'
from dotenv import load_dotenv
load_dotenv(Path(os.environ.get('B22D_ENV_PATH', ROOT / '.env')),override=False)
from qdrant_client import QdrantClient
from app.embeddings import SentenceTransformerEmbedding
from app.vector_store import QdrantStore
from app.retrieval import Retriever
from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueState,DialogueManager
from app.dialogue_understanding import validate_response
from app.rag_query import build_rag_query
from b2_2c_live_harness import ReadOnlyQdrant

def main():
    client=QdrantClient(url=os.getenv('QDRANT_URL','http://127.0.0.1:6333'))
    rag=RetrieverRAGAdapter(Retriever(QdrantStore(ReadOnlyQdrant(client),SentenceTransformerEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'),'knowledge_stage3_retrieval_20261022')))
    rows=[]
    for filename,ids in [('b22d_regressions_live.json',{'b01','h08','m01'}),('b22d_baseline_resume1_live.json',{'d10','d11'}),('bounded_live_20261105.json',{'u01','u02'})]:
        data=json.loads((ROOT/'reports/b2_2d_20261105'/filename).read_text(encoding='utf-8'))
        states={}
        for turn in data['turns']:
            cid=turn['case']
            if cid not in ids: continue
            before=states.get(cid,DialogueState())
            call=data['understanding_calls'][turn['understanding_call_indices'][-1]]
            raw=call['structured_output']
            _,_,unknown,obs=validate_response(raw,turn['question'],turn['turn'],before)
            state=DialogueManager().advance(before,turn['question'],turn['turn'],observation=obs,unknown_facts=list(unknown))
            states[cid]=state
            query=build_rag_query(state)
            result=rag.search_for_state(state,query)
            row=dict(case=cid,turn=turn['turn'],task_frame=state.to_dict(),same_task=before.task_id==state.task_id,query=query,retrieval=result.diagnostics())
            rows.append(row)
            print(cid,turn['turn'],state.intent,state.operation,state.routing_service,result.sufficient,result.insufficiency_reason,[c.source for c in result.candidates if c.selected],flush=True)
    output=dict(kind='Offline saved-provider-JSON replay, real read-only Stage3, no LLM; not LIVE AFTER',rows=rows,source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app').glob('*.py')})
    (ROOT/'reports/b2_2d_20261105/main_merge_replay_20261105.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    client.close()

if __name__=='__main__': main()

