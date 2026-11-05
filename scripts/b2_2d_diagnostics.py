"""Read preserved traces, no model calls or mutable stores."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'reports/b2_2d_20261105'

def main():
    rows=[]
    for name,ids in [('b22c_holdout_final_live.json',{'h01','h05','h06','h07','h08','h10'}),('b22c_after_final_live.json',{'b01','s01','m01'})]:
        data=json.loads((ROOT/'reports/b2_2c_20261104'/name).read_text(encoding='utf-8'))
        for turn in data['turns']:
            if turn['case'] not in ids: continue
            obs=(turn['understanding'][0] or {}).get('observation',{})
            diagnostics=turn['diagnostics'] or {}
            retrieval=diagnostics.get('retrieval_diagnostics') or {}
            calls=[data['generation_calls'][i] for i in turn['generation_call_indices']]
            rows.append(dict(case=turn['case'],turn=turn['turn'],question=turn['question'],answer=turn['answer'],
                trace='../b2_2c_20261104/'+name,understanding=obs,task_frame=turn['task_frame'],
                previous_frame=turn['state_before'],retrieval=retrieval,planner_calls=calls,
                result_reason=diagnostics.get('scenario_reason')))
    (DEST/'regression_diagnostics.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    protected=[ROOT/'.env',*sorted((ROOT/'data/knowledge').rglob('*')),*sorted((ROOT/'reports/b2_2c_20261104/kb_drafts').rglob('*'))]
    receipt={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.is_file()}
    p=DEST/'protected_before.json'
    assert not p.exists()
    p.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('Saved',len(rows),'regression turns;',len(receipt),'protected hashes (no contents)')

if __name__=='__main__': main()
