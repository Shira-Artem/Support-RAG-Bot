"""Real Groq execution of separately frozen independent holdout / controls."""
import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from b2_2c_live_harness import CASES, run

ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--suite',choices=['holdout','controls'],required=True)
    parser.add_argument('--cases')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    filename='holdout_frozen.json' if args.suite=='holdout' else 'negative_controls_frozen.json'
    frozen=json.loads((ROOT/'reports/b2_2c_20261104'/filename).read_text(encoding='utf-8'))
    CASES.update({case['id']:case['turns'] for case in frozen['cases']})
    if args.cases:
        baseline=json.loads((ROOT/'reports/b2_2c_20261104/baseline_frozen_v2.json').read_text(encoding='utf-8'))
        CASES.update({case['id']:case['turns'] for case in baseline['cases']
                      if case['id'] in args.cases.split(',')})
    asyncio.run(run(SimpleNamespace(cases=args.cases or ','.join(case['id'] for case in frozen['cases']),
                                   output=args.output,pause=12)))
