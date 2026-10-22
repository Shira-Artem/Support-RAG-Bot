import hashlib
import json
import sqlite3

import pytest

from scripts.capture_telegram_manual_test import COLLECTION, mark, capture


def test_capture_twenty_turns_is_read_only_and_preserves_diagnostics(tmp_path):
    path=tmp_path/'messages.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, status TEXT, diagnostics_json TEXT)')
    cases=[dict(conversation=str(i),message=f'question {i}-{j}') for i in range(5) for j in range(4)]
    marker=mark(path,dict(collection=COLLECTION,pid=123),cases)
    with sqlite3.connect(path) as db:
        for i,case in enumerate(cases):
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)',(2*i+1,case['conversation'],'user',case['message'],'complete',None))
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)',(2*i+2,case['conversation'],'assistant','answer','complete',json.dumps(dict(retrieval_collection=COLLECTION,provider='groq',model='openai/gpt-oss-20b',reasoning_effort='medium',raw_model_text='raw',dialogue_state={'operation':'create_role'}))))
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    result=capture(path,marker)
    assert result['complete'] and result['client_turns']==20 and result['completed_answers']==20
    assert result['turns'][0]['diagnostics']['raw_model_text']=='raw'
    assert all(t['planned_text_matches'] for t in result['turns'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM messages WHERE id=40')
    assert not capture(path,marker)['complete']


def test_marker_refuses_old_collection(tmp_path):
    with pytest.raises(ValueError,match='STAGING'):
        mark(tmp_path/'unused.sqlite3',dict(collection='knowledge_demo'),[])
