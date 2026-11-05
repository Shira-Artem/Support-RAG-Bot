import asyncio, json
from types import SimpleNamespace
from pathlib import Path
from b2_2d_evidence_live import CASES, run
root=Path(__file__).resolve().parents[1]
folder=root/'reports/b2_2d_20261105'
for name in ('regressions_frozen.json','baseline_frozen.json'):
    data=json.loads((folder/name).read_text(encoding='utf-8'))
    for case in data['cases']:
        if case['id'] in {'b01','h08','d10','d11'}:
            CASES[case['id']]=case['turns']
assert set(('b01','h08','d10','d11')) <= CASES.keys()
asyncio.run(run(SimpleNamespace(cases='b01,h08,d10,d11', output='reports/b2_2d_20261105/evidence_contract_live.json',pause=12,runtime_dir=None)))
