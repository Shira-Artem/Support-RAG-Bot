"""Read-only export of the seven reported Telegram turns (no application I/O)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/incidents/2026-10-21'


def export():
    OUT.mkdir(parents=True, exist_ok=True)
    path = ROOT / 'data/conversations.sqlite3'
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    turns = []
    for uid in (49, 51, 53, 55, 57, 59, 61):
        user = dict(db.execute('SELECT * FROM messages WHERE id=?', (uid,)).fetchone())
        assistant = dict(db.execute('SELECT * FROM messages WHERE id=?', (uid + 1,)).fetchone())
        diagnostic = json.loads(assistant.pop('diagnostics_json') or '{}')
        saved = db.execute('SELECT state_json FROM dialogue_turns WHERE message_id=?', (uid,)).fetchone()
        previous = db.execute('SELECT * FROM messages WHERE conversation_id=? AND role=\'assistant\' '
                              'AND id<? ORDER BY id DESC LIMIT 1', (user['conversation_id'], uid)).fetchone()
        before = json.loads(previous['diagnostics_json']) if previous else {}
        turns.append(dict(user=user, assistant=assistant, diagnostics=diagnostic,
                          before_user_snapshot=before.get('dialogue_state'),
                          before_answer_metadata={k: before.get(k) for k in
                              ('scenario', 'scenario_reason', 'clarification_slot', 'text')},
                          after_user_snapshot=json.loads(saved[0]) if saved else None))
    db.close()
    protected = [*ROOT.glob('data/*.sqlite3'), *ROOT.glob('data/evaluations/**/*')]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in protected if p.is_file()}
    payload = dict(turns=turns, protected_file_sha256=hashes,
                   notes=['Read-only SQLite export; historical data, not regenerated model output.',
                          'before_user_snapshot is the previous saved user state, before observing its answer.',
                          'Apply before_answer_metadata to expected only; no assistant facts become entities.',
                          'null before_user_snapshot means the first turn of a new conversation.'])
    (OUT / 'historical.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Историческая трассировка, 21.10.2026', '',
             'Время в SQLite — UTC; 12:29–12:30 UTC = 15:29–15:30 МСК. '
             'Все 7 сообщений найдены: user id 49–61, ответы 50–62. '
             'JSON рядом содержит полные исходные diagnostics без сокращения.', '',
             'До сообщения показан предыдущий сохранённый снимок пользователя и метаданные ответа: '
             'scenario=clarify устанавливает expected, прочие сценарии очищают expected. '
             'Для первого сообщения начальное пустое состояние следует из новой conversation; '
             'отдельный начальный снимок в SQLite не хранится.', '']
    for t in turns:
        d = t['diagnostics']; r = d.get('retrieval_diagnostics') or {}
        lines += [f"## Сообщение {t['user']['id']}: {t['user']['content']}", '',
                  f"Conversation: `{t['user']['conversation_id']}`; UTC: {t['user']['created_at']}", '']
        sections = [('Состояние до (предыдущий сохранённый снимок)', t['before_user_snapshot']),
                    ('Ответ перед сообщением / переход expected', t['before_answer_metadata']),
                    ('Состояние после сообщения (dialogue_turns)', t['after_user_snapshot']),
                    ('Состояние, использованное AnswerService', d.get('dialogue_state')),
                    ('Intent / operation / запрос', {k: d.get(k) for k in
                        ('active_request', 'rag_query', 'confirmed_service')}),
                    ('Найденные статьи', r.get('candidates', [])),
                    ('Выбранные статьи', r.get('selected', [])),
                    ('Отклонённые статьи', r.get('rejected', [])),
                    ('Итоговый контекст LLM (точно сохранённый)', r.get('context') or '(пусто; поиска/вызова не было)'),
                    ('Исходный GPT-OSS', d.get('raw_model_text') or '(вызова не было)'),
                    ('Валидация и исправление', {k: d.get(k) for k in
                        ('validation_status', 'validation_reason', 'response_repair')}),
                    ('Конечный ответ', t['assistant']['content']),
                    ('Факт вызова / модель / токены', {k: d.get(k) for k in
                        ('llm_call_attempted', 'used_model', 'model', 'generation_status',
                         'generation_reason', 'prompt_tokens', 'completion_tokens', 'reasoning_tokens')})]
        for label, value in sections:
            body = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
            lines += [f'### {label}', '', '```text', body, '```', '']
    (OUT / 'historical.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Exported {len(turns)} turns to {OUT}')


if __name__ == '__main__':
    export()
