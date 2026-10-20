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
            """)

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
