import asyncio, json
from types import SimpleNamespace
from pathlib import Path
from b2_2d_bounded_live_20261105 import CASES, run
root=Path(__file__).resolve().parents[1]
folder=root/'reports/b2_2d_20261105'
for name in ('regressions_frozen.json','holdout_frozen.json'):
    data=json.loads((folder/name).read_text(encoding='utf-8'))
    for case in data['cases']:
        if case['id'] in {'m01','u01','u02'}:
            CASES[case['id']]=case['turns']
assert set(('m01','u01','u02')) <= CASES.keys()
asyncio.run(run(SimpleNamespace(cases='m01,u01,u02', output='reports/b2_2d_20261105/bounded_live_20261105.json',pause=12,runtime_dir=None)))
