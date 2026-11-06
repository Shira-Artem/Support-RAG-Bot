import json, sys, tempfile
from pathlib import Path
from pytest import MonkeyPatch
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from test_telegram_pilot_sqlite_replay import _run_replay
p=json.loads(Path('reports/b2_2d_20261106/p01_coverage_live_20261106_transfer.json').read_text(encoding='utf8'))
t=[x for x in p['turns'] if x['case']=='P01_transfer_time']
c=[{'id':str(x['turn']),'text':x['question'],'provider_raw':p['understanding_calls'][x['understanding_call_indices'][-1]]['structured_output']} for x in t]
plans={i:json.loads(p['generation_calls'][x['generation_call_indices'][0]]['result']['text']) for i,x in enumerate(t,1) if x['generation_call_indices']}
for plan in plans.values(): plan['source_order_complete']=True
m=MonkeyPatch()
try:
 with tempfile.TemporaryDirectory() as d:
  result=_run_replay(m,Path(d),c,sources=('evotor/fn/fn-234.md',),coordinator_enabled=True,validate_with_state=True,planner_overrides=plans)
  Path('reports/b2_2d_20261106/p01_final_unsafe_counterfactual.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
  for x in result: print(x['turn'],x['reason'],x['final_reply'])
finally: m.undo()
