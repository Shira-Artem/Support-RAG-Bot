"""Replay a frozen manifest through the existing real HTTP handler harness."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, default=ROOT/'reports/manual_checkpoint_20261120/scenarios.json')
    p.add_argument('--cohort', default='manual,additional')
    p.add_argument('--cases', help='Optional comma-separated IDs, preserving manifest order')
    p.add_argument('--kb', choices=['current', 'pre_b2'], default='current')
    p.add_argument('--source-root', type=Path, help='Required matching pre-B2 checkout, never the current source root')
    p.add_argument('--code-root', type=Path, help='Optional immutable app snapshot for baseline completion')
    p.add_argument('--revision', help='Git revision of an archived runtime')
    p.add_argument('--resume', action='store_true', help='Continue next planned turn with the same saved SQLite and unchanged app/profile')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env', override=False)
    os.environ.update(LLM_PROVIDER='hubris', HUBRIS_MODEL='openai/gpt-oss-20b',
        HUBRIS_REASONING_EFFORT='low', SEMANTIC_COMPOSER_ENABLED='1',
        PYTHONUTF8='1', HF_HUB_OFFLINE='1', DOCS_DIR=str(ROOT/'data/knowledge'))
    if a.code_root:
        sys.path.insert(0, str(a.code_root.resolve()))
    # SourceFirst verifies actual files in rag.root. The loader's legacy docs
    # path and the KB's validation root are distinct in the existing adapter.
    import app.config as config
    original_settings = config.get_settings
    source_root = ROOT
    if a.kb == 'pre_b2':
        if not a.source_root or not (a.source_root/'data/knowledge').is_dir():
            p.error('--source-root must contain the matching pre-B2 KB')
        source_root = a.source_root.resolve()
    config.get_settings = lambda: replace(original_settings(), docs_dir=source_root/'data/docs')
    from scripts import run_telegram_equivalent_live as live
    manifest = json.loads(a.manifest.read_text(encoding='utf-8'))
    cohort = set(a.cohort.split(','))
    selected = [s for s in manifest['scenarios'] if s['cohort'] in cohort
        and (not a.cases or s['id'] in a.cases.split(','))]
    if not selected:
        p.error('No selected scenarios')
    for s in selected:
        live.CASES[s['id']] = s['messages']
    cli = SimpleNamespace(cases=','.join(s['id'] for s in selected), output=str((ROOT/a.output).resolve()),
        pause=0, revision=a.revision, max_cost_kopecks=1500,
        continue_after_understanding_shape_error=True,
        resume=a.resume,
        collection='knowledge_kb_b2_integrated_20261119' if a.kb=='current' else 'knowledge_kb_b2_base_20261119',
        expected_points=833 if a.kb=='current' else 672)
    asyncio.run(live.run(cli))


if __name__ == '__main__':
    main()
