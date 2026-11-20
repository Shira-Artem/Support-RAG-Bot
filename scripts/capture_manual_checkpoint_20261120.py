"""Read-only, pseudonymous evidence capture; never starts Telegram or writes Qdrant."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MSK = timezone(timedelta(hours=3))


def capture(database: Path, trace: Path, output: Path) -> dict:
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        check = db.execute('PRAGMA quick_check').fetchone()[0]
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM messages WHERE created_at >= ? AND created_at < ? ORDER BY id",
            ('2026-11-18T21:00:00', '2026-11-20T21:00:00'))]
        states = {r['message_id']: json.loads(r['state_json']) for r in db.execute(
            'SELECT * FROM dialogue_turns') if any(m['id'] == r['message_id'] for m in rows)}
        # Consistent SQLite backup is private and excluded from Git.
        private = ROOT / '.local/manual-checkpoint-20261120'
        private.mkdir(parents=True, exist_ok=True)
        backup = private / 'snapshot.sqlite3'
        if not backup.exists():
            with sqlite3.connect(backup) as destination:
                db.backup(destination)
        identities = [str(r[0]) for r in db.execute('SELECT user_id FROM conversations')]
        identities += [str(r[0]) for r in db.execute('SELECT chat_id FROM conversations')]

    conversations = {v: f'dialogue-{i:02}' for i, v in enumerate(
        dict.fromkeys(r['conversation_id'] for r in rows), 1)}
    identities = sorted(set(identities), key=len, reverse=True)
    aliases = {}

    def clean(value, key=''):
        if key in {'user_id', 'chat_id', 'callback_id', 'api_call_id', 'source_first_user_ids_sha256'}:
            return '[REDACTED]'
        if key == 'task_id' and value:
            return aliases.setdefault(str(value), f'task-{len(aliases)+1:02}')
        if isinstance(value, dict):
            return {k: clean(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, str):
            for cid, alias in conversations.items():
                value = value.replace(cid, alias)
            for identity in identities:
                value = re.sub(r'(?<!\d)' + re.escape(identity) + r'(?!\d)', '[PERSON_ID]', value)
            value = re.sub(r'(?i)(?:\d{6,}:[\w-]{20,}|(?:sk-|gsk_)[\w-]{20,}|Bearer\s+[^\s,;]+)', '[SECRET]', value)
            value = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[EMAIL]', value)
            value = re.sub(r'(?<!\w)@\w{5,}', '[HANDLE]', value)
            value = re.sub(r'[A-Z]:[\\/](?:Users[\\/])[^\\/\s"<>]+', '[USER_HOME]', value, flags=re.I)
        return value

    traces, parse_errors = [], 0
    if trace.exists():
        for line in trace.read_text(encoding='utf-8').splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                parse_errors += 1
                continue
            if '2026-11-18T21:' <= r.get('timestamp_utc', '') < '2026-11-20T21:':
                traces.append(r)

    turns = []
    for row in rows:
        if row['role'] != 'user':
            continue
        following = []
        for candidate in rows:
            if candidate['id'] <= row['id'] or candidate['conversation_id'] != row['conversation_id']:
                continue
            if candidate['role'] == 'user':
                break
            following.append(candidate)
        matches = []
        for index, t in enumerate(traces):
            for message in (t.get('request_payload') or {}).get('messages', []):
                try:
                    payload = json.loads(message.get('content', ''))
                except (ValueError, TypeError):
                    continue
                # Match both exact message and temporal adjacency; never invent a trace.
                stamp = datetime.fromisoformat(t['timestamp_utc'])
                received = datetime.fromisoformat(row['created_at'])
                if payload.get('current_message') == row['content'] and abs((stamp-received).total_seconds()) < 120:
                    matches.append((abs((stamp-received).total_seconds()), index))
        matches = [min(matches)[1]] if matches else []
        turns.append(clean(dict(turn=f'M{len(turns)+1:02}', dialogue=conversations[row['conversation_id']],
            user={k: row[k] for k in ('id', 'created_at', 'content', 'status')},
            time_msk=datetime.fromisoformat(row['created_at']).astimezone(MSK).isoformat(),
            assistants=[{**{k: r[k] for k in ('id', 'created_at', 'content', 'status')},
                'diagnostics': json.loads(r['diagnostics_json'] or '{}')} for r in following],
            state_after_understanding=states.get(row['id']), understanding_trace_indices=matches,
            trace_match_basis='exact current_message + timestamp distance <120s',
            missing=[] if matches else ['linked raw Understanding trace'])) )

    result = dict(captured_at=datetime.now(timezone.utc).isoformat(),
        head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        sqlite_quick_check=check, source='private manual SQLite consistent snapshot; no personal identity fields exported',
        window='19–20.11.2026 MSK; all recorded turns included, including pre-16:02 context',
        turns=turns, understanding_traces=clean(traces), trace_parse_errors=parse_errors,
        limitations=['Message timestamps are database insertion timestamps, not Telegram receive/delivery times.',
            'Telegram update IDs and original generation/grounding call traces may be absent.',
            'Rejected model text in diagnostics is not a delivered answer.',
            'No missing intermediate trace is reconstructed.'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return dict(turns=len(turns), raw_traces=len(traces), linked_turns=sum(bool(t['understanding_trace_indices']) for t in turns),
        sqlite_quick_check=check, sha256=hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', type=Path, default=ROOT/'.local/kb-integration-20261119/manual/conversations.sqlite3')
    p.add_argument('--trace', type=Path, default=ROOT/'.local/conversational-understanding.jsonl')
    p.add_argument('--output', type=Path, default=ROOT/'reports/manual_checkpoint_20261120/manual_evidence.json')
    a = p.parse_args()
    print(json.dumps(capture(a.database, a.trace, a.output)))
