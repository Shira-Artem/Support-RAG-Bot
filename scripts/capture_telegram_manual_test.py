"""Read-only capture of five manual Telegram dialogs (20 client turns).

Private exports default to .local; no provider, Telegram or app-store imports.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = 'knowledge_sprint_v1_20261022_quality_gate'


def read_db(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def mark(db_path, receipt, cases):
    if receipt.get('collection') != COLLECTION:
        raise ValueError('Start marker requires a receipt from the approved STAGING worker')
    with read_db(db_path) as db:
        last = db.execute('SELECT COALESCE(MAX(id),0) FROM messages').fetchone()[0]
    return dict(created_at=datetime.now(timezone.utc).isoformat(), after_message_id=last,
                collection=COLLECTION, runtime=receipt, planned_turns=cases)


def capture(db_path, marker):
    with read_db(db_path) as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM messages WHERE id>? ORDER BY id',
                                         (marker['after_message_id'],))]
    dialogs={}
    for row in rows:
        dialogs.setdefault(row['conversation_id'],[]).append(row)
    turns=[]
    groups=list(dict.fromkeys(case['conversation'] for case in marker['planned_turns']))
    counts={}
    for index,(cid,messages) in enumerate(dialogs.items()):
        group=groups[index] if index<len(groups) else f'extra-{index+1}'
        users=[r for r in messages if r['role']=='user']
        counts[cid]=len(users)
        planned=[case for case in marker['planned_turns'] if case['conversation']==group]
        for i,user in enumerate(users):
            end=users[i+1]['id'] if i+1<len(users) else float('inf')
            answer=next((r for r in messages if r['role']=='assistant' and user['id']<r['id']<end),None)
            diagnostics=json.loads(answer.get('diagnostics_json') or '{}') if answer else {}
            expected=planned[i] if i<len(planned) else None
            turns.append(dict(dialog=group,conversation_id=cid,user=user,assistant=answer,
                              diagnostics=diagnostics,planned=expected,
                              planned_text_matches=bool(expected and expected['message']==user['content'])))
    collection_matches=sum(t['diagnostics'].get('retrieval_collection')==marker['collection'] for t in turns)
    configuration_matches=sum(t['diagnostics'].get('provider')=='groq'
        and t['diagnostics'].get('model')=='openai/gpt-oss-20b'
        and t['diagnostics'].get('reasoning_effort')=='medium' for t in turns)
    completed=sum(bool(t['assistant'] and t['assistant']['status']=='complete') for t in turns)
    return dict(marker=marker, captured_at=datetime.now(timezone.utc).isoformat(),
                dialog_counts=counts,client_turns=len(turns),completed_answers=completed,
                verified_collection_answers=collection_matches,
                verified_model_answers=configuration_matches,
                complete=(len(counts)==5 and list(counts.values())==[4]*5
                          and len(turns)==completed==collection_matches==configuration_matches==20),turns=turns)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['mark','capture'])
    parser.add_argument('--db',type=Path,default=ROOT/'data/conversations.sqlite3')
    parser.add_argument('--marker',type=Path,default=ROOT/'.local/telegram-live-test/marker.json')
    parser.add_argument('--output',type=Path,default=ROOT/'.local/telegram-live-test/diagnostics-20.json')
    args=parser.parse_args()
    if args.action=='mark':
        if args.marker.exists():
            parser.error('Marker already exists; preserve the earlier session and choose another path')
        receipt=json.loads((ROOT/'.local/bot-runtime.json').read_text(encoding='utf-8'))
        cases=json.loads((ROOT/'docs/telegram-live-test/dialogs.json').read_text(encoding='utf-8'))
        data=mark(args.db,receipt,cases);target=args.marker
    else:
        data=capture(args.db,json.loads(args.marker.read_text(encoding='utf-8')));target=args.output
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(path=str(target),complete=data.get('complete'),client_turns=data.get('client_turns'),
                          completed_answers=data.get('completed_answers'),verified_collection_answers=data.get('verified_collection_answers'))))


if __name__=='__main__':
    main()
