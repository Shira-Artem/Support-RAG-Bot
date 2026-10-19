"""Free conversations are independent of expert sessions and never deleted on reset."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.answer_service import Answer, _active_request, _confirmed_service

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data/conversations.sqlite3"


class ConversationStore:
    def __init__(self, path: Path = DEFAULT_DB):
        self.path = Path(path)
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

    def history(self, conversation_id: str) -> list[dict]:
        # Re-evaluate topic boundaries from the immutable transcript. Old
        # continuation flags may have been written by a faulty classifier; do
        # not let such a flag permanently hide the client's confirmed service.
        active = []
        with self.connect() as db:
            for row in db.execute("""SELECT * FROM messages WHERE conversation_id=?
                AND status='complete' ORDER BY id""", (conversation_id,)):
                diagnostics = json.loads(row['diagnostics_json'] or '{}')
                continuing = False
                if row['role'] == 'user':
                    continuing = _active_request(row['content'], active)[2]
                    if not continuing:
                        active = []
                active.append({'role': row['role'], 'content': row['content'],
                               'clarification_reply': continuing,
                               'scenario': diagnostics.get('scenario'),
                               'scenario_reason': diagnostics.get('scenario_reason')})
        if not active:
            return []
        selected = {0, *range(max(0, len(active) - 12), len(active))}
        for i in range(len(active) - 1, -1, -1):
            if active[i]['role'] == 'user' and _confirmed_service(active[i]['content']):
                selected.add(i)
                break
        return [active[i] for i in sorted(selected)]

    def begin(self, conversation_id: str, text: str, continuing: bool) -> int:
        with self.connect() as db:
            created = datetime.now(timezone.utc).isoformat()
            db.execute("""INSERT INTO messages(conversation_id,role,content,created_at,continuation)
                VALUES(?,'user',?,?,?)""", (conversation_id, text, created, int(continuing)))
            return db.execute("""INSERT INTO messages(conversation_id,role,content,created_at,status)
                VALUES(?,'assistant','',?,'pending')""", (conversation_id, created)).lastrowid

    def complete(self, message_id: int, answer: Answer) -> None:
        with self.connect() as db:
            db.execute("""UPDATE messages SET content=?, status='complete', diagnostics_json=?
                WHERE id=? AND status='pending'""",
                       (answer.text, json.dumps(asdict(answer), ensure_ascii=False), message_id))

    def recover_pending(self) -> None:
        with self.connect() as db:
            ids = [row['id'] for row in db.execute("SELECT id FROM messages WHERE status='pending'")]
        for message_id in ids:
            self.complete(message_id, Answer("Обработка была прервана перезапуском. Повторите последнее сообщение.",
                          generation_status="error", generation_reason="process_interrupted",
                          scenario="escalate", scenario_reason="process_interrupted"))
