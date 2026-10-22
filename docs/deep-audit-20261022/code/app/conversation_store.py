"""Free conversations are independent of expert sessions and never deleted on reset."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.answer_service import Answer
from app.dialogue_state import DialogueManager, DialogueState

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data/conversations.sqlite3"


class ConversationStore:
    def __init__(self, path: Path = DEFAULT_DB, *, manager: DialogueManager | None = None):
        self.path = Path(path)
        self.manager = manager or DialogueManager()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_state (
                    user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'menu' CHECK(mode IN ('menu','free','expert')),
                    conversation_id TEXT REFERENCES conversations(id),
                    PRIMARY KEY(user_id, chat_id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
                    created_at TEXT NOT NULL, continuation INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'complete', diagnostics_json TEXT
                );
                CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id, id);
                CREATE TABLE IF NOT EXISTS dialogue_states (
                    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id),
                    state_json TEXT NOT NULL, processed_message_id INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dialogue_turns (
                    message_id INTEGER PRIMARY KEY REFERENCES messages(id),
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    topic_start_message_id INTEGER NOT NULL, state_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    answer_message_id INTEGER NOT NULL REFERENCES messages(id),
                    rating TEXT NOT NULL CHECK(rating IN ('helpful','unhelpful')),
                    created_at TEXT NOT NULL,
                    scenario TEXT, generation_status TEXT, generation_reason TEXT,
                    retrieval_json TEXT, collection TEXT, callback_id TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS support_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    answer_message_id INTEGER NOT NULL UNIQUE REFERENCES messages(id),
                    question_message_id INTEGER NOT NULL REFERENCES messages(id),
                    status TEXT NOT NULL CHECK(status IN ('pending_confirmation','cancelled','saved','delivered')),
                    basis TEXT NOT NULL, created_at TEXT NOT NULL, confirmed_at TEXT,
                    delivered_at TEXT
                );
                CREATE TABLE IF NOT EXISTS escalation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    answer_message_id INTEGER NOT NULL REFERENCES messages(id),
                    event_type TEXT NOT NULL CHECK(event_type IN ('requested','confirmed','cancelled','delivered')),
                    created_at TEXT NOT NULL, scenario TEXT, generation_status TEXT,
                    generation_reason TEXT, retrieval_json TEXT, collection TEXT,
                    request_status TEXT NOT NULL, basis TEXT NOT NULL,
                    UNIQUE(answer_message_id, event_type)
                );
                CREATE INDEX IF NOT EXISTS feedback_answer ON feedback_events(answer_message_id);
                CREATE INDEX IF NOT EXISTS escalation_conversation ON escalation_events(conversation_id);
            """)
            # The first local revision keyed ratings by (answer, rating).
            # Preserve any events while allowing a user to revise a rating.
            columns = {row['name'] for row in db.execute('PRAGMA table_info(feedback_events)')}
            if 'callback_id' not in columns:
                db.executescript('''
                    ALTER TABLE feedback_events RENAME TO feedback_events_old;
                    CREATE TABLE feedback_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id TEXT NOT NULL REFERENCES conversations(id),
                        answer_message_id INTEGER NOT NULL REFERENCES messages(id),
                        rating TEXT NOT NULL CHECK(rating IN ('helpful','unhelpful')),
                        created_at TEXT NOT NULL,
                        scenario TEXT, generation_status TEXT, generation_reason TEXT,
                        retrieval_json TEXT, collection TEXT, callback_id TEXT UNIQUE
                    );
                    INSERT INTO feedback_events
                        (id,conversation_id,answer_message_id,rating,created_at,scenario,
                         generation_status,generation_reason,retrieval_json,collection)
                    SELECT id,conversation_id,answer_message_id,rating,created_at,scenario,
                           generation_status,generation_reason,retrieval_json,collection
                    FROM feedback_events_old;
                    DROP TABLE feedback_events_old;
                    CREATE INDEX IF NOT EXISTS feedback_answer ON feedback_events(answer_message_id);
                ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def state(self, user_id: int, chat_id: int) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM chat_state WHERE user_id=? AND chat_id=?", (user_id, chat_id)).fetchone()
        return dict(row) if row else {"mode": "menu", "conversation_id": None}

    def set_mode(self, user_id: int, chat_id: int, mode: str) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO chat_state(user_id,chat_id,mode) VALUES(?,?,?)
                ON CONFLICT(user_id,chat_id) DO UPDATE SET mode=excluded.mode""", (user_id, chat_id, mode))

    def new(self, user_id: int, chat_id: int) -> str:
        conversation_id = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO conversations VALUES(?,?,?,?)",
                       (conversation_id, user_id, chat_id, datetime.now(timezone.utc).isoformat()))
            db.execute("""INSERT INTO chat_state VALUES(?,?,'free',?)
                ON CONFLICT(user_id,chat_id) DO UPDATE SET mode='free', conversation_id=excluded.conversation_id""",
                       (user_id, chat_id, conversation_id))
        return conversation_id

    def _sync_state(self, db, conversation_id: str) -> DialogueState:
        """Replay legacy messages ONCE, then apply only unseen events.

        Old continuation flags and assistant claims are never client evidence.
        The additive tables leave all old rows and diagnostic JSON untouched.
        A pending assistant stops the cursor so its later completion isn't lost.
        Callers hold the same write transaction as the message/snapshot update.
        """
        snapshot = db.execute('SELECT * FROM dialogue_states WHERE conversation_id=?', (conversation_id,)).fetchone()
        state = DialogueState.from_dict(json.loads(snapshot['state_json'])) if snapshot else DialogueState()
        cursor = snapshot['processed_message_id'] if snapshot else 0
        manager = self.manager
        for row in db.execute('SELECT * FROM messages WHERE conversation_id=? AND id>? ORDER BY id',
                              (conversation_id, cursor)).fetchall():
            if row['status'] != 'complete':
                break
            if row['role'] == 'user':
                state = manager.advance(state, row['content'], row['id'])
                db.execute('INSERT OR IGNORE INTO dialogue_turns VALUES(?,?,?,?)',
                           (row['id'], conversation_id, state.topic_start_message_id,
                            json.dumps(state.to_dict(), ensure_ascii=False)))
            else:
                diagnostic = json.loads(row['diagnostics_json'] or '{}')
                state = manager.observe_answer(state, scenario=diagnostic.get('scenario'),
                                               reason=diagnostic.get('scenario_reason'), question=row['content'],
                                               message_id=row['id'], slot=diagnostic.get('clarification_slot'))
            cursor = row['id']
        if snapshot is None or cursor != snapshot['processed_message_id']:
            db.execute('INSERT INTO dialogue_states VALUES(?,?,?) ON CONFLICT(conversation_id) '
                       'DO UPDATE SET state_json=excluded.state_json,processed_message_id=excluded.processed_message_id',
                       (conversation_id, json.dumps(state.to_dict(), ensure_ascii=False), cursor))
        return state

    def dialogue_state(self, conversation_id: str) -> DialogueState:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._sync_state(db, conversation_id)

    def history(self, conversation_id: str) -> list[dict]:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self._sync_state(db, conversation_id)
            root = state.topic_start_message_id
            if root is None:
                return []
            rows = db.execute("""SELECT * FROM messages WHERE conversation_id=? AND status='complete'
                AND id>=? ORDER BY id DESC LIMIT 12""", (conversation_id, root)).fetchall()[::-1]
            if rows and rows[0]['id'] != root:
                rows.insert(0, db.execute('SELECT * FROM messages WHERE id=?', (root,)).fetchone())
            return [dict(message_id=row['id'], role=row['role'], content=row['content'],
                         clarification_reply=row['role'] == 'user' and row['id'] != root,
                         **{k: v for k, v in json.loads(row['diagnostics_json'] or '{}').items()
                            if k in {'scenario', 'scenario_reason', 'clarification_slot'}}) for row in rows]

    def begin(self, conversation_id: str, text: str, continuing: bool | None = None) -> int:
        # continuing is retained for old callers, but no longer controls state.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._sync_state(db, conversation_id)
            if db.execute("SELECT 1 FROM messages WHERE conversation_id=? AND status='pending'", (conversation_id,)).fetchone():
                raise RuntimeError('Complete or recover the pending turn before starting another')
            created = datetime.now(timezone.utc).isoformat()
            db.execute("""INSERT INTO messages(conversation_id,role,content,created_at,continuation)
                VALUES(?,'user',?,?,?)""", (conversation_id, text, created, 0))
            user_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            state = self._sync_state(db, conversation_id)
            db.execute('UPDATE messages SET continuation=? WHERE id=?', (int(state.transition != 'new_task'), user_id))
            return db.execute("""INSERT INTO messages(conversation_id,role,content,created_at,status)
                VALUES(?,'assistant','',?,'pending')""", (conversation_id, created)).lastrowid

    def complete(self, message_id: int, answer: Answer) -> None:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM messages WHERE id=? AND status='pending'", (message_id,)).fetchone()
            if row is None:
                return
            db.execute("""UPDATE messages SET content=?, status='complete', diagnostics_json=?
                WHERE id=? AND status='pending'""",
                       (answer.text, json.dumps(asdict(answer), ensure_ascii=False), message_id))
            self._sync_state(db, row['conversation_id'])

    def recover_pending(self) -> None:
        with self.connect() as db:
            ids = [row['id'] for row in db.execute("SELECT id FROM messages WHERE status='pending'")]
        for message_id in ids:
            self.complete(message_id, Answer("Обработка была прервана перезапуском. Повторите последнее сообщение.",
                          generation_status="error", generation_reason="process_interrupted",
                          scenario="escalate", scenario_reason="process_interrupted"))

    @staticmethod
    def _event_context(db, answer_id: int, user_id: int, chat_id: int):
        row = db.execute('''SELECT m.*, c.user_id, c.chat_id FROM messages m
            JOIN conversations c ON c.id=m.conversation_id
            WHERE m.id=? AND m.role='assistant' AND m.status='complete' ''', (answer_id,)).fetchone()
        if row is None or row['user_id'] != user_id or row['chat_id'] != chat_id:
            raise ValueError('Answer does not belong to this user and chat')
        diagnostic = json.loads(row['diagnostics_json'] or '{}')
        retrieval = diagnostic.get('retrieval_diagnostics') or {}
        compact = {key: retrieval.get(key) for key in ('sufficient','evidence_status','missing_evidence',
                   'insufficiency_reason') if key in retrieval}
        compact['selected_document_ids'] = [item.get('document_id') for item in retrieval.get('selected', [])]
        question = db.execute('''SELECT id FROM messages WHERE conversation_id=? AND role='user'
            AND id<? ORDER BY id DESC LIMIT 1''', (row['conversation_id'], answer_id)).fetchone()
        if question is None:
            raise ValueError('Answer has no client question')
        return row['conversation_id'], question['id'], diagnostic, json.dumps(compact, ensure_ascii=False)

    def record_feedback(self, answer_id: int, user_id: int, chat_id: int, rating: str,
                        callback_id: str | None = None) -> bool:
        if rating not in {'helpful', 'unhelpful'}:
            raise ValueError('Unsupported rating')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cid, _, d, retrieval = self._event_context(db, answer_id, user_id, chat_id)
            if callback_id is None:
                latest = db.execute('SELECT rating FROM feedback_events WHERE answer_message_id=? '
                                    'ORDER BY id DESC LIMIT 1', (answer_id,)).fetchone()
                if latest and latest['rating'] == rating:
                    return False
            result = db.execute('''INSERT OR IGNORE INTO feedback_events
                (conversation_id,answer_message_id,rating,created_at,scenario,generation_status,
                 generation_reason,retrieval_json,collection,callback_id) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (cid, answer_id, rating, datetime.now(timezone.utc).isoformat(), d.get('scenario'),
                 d.get('generation_status'), d.get('generation_reason'), retrieval,
                 d.get('retrieval_collection'), callback_id))
            return result.rowcount > 0

    def support_request(self, answer_id: int, user_id: int, chat_id: int, action: str) -> str:
        if action not in {'ask', 'confirm', 'cancel'}:
            raise ValueError('Unsupported action')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cid, question_id, d, retrieval = self._event_context(db, answer_id, user_id, chat_id)
            request = db.execute('SELECT * FROM support_requests WHERE answer_message_id=?', (answer_id,)).fetchone()
            now = datetime.now(timezone.utc).isoformat()
            basis = ('insufficient_knowledge' if d.get('generation_status') == 'no_context' else
                     'system_error' if d.get('generation_status') in {'error','unavailable','truncated'} else
                     'risky_operation' if str(d.get('scenario_reason') or '').startswith(
                         ('unsupported_dangerous_operation','unsafe_operation','risk_operation')) else
                     'user_requested')
            if action == 'ask':
                if request is None:
                    db.execute('''INSERT INTO support_requests
                        (conversation_id,answer_message_id,question_message_id,status,basis,created_at)
                        VALUES(?,?,?,'pending_confirmation',?,?)''', (cid,answer_id,question_id,basis,now))
                elif request['status'] == 'cancelled':
                    db.execute("UPDATE support_requests SET status='pending_confirmation' WHERE id=?", (request['id'],))
            elif action == 'confirm':
                if request is None:
                    raise ValueError('Confirmation was not requested')
                if request['status'] == 'cancelled':
                    raise ValueError('Confirmation was cancelled')
                if request['status'] == 'pending_confirmation':
                    db.execute("UPDATE support_requests SET status='saved',confirmed_at=? WHERE id=?", (now,request['id']))
            elif action == 'cancel':
                if request is None:
                    raise ValueError('Confirmation was not requested')
                if request['status'] == 'pending_confirmation':
                    db.execute("UPDATE support_requests SET status='cancelled' WHERE id=?", (request['id'],))
            request = db.execute('SELECT * FROM support_requests WHERE answer_message_id=?', (answer_id,)).fetchone()
            status = request['status']
            event_type = {'ask':'requested','confirm':'confirmed','cancel':'cancelled'}[action]
            if (action == 'ask' or action == 'cancel' and status == 'cancelled'
                    or action == 'confirm' and status in {'saved','delivered'}):
                db.execute('''INSERT OR IGNORE INTO escalation_events
                    (conversation_id,answer_message_id,event_type,created_at,scenario,
                     generation_status,generation_reason,retrieval_json,collection,request_status,basis)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                    (cid,answer_id,event_type,now,d.get('scenario'),d.get('generation_status'),
                     d.get('generation_reason'),retrieval,d.get('retrieval_collection'),status,basis))
            return status

    def previous_unresolved(self, conversation_id: str, answer_id: int, state: DialogueState) -> bool:
        if state.transition == 'new_task':
            return False
        with self.connect() as db:
            row = db.execute('''SELECT diagnostics_json FROM messages WHERE conversation_id=?
                AND role='assistant' AND status='complete' AND id<? ORDER BY id DESC LIMIT 1''',
                (conversation_id, answer_id)).fetchone()
        if not row:
            return False
        previous = json.loads(row['diagnostics_json'] or '{}')
        old_state = previous.get('dialogue_state') or {}
        current = state.to_dict()
        def values(facts):
            return [item.get('value') for item in facts or []]
        def entities(snapshot):
            return {slot: values(facts) for slot, facts in (snapshot.get('entities') or {}).items()}
        return (previous.get('generation_status') == 'no_context'
                and old_state.get('task_id') == state.task_id
                and old_state.get('intent') == state.intent
                and old_state.get('operation') == state.operation
                and entities(old_state) == entities(current)
                and all(values(old_state.get(key)) == values(current.get(key))
                        for key in ('parameters','goals','constraints','details'))
                and (old_state.get('error') or {}).get('value') ==
                    (current.get('error') or {}).get('value'))
