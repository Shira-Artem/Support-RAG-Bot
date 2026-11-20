"""Publish synthetic LIVE evidence without credentials or provider identifiers."""
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sanitize(value, key=''):
    if key in {'api_call_id', 'system_fingerprint'}:
        return '[REDACTED_PROVIDER_ID]' if value else None
    if key == 'id' and isinstance(value, str) and value.startswith(('chatcmpl-', 'gen-')):
        return '[REDACTED_PROVIDER_ID]'
    if isinstance(value, dict):
        return {k: sanitize(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'(?i)(?:\d{6,}:[\w-]{20,}|(?:sk-|gsk_)[\w-]{20,}|Bearer\s+[^\s,;]+)', '[SECRET]', value)
        value = re.sub(r'(?i)[A-Z]:[\\/]Users[\\/][^\\/\s"<>]+', '[USER_HOME]', value)
    return value


def export(source: Path, output: Path):
    r = sanitize(json.loads(source.read_text(encoding='utf-8')))
    output.mkdir(parents=True, exist_ok=True)
    name = source.stem
    packed = output/(name+'.json.gz')
    with gzip.GzipFile(filename=str(packed), mode='wb', mtime=0) as f:
        f.write(json.dumps(r,ensure_ascii=False,separators=(',',':')).encode())
    answers = ['# '+name+' — дословные LIVE-ответы', '',
        'Только Telegram transport перехвачен. Модельные ответы получены настоящими HTTP Hubris; retrieval — Qdrant.', '']
    for t in r['turns']:
        answers += [f"## {t['case']} / {t['turn']}", '', t['question'], '', t['answer'], '',
            f"Latency: {t['latency_ms']} ms; reason: {(t.get('diagnostics') or {}).get('scenario_reason')}", '']
    (output/(name+'_answers.md')).write_text('\n'.join(answers), encoding='utf-8')
    metrics = dict(name=name,head=r['head'],collection=r['collection'],model=r['model'],
        reasoning_effort=r['reasoning_effort'],turns=len(r['turns']),
        http_status_counts={str(status):sum(h.get('status')==status for h in r['provider_http'])
            for status in {h.get('status') for h in r['provider_http']}},
        reported_cost_kopecks=r['reported_cost_kopecks'],
        reported_total_tokens=sum(h.get('total_tokens') or 0 for h in r['provider_http']),
        sqlite_reopen_equal=sum(t['sqlite_reopen_equal'] for t in r['turns']),
        error_turns=[dict(case=t['case'],turn=t['turn'],reason=t['diagnostics'].get('scenario_reason'))
            for t in r['turns'] if (t.get('diagnostics') or {}).get('generation_status')=='error'],
        trace_file=packed.name,trace_sha256=sha256(packed.read_bytes()).hexdigest(),
        raw_trace_completeness='Initial baseline harness did not save every HTTP request/response or per-turn HTTP indices; no missing trace reconstructed.'
            if any('provider_http_indices' not in t for t in r['turns']) else 'HTTP payloads, timing and per-turn indices captured; transport exceptions recorded separately.')
    (output/(name+'_metrics.json')).write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    return metrics


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sources',nargs='+',type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'reports/manual_checkpoint_20261120/live')
    a=p.parse_args()
    for source in a.sources:
        m=export(source,a.output)
        print(json.dumps({k:m[k] for k in ('name','turns','http_status_counts','reported_cost_kopecks')}))
