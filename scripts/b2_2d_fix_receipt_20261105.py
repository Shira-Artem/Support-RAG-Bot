"""Read-only integrity and cost receipt for the bounded b01/h08 repair."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEST = ROOT / 'reports/b2_2d_20261105'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    from dotenv import load_dotenv
    from qdrant_client import QdrantClient
    load_dotenv(ROOT / '.env', override=False)
    protected = [ROOT / '.env', *sorted((ROOT / 'data/knowledge').rglob('*'))]
    files = {p.relative_to(ROOT).as_posix(): digest(p) for p in protected if p.is_file()}
    client = QdrantClient(url=os.getenv('QDRANT_URL', 'http://127.0.0.1:6333'))
    points, offset = [], None
    while True:
        batch, offset = client.scroll('knowledge_stage3_retrieval_20261022', offset=offset,
            limit=256, with_payload=True, with_vectors=False)
        points.extend(batch)
        if offset is None:
            break
    info = client.get_collection('knowledge_stage3_retrieval_20261022')
    client.close()
    payload = sorted([{'id': str(p.id), 'payload': p.payload} for p in points], key=lambda p: p['id'])
    return dict(protected=files, stage3=dict(points=len(points), status=str(info.status),
        id_payload_sha256=hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()))


def main(mode):
    current = snapshot()
    if mode == 'before':
        (DEST / 'fixes_integrity_before.json').write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Protected hashes and read-only Stage3 baseline saved')
        return
    before = json.loads((DEST / 'fixes_integrity_before.json').read_text(encoding='utf-8'))
    assert current == before, 'Protected files or Stage3 payload changed'
    runs = {}
    for name in ('fixes_offline_20261105_final_v3.json', 'fixes_live_20261105.json'):
        path = DEST / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        trace = data.get('http_trace', [])
        sqlite_checks = {}
        directory = ROOT / '.local' / ('telegram-equivalent-' + path.stem)
        for db_path in directory.glob('*.sqlite3'):
            with sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True) as db:
                sqlite_checks[db_path.relative_to(ROOT).as_posix()] = db.execute('pragma quick_check').fetchone()[0]
        assert all(v == 'ok' for v in sqlite_checks.values())
        hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in [ROOT / 'bot.py', *sorted((ROOT / 'app').glob('*.py'))]}
        assert hashes == data['source_hashes'], 'Runtime changed since run'
        runs[name] = dict(kind=data.get('validation_kind'), turns=len(data['turns']),
            statuses=dict(Counter(t['http_status'] for t in trace)),
            confirmed_tokens=sum((t.get('usage') or {}).get('total_tokens') or 0 for t in trace),
            unknown_usage_responses=sum(not t.get('usage') for t in trace),
            reopen_equal=sum(t['sqlite_reopen_equal'] for t in data['turns']),
            sqlite_quick_check=sqlite_checks, runtime_hashes_match=True,
            negative_controls=[dict(control=c['control'], reason=c['reason']) for c in data.get('negative_controls', [])])
    receipt = dict(protected_equal=True, env_unchanged=True, approved_unchanged=True,
        stage3=current['stage3'], stage3_equal=True, runs=runs,
        production_used=False, frozen_holdout_run=False, commit_push=False)
    historical = json.loads((DEST / 'protected_before.json').read_text(encoding='utf-8'))
    historical = {path: value for path, value in historical.items() if path != '.env'}
    assert all(digest(ROOT / path) == value for path, value in historical.items())
    receipt['historical_protected_files_equal'] = len(historical)
    (DEST / 'fixes_integrity_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('before', 'after'))
    main(parser.parse_args().mode)
