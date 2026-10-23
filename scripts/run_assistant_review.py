"""Explicit live QA run. Synthetic data never enters human reviews or Qdrant.

Running this command makes real paid provider calls. Pytest must not invoke it.
Each result is committed immediately; --batch resumes an interrupted run.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB = ROOT / 'data/evaluations/expert_reviews.sqlite3'


def verify_retriever_collection(service, expected: str) -> str:
    """Verify the collection actually bound to the constructed retriever."""
    actual = getattr(getattr(getattr(service, 'rag', None), 'retriever', None), 'store', None)
    actual = getattr(actual, 'collection', None)
    if actual != expected:
        raise RuntimeError(
            f"Retriever collection mismatch: expected {expected!r}, actual {actual!r}. "
            "Abort before Groq; set the process-only QDRANT_COLLECTION explicitly."
        )
    return actual


def encoded(value):
    return json.dumps(value, ensure_ascii=False)


def connect(path=DB):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def backup_databases(stamp):
    target = Path(os.environ['LOCALAPPDATA']) / 'Support-RAG-Bot/backups' / ('assistant-review-' + stamp)
    target.mkdir(parents=True, exist_ok=False)
    for source in (ROOT / 'data/conversations.sqlite3', DB):
        if not source.is_file():
            continue
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original:
            with sqlite3.connect(target / source.name) as copy:
                original.backup(copy)
                assert copy.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    print('BACKUP', target, flush=True)


def prepare(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS assistant_review_batches(
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL,
            config_json TEXT NOT NULL, source_snapshot_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assistant_review_cases(
            batch_id TEXT NOT NULL, case_id TEXT NOT NULL, case_json TEXT NOT NULL,
            conversation_id TEXT NOT NULL, PRIMARY KEY(batch_id,case_id));
        CREATE TABLE IF NOT EXISTS assistant_review_attempts(
            id INTEGER PRIMARY KEY, batch_id TEXT NOT NULL, case_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL, created_at TEXT NOT NULL, query TEXT NOT NULL,
            state_json TEXT NOT NULL, answer_json TEXT NOT NULL,
            UNIQUE(batch_id,case_id,turn_index));
        CREATE TABLE IF NOT EXISTS assistant_review_grades(
            attempt_id INTEGER PRIMARY KEY, reviewer_kind TEXT NOT NULL DEFAULT 'assistant',
            score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 10),
            verdict TEXT NOT NULL, error_layer TEXT, comment TEXT NOT NULL,
            corrected_answer TEXT NOT NULL, human_approved INTEGER NOT NULL DEFAULT 0);
    ''')


def export(batch):
    output = ROOT / 'data/evaluations/assistant_review' / batch
    output.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        cases = {r['case_id']: json.loads(r['case_json']) for r in db.execute(
            'SELECT * FROM assistant_review_cases WHERE batch_id=?', (batch,))}
        records = [dict(r) for r in db.execute('''SELECT a.*,g.score,g.verdict,g.error_layer,g.comment,
            g.corrected_answer,g.human_approved FROM assistant_review_attempts a
            LEFT JOIN assistant_review_grades g ON g.attempt_id=a.id
            WHERE a.batch_id=? ORDER BY a.id''', (batch,))]
    lines = ['# Разбор синтетических диалогов', '',
             'Настоящие Qdrant и LLM; транспорт Telegram не вызывается. Оценки — помощника, не специалиста.',
             'Это кандидаты для последующей проверки. Одобрения человеком и автоматического обучения нет.', '']
    from collections import Counter
    verdicts = Counter(r.get('verdict') or 'unreviewed' for r in records)
    scores = [r['score'] for r in records if r.get('score') is not None and r.get('verdict') != 'technical_error']
    lines += ['## Оценки помощника', '',
              ' | '.join(f'{kind}: {count}' for kind, count in sorted(verdicts.items())),
              f"Средняя оценка: {sum(scores) / len(scores):.2f}/10." if scores else 'Ответы ещё не оценены.', '',
              'Оценка отражает полезность и соответствие локальным карточкам; внешняя актуальность draft-источников не подтверждена.', '']
    calls = tokens = 0
    for record in records:
        a = json.loads(record['answer_json'])
        s = json.loads(record['state_json'])
        expectation = cases[record['case_id']]['turns'][record['turn_index']]
        from app.dialogue_state import DialogueState
        service = DialogueState.from_dict(s).routing_service
        calls += int(a.get('llm_call_attempted', False))
        tokens += a.get('total_tokens') or 0
        retrieval = a.get('retrieval_diagnostics') or {}
        context = retrieval.get('context') or ''
        sources = list(dict.fromkeys(re.findall(r'^\[Источник: ([^;\n]+)', context, re.M)))
        lines += [f"## {record['case_id']} / {record['turn_index'] + 1} (запись {record['id']})", '',
                  record['query'], '',
                  f"Задача: {s.get('intent')}/{s.get('operation')}; сервис: {service}; переход: {s.get('transition')}.",
                  f"Генерация: {a['generation_status']}; LLM: {a.get('llm_call_attempted')}; модель: {a.get('model')}; effort: {a.get('reasoning_effort')}; токены: {a.get('total_tokens')}.",
                  f"Валидация: {a.get('validation_status')}; {a.get('validation_reason')}. Ошибка API: {a.get('generation_error')}",
                  f"Поисковый запрос: {a.get('rag_query')}", '',
                  '**Источники подготовленного контекста**' + ('' if a.get('llm_call_attempted') else ' (LLM не вызывалась)'), '',
                  *(['- ' + name for name in sources] or ['- Нет']), '',
                  '**Отклонённые источники и причины**', '',
                  *([f"- {item['source']}: {', '.join(item.get('reasons') or [])}"
                     for item in retrieval.get('rejected', [])] or ['- Нет']), '',
                  '**Ответ клиенту**', '', a['text'], '',
                  '**Ожидаемое поведение по локальной карточке (не одобрено человеком)**', '', expectation['reference_answer'], '',
                  f"**Оценка помощника:** {record.get('score') or 'ожидает разбора'}; {record.get('verdict') or ''}; {record.get('error_layer') or ''}",
                  record.get('comment') or '', '', '**Уточнённый ориентир после разбора**', '',
                  record.get('corrected_answer') or '(ещё не разобрано)', '',
                  '**Исходный ответ LLM**', '', '```', a.get('raw_model_text') or '(без вызова)', '```', '',
                  '<details><summary>Точный текст подготовленного контекста</summary>', '', '```text', context or '(пусто)', '```', '</details>', '',
                  '<details><summary>Состояние, источники и фактический контекст</summary>', '', '```json',
                  json.dumps({'state': s, 'retrieval': a.get('retrieval_diagnostics'), 'repair': a.get('response_repair')}, ensure_ascii=False, indent=2),
                  '```', '</details>', '']
    lines.insert(5, f'Сохранено ответов: {len(records)}. Вызовов API: {calls}. Известный расход: {tokens} токенов (reasoning включён).')
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    (output / 'results.jsonl').write_text('\n'.join(encoded(r) for r in records) + '\n', encoding='utf-8')
    return output


def import_reviews(batch, path):
    """Import deliberate assistant review, never human approval or expert scores."""
    reviews = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    with connect() as db:
        for review in reviews:
            row = db.execute('SELECT id FROM assistant_review_attempts WHERE batch_id=? AND case_id=? AND turn_index=?',
                             (batch, review['case_id'], review['turn_index'])).fetchone()
            if row is None:
                raise ValueError('Review refers to an absent attempt')
            if review['verdict'] not in {'pass', 'partial', 'fail', 'technical_error'}:
                raise ValueError('Unknown review verdict')
            db.execute('''INSERT INTO assistant_review_grades(attempt_id,score,verdict,error_layer,comment,corrected_answer)
                VALUES(?,?,?,?,?,?) ON CONFLICT(attempt_id) DO UPDATE SET
                score=excluded.score,verdict=excluded.verdict,error_layer=excluded.error_layer,
                comment=excluded.comment,corrected_answer=excluded.corrected_answer''',
                (row['id'], review['score'], review['verdict'], review.get('error_layer'),
                 review['comment'], review['corrected_answer']))
    return export(batch)


async def run(args):
    from app import answer_service
    from app.compat import build_answer_rag
    from app.config import get_settings
    from app.conversation_store import ConversationStore
    from qdrant_client import QdrantClient

    settings = get_settings()
    # Explicitly guard this operator-authorized run against a changed backend/model.
    assert settings.llm_provider == 'groq' and settings.groq_model == 'openai/gpt-oss-20b'
    assert settings.groq_reasoning_effort == 'medium'
    assert os.getenv('RAG_BACKEND', 'qdrant') == 'qdrant'
    collection = os.getenv('QDRANT_COLLECTION', 'knowledge_demo')
    expected_collection = args.expected_collection or collection
    client = QdrantClient(url=os.getenv('QDRANT_URL', 'http://127.0.0.1:6333'), timeout=15)
    info = client.get_collection(collection)  # fail before constructors; never create a collection
    print('QDRANT', collection, info.points_count, info.status, flush=True)
    # Construct and inspect the same retriever that will serve the run.  This
    # catches a stage2/stage3 mismatch that an environment-variable check alone
    # cannot catch, before backups, persistence, or any provider call.
    service = answer_service.AnswerService(build_answer_rag(settings.docs_dir), settings)
    collection = verify_retriever_collection(service, expected_collection)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    batch = args.batch or stamp
    backup_databases(stamp)
    cases = [json.loads(line) for line in args.scenarios.read_text(encoding='utf-8').splitlines() if line.strip()]
    snapshots = {}
    for case in cases:
        for name in case['reference_documents']:
            path = ROOT / 'data/knowledge' / name
            body = path.read_text(encoding='utf-8')
            snapshots[name] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), text=body)
    config = dict(provider=settings.llm_provider, model=settings.groq_model, reasoning_effort=settings.groq_reasoning_effort,
                  collection=collection, points=info.points_count, synthetic=True, human_approved=False,
                  code_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (ROOT / 'app').glob('*.py')})
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        prepare(db)
        db.execute('INSERT OR IGNORE INTO assistant_review_batches VALUES(?,?,?,?,?)',
                   (batch, datetime.now(timezone.utc).isoformat(), 'running', encoded(config), encoded(snapshots)))
        db.execute("UPDATE assistant_review_batches SET status='running' WHERE id=?", (batch,))
    store = ConversationStore(ROOT / '.local' / f'assistant-conversations-{batch}.sqlite3')
    # Recovery is local to this synthetic DB, and never touches Telegram histories.
    store.recover_pending()
    original = answer_service.generate
    last_call = 0.0
    recent = []

    async def paced_generate(messages, settings):
        nonlocal last_call
        estimate = sum(len(m['content']) for m in messages) // 3 + 512
        while True:
            now = time.monotonic()
            recent[:] = [(t, n) for t, n in recent if now - t < 65]
            delay = max(0, 16 - (now - last_call))
            if recent and sum(n for _, n in recent) + estimate > 6000:
                delay = max(delay, 66 - (now - recent[0][0]))
            if delay <= 0:
                break
            await asyncio.sleep(min(delay, 20))
        last_call = time.monotonic()
        result = await original(messages, settings)
        recent.append((time.monotonic(), result.total_tokens or estimate))
        return result

    answer_service.generate = paced_generate
    consecutive_errors = 0
    try:
        for case_number, case in enumerate(cases):
            with connect() as db:
                row = db.execute('SELECT * FROM assistant_review_cases WHERE batch_id=? AND case_id=?', (batch, case['id'])).fetchone()
                if row:
                    assert encoded(case) == row['case_json'], 'Cannot change cases inside a resumed batch'
                    cid = row['conversation_id']
                else:
                    cid = store.new(-1000 - case_number, -1000 - case_number)
                    db.execute('INSERT INTO assistant_review_cases VALUES(?,?,?,?)', (batch, case['id'], encoded(case), cid))
            for index, turn in enumerate(case['turns']):
                with connect() as db:
                    if db.execute('SELECT 1 FROM assistant_review_attempts WHERE batch_id=? AND case_id=? AND turn_index=?', (batch, case['id'], index)).fetchone():
                        continue
                pending = store.begin(cid, turn['query'])
                state = store.dialogue_state(cid)
                answer = await service.answer(turn['query'], state=state)
                store.complete(pending, answer)
                with connect() as db:
                    db.execute('INSERT INTO assistant_review_attempts(batch_id,case_id,turn_index,created_at,query,state_json,answer_json) VALUES(?,?,?,?,?,?,?)',
                               (batch, case['id'], index, datetime.now(timezone.utc).isoformat(), turn['query'], encoded(state.to_dict()), encoded(asdict(answer))))
                export(batch)
                print(encoded(dict(case=case['id'], turn=index+1, query=turn['query'], answer=answer.text,
                                   generation=answer.generation_status, validation=answer.validation_reason,
                                   tokens=answer.total_tokens, error=answer.generation_error)), flush=True)
                consecutive_errors = consecutive_errors + 1 if answer.generation_status == 'error' else 0
                if consecutive_errors >= 3:
                    raise RuntimeError('Three consecutive provider errors; saved partial run, no automatic retries')
        with connect() as db:
            db.execute("UPDATE assistant_review_batches SET status='complete' WHERE id=?", (batch,))
    except BaseException:
        with connect() as db:
            db.execute("UPDATE assistant_review_batches SET status='interrupted' WHERE id=?", (batch,))
        raise
    finally:
        answer_service.generate = original
        print('REPORT', export(batch), flush=True)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenarios', type=Path, default=ROOT / 'data/assistant_review_scenarios.jsonl')
    parser.add_argument('--batch', help='Resume an existing batch or name a new batch')
    parser.add_argument('--export', action='store_true', help='Only regenerate the local report; no API calls')
    parser.add_argument('--reviews', type=Path, help='Import assistant grades from JSONL; no API calls')
    parser.add_argument('--expected-collection', help='Abort unless the constructed retriever uses this exact Qdrant collection')
    args = parser.parse_args()
    if args.reviews:
        assert args.batch, '--reviews requires --batch'
        print(import_reviews(args.batch, args.reviews))
    elif args.export:
        assert args.batch, '--export requires --batch'
        print(export(args.batch))
    else:
        asyncio.run(run(args))


if __name__ == '__main__':
    main()
