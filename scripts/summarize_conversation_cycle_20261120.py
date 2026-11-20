"""Build comparison tables from frozen scenarios and explicit human assessments."""
import collections
import csv
import gzip
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/manual_checkpoint_20261120'


def main():
    reviews=json.loads((OUT/'live_assessments.json').read_text(encoding='utf-8'))
    grades={(r['variant'],r['case'],r['turn']):r for r in reviews}
    names={'baseline':['baseline','baseline-supplement','baseline-rest'],
        'candidate_pre_safety':['candidate','candidate-rest'],'old_kb_pre_safety':['old-kb']}
    variants={};summary={}
    for variant,runs in names.items():
        rows={};http=[];cost=0;attempts=0
        for name in runs:
            with gzip.open(OUT/'live'/(name+'.json.gz'),'rt',encoding='utf-8') as f:r=json.load(f)
            attempts+=len(r['turns']);http+=r['provider_http'];cost+=r['reported_cost_kopecks']
            for t in r['turns']:rows.setdefault((t['case'],t['turn']),(name,t))
        variants[variant]=rows
        lat=[t['latency_ms'] for _,t in rows.values()]
        summary[variant]=dict(unique_turns=len(rows),attempts=attempts,
            grades=dict(collections.Counter(grades[(variant,c,n)]['grade'] for c,n in rows)),
            http_status_counts=dict(collections.Counter(str(h.get('status')) for h in http)),
            reported_cost_kopecks=cost,reported_tokens=sum(h.get('total_tokens') or 0 for h in http),
            latency_median_ms=round(statistics.median(lat)),latency_max_ms=max(lat),
            sqlite_reopen_equal=sum(t['sqlite_reopen_equal'] for _,t in rows.values()),
            full_quality_go=False)
    manifest=json.loads((OUT/'scenarios.json').read_text(encoding='utf-8'))
    rows=[]
    for scenario in manifest['scenarios']:
        for n,q in enumerate(scenario['messages'],1):
            item=dict(case=scenario['id'],turn=n,cohort=scenario['cohort'],question=q)
            for variant,data in variants.items():
                run,t=data[(scenario['id'],n)];d=t.get('diagnostics') or {}
                item[variant]=dict(grade=grades[(variant,scenario['id'],n)]['grade'],
                    reason=d.get('scenario_reason'),latency_ms=t['latency_ms'],run=run,
                    per_turn_reported_cost_kopecks=sum(
                        loads(run)['provider_http'][i].get('cost_kopecks') or 0
                        for i in t['provider_http_indices']) if 'provider_http_indices' in t else None)
            rows.append(item)
    (OUT/'comparison.json').write_text(json.dumps(dict(summary=summary,turns=rows,
        limitations=['Editorial developer evaluation; no independent or frozen holdout gate.',
            'Baseline first attempt per row; two duplicate explain attempts remain in raw evidence and totals.',
            'KB A/B uses identical 37 app hashes, provider/model/effort and inputs; model-only turns do not depend on KB.',
            'Single pass is confounded by provider/semantic variance; no general improvement inferred.',
            'Final safety patch is a later phase; do not assign pre-safety 65-turn score to it.',
            'Missing baseline per-turn cost/HTTP indices remain null. All costs are reported usage, not an invoice.']),ensure_ascii=False,indent=2),encoding='utf-8')
    md=['# Сравнение реальных LIVE-ответов','',
        'Baseline/current KB → candidate до safety repair/current KB → тот же candidate/pre-B2 KB. '
        'Проверенный input/prompt/code contract важнее суммарного счёта. Candidate дал критическую опасную инструкцию и NO-GO.','',
        '| Вариант | Planned unique / attempts | PASS / PARTIAL / FAIL | Reported коп. | Медиана / max ms |',
        '|---|---:|---:|---:|---:|']
    for v,s in summary.items():
        g=s['grades'];md.append(f"| {v} | {s['unique_turns']} / {s['attempts']} | {g.get('PASS',0)} / {g.get('PARTIAL',0)} / {g.get('FAIL',0)} | {s['reported_cost_kopecks']} | {s['latency_median_ms']} / {s['latency_max_ms']} |")
    md += ['', '## Все 65 одинаковых ходов','', '| Сценарий / ход | Baseline | Candidate | Pre-B2 KB |','|---|---|---|---|']
    for t in rows:md.append('| '+f"{t['case']} / {t['turn']}"+' | '+' | '.join(t[v]['grade'] for v in variants)+' |')
    md += ['', 'Причины, задержки и стоимость по каждому доступному ходу: [comparison.json](comparison.json). '
        'Дословные ответы/запросы/HTTP/полный state — в [live](live/), оценки с оговорками — [live_assessments.json](live_assessments.json).',
        '', '65-turn таблица относится к версии ДО последнего safety repair. Финальные 26+9 проверок сохранены отдельно; они не заменяют отрицательные первые ответы.']
    (OUT/'comparison.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    with (OUT/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['case','turn','question',*variants])
        for t in rows:w.writerow([t['case'],t['turn'],t['question'],*(t[v]['grade'] for v in variants)])
    print(json.dumps(summary,ensure_ascii=False))


_CACHE={}
def loads(run):
    if run not in _CACHE:
        with gzip.open(OUT/'live'/(run+'.json.gz'),'rt',encoding='utf-8') as f:_CACHE[run]=json.load(f)
    return _CACHE[run]


if __name__=='__main__':main()
