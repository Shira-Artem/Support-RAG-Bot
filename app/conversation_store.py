"""Free conversations are independent of expert sessions and never deleted on reset."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.answer_service import Answer
from app.dialogue_state import DialogueManager, DialogueState
from app.dialogue_understanding import observation_from_dict

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
                    retrieval_json TEXT, collection TEXT, callback_id TEXT UNIQUE,
                    comment TEXT, comment_created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS pending_feedback_comments (
                    user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
                    answer_message_id INTEGER NOT NULL REFERENCES messages(id),
                    PRIMARY KEY(user_id, chat_id)
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
            columns = {row['name'] for row in db.execute('PRAGMA table_info(feedback_events)')}
            for column in ('comment', 'comment_created_at'):
                if column not in columns:
                    db.execute(f'ALTER TABLE feedback_events ADD COLUMN {column} TEXT')

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
        self._ensure_v2_tables(db)
        snapshot = db.execute('SELECT * FROM dialogue_states_v2 WHERE conversation_id=?', (conversation_id,)).fetchone()
        legacy = None
        if snapshot is None:
            legacy = db.execute('SELECT * FROM dialogue_states WHERE conversation_id=?', (conversation_id,)).fetchone()
        if snapshot:
            state = DialogueState.from_dict(json.loads(snapshot['state_json']))
            cursor = snapshot['processed_message_id']
        elif legacy:
            raw = legacy['state_json']
            data = json.loads(raw)
            state = DialogueState.from_dict(data)
            cursor = legacy['processed_message_id']
            self._archive_v1(db, conversation_id, raw, data.get('schema_version'), 'migrated')
            db.execute('INSERT INTO dialogue_states_v2 VALUES(?,?,?)',
                       (conversation_id, json.dumps(state.to_dict(), ensure_ascii=False), cursor))
            snapshot = db.execute('SELECT * FROM dialogue_states_v2 WHERE conversation_id=?',
                                  (conversation_id,)).fetchone()
        else:
            state, cursor = DialogueState(), 0
        manager = self.manager
        for row in db.execute('SELECT * FROM messages WHERE conversation_id=? AND id>? ORDER BY id',
                              (conversation_id, cursor)).fetchall():
            if row['status'] != 'complete':
                break
            if row['role'] == 'user':
                diagnostic = json.loads(row['diagnostics_json'] or '{}')
                if diagnostic.get('semantic_mode'):
                    semantic = diagnostic.get('understanding')
                    if semantic:
                        try:
                            observation, summary = observation_from_dict(semantic, row['content'], row['id'])
                        except (ValueError, TypeError, KeyError) as exc:
                            # Corrupt or stale semantic evidence is a no-op,
                            # never a reason to reinterpret the text lexically.
                            diagnostic["understanding_error"] = {
                                "type": "persisted_semantic_validation",
                                "error_type": type(exc).__name__,
                                "phase": getattr(exc, "phase", "persisted_validation"),
                                "error_code": getattr(exc, "code", "persisted_semantic_validation")}
                            db.execute('UPDATE messages SET diagnostics_json=? WHERE id=?',
                                (json.dumps(diagnostic, ensure_ascii=False), row['id']))
                            state.revision += 1
                        else:
                            if summary["request_type"] in {"greeting", "escalation"}:
                                state.revision += 1
                            else:
                                state = manager.advance(state, row['content'], row['id'], observation=observation,
                                                        unknown_facts=summary['unknown_facts'])
                    else:
                        # Understanding failed. Preserve prior task state and
                        # advance the cursor exactly once; never reinterpret
                        # this Source-first turn with lexical heuristics.
                        state.revision += 1
                else:
                    # Historic turns and the legacy route retain their original reducer.
                    state = manager.advance(state, row['content'], row['id'])
                db.execute('INSERT OR IGNORE INTO dialogue_turns VALUES(?,?,?,?)',
                           (row['id'], conversation_id, state.topic_start_message_id,
                            json.dumps(state.to_dict(), ensure_ascii=False)))
            else:
                diagnostic = json.loads(row['diagnostics_json'] or '{}')
                state = manager.observe_answer(state, scenario=diagnostic.get('scenario'),
                                               reason=diagnostic.get('scenario_reason'), question=row['content'],
                                               message_id=row['id'], slot=diagnostic.get('clarification_slot'),
                                               progress_update=diagnostic.get('progress_update'))
            cursor = row['id']
        if snapshot is None or cursor != snapshot['processed_message_id']:
            db.execute('INSERT INTO dialogue_states_v2 VALUES(?,?,?) ON CONFLICT(conversation_id) '
                       'DO UPDATE SET state_json=excluded.state_json,processed_message_id=excluded.processed_message_id',
                       (conversation_id, json.dumps(state.to_dict(), ensure_ascii=False), cursor))
        return state

    @staticmethod
    def _ensure_v2_tables(db) -> None:
        db.execute('''CREATE TABLE IF NOT EXISTS dialogue_states_v2 (
            conversation_id TEXT PRIMARY KEY REFERENCES conversations(id),
            state_json TEXT NOT NULL, processed_message_id INTEGER NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS dialogue_state_migration_archive (
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            source_sha256 TEXT NOT NULL, source_version INTEGER, source_state_json TEXT NOT NULL,
            status TEXT NOT NULL, error TEXT, migrated_at TEXT NOT NULL,
            PRIMARY KEY(conversation_id, source_sha256))''')

    @staticmethod
    def _archive_v1(db, conversation_id: str, raw: str, version: int | None,
                    status: str, error: str | None = None) -> None:
        digest = sha256(raw.encode('utf-8')).hexdigest()
        db.execute('''INSERT OR IGNORE INTO dialogue_state_migration_archive
            (conversation_id,source_sha256,source_version,source_state_json,status,error,migrated_at)
            VALUES(?,?,?,?,?,?,?)''', (conversation_id, digest, version, raw, status, error,
                                        datetime.now(timezone.utc).isoformat()))

    def migrate_dialogue_states(self) -> dict[str, int]:
        """Copy known legacy snapshots to v2 storage; never modify the v1 source.

        This explicit operation is idempotent and intended for a planned,
        backed-up migration window. Unknown or invalid rows are archived and
        reported as blocked; their source snapshots remain byte-for-byte intact.
        """
        result = {"migrated": 0, "already_migrated": 0,
                  "blocked_unknown_version": 0, "blocked_invalid_payload": 0}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._ensure_v2_tables(db)
            rows = db.execute('SELECT * FROM dialogue_states ORDER BY conversation_id').fetchall()
            for row in rows:
                existing = db.execute('SELECT 1 FROM dialogue_states_v2 WHERE conversation_id=?',
                                      (row['conversation_id'],)).fetchone()
                if existing:
                    result['already_migrated'] += 1
                    continue
                raw = row['state_json']
                version = None
                try:
                    data = json.loads(raw)
                    version = data.get('schema_version')
                    if version not in {1, 2}:
                        self._archive_v1(db, row['conversation_id'], raw, version,
                                         'blocked_unknown_version', 'unsupported schema version')
                        result['blocked_unknown_version'] += 1
                        continue
                    state = DialogueState.from_dict(data)
                except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                    self._archive_v1(db, row['conversation_id'], raw, version,
                                     'blocked_invalid_payload', type(exc).__name__)
                    result['blocked_invalid_payload'] += 1
                    continue
                db.execute('INSERT INTO dialogue_states_v2 VALUES(?,?,?)',
                           (row['conversation_id'], json.dumps(state.to_dict(), ensure_ascii=False),
                            row['processed_message_id']))
                self._archive_v1(db, row['conversation_id'], raw, version, 'migrated')
                result['migrated'] += 1
            return result

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
                # A conversation containing only greetings, thanks or a vague
                # request still belongs in the durable transcript even though
                # it deliberately has no active technical task.
                rows = db.execute("""SELECT * FROM messages WHERE conversation_id=? AND status='complete'
                    ORDER BY id DESC LIMIT 12""", (conversation_id,)).fetchall()[::-1]
            else:
                rows = db.execute("""SELECT * FROM messages WHERE conversation_id=? AND status='complete'
                    AND id>=? ORDER BY id DESC LIMIT 12""", (conversation_id, root)).fetchall()[::-1]
            if root is not None and rows and rows[0]['id'] != root:
                rows.insert(0, db.execute('SELECT * FROM messages WHERE id=?', (root,)).fetchone())
            return [dict(message_id=row['id'], role=row['role'], content=row['content'],
                         clarification_reply=row['role'] == 'user' and row['id'] != root,
                         **{k: v for k, v in json.loads(row['diagnostics_json'] or '{}').items()
                            if k in {'scenario', 'scenario_reason', 'clarification_slot', 'understanding',
                                     'understanding_error', 'semantic_mode'}}) for row in rows]

    def begin(self, conversation_id: str, text: str, continuing: bool | None = None, *,
              understanding: dict | None = None, understanding_error: str | None = None,
              semantic_mode: bool = False) -> int:
        # continuing is retained for old callers, but no longer controls state.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._sync_state(db, conversation_id)
            if db.execute("SELECT 1 FROM messages WHERE conversation_id=? AND status='pending'", (conversation_id,)).fetchone():
                raise RuntimeError('Complete or recover the pending turn before starting another')
            created = datetime.now(timezone.utc).isoformat()
            user_diagnostics = ({"semantic_mode": True, "understanding": understanding,
                                 "understanding_error": understanding_error}
                                if semantic_mode else {})
            db.execute("""INSERT INTO messages(conversation_id,role,content,created_at,continuation,diagnostics_json)
                VALUES(?,'user',?,?,?,?)""", (conversation_id, text, created, 0,
                    json.dumps(user_diagnostics, ensure_ascii=False)))
            user_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            if user_diagnostics.get("understanding"):
                def bind_source_id(value):
                    if isinstance(value, dict):
                        return {key: (user_id if key == "message_id"
                                      else bind_source_id(child)) for key, child in value.items()}
                    if isinstance(value, list):
                        return [bind_source_id(child) for child in value]
                    return value
                user_diagnostics["understanding"] = bind_source_id(user_diagnostics["understanding"])
                db.execute('UPDATE messages SET diagnostics_json=? WHERE id=?',
                           (json.dumps(user_diagnostics, ensure_ascii=False), user_id))
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
            latest = db.execute('SELECT rating FROM feedback_events WHERE answer_message_id=? '
                                'ORDER BY id DESC LIMIT 1', (answer_id,)).fetchone()
            if latest and latest['rating'] == rating:
                return False
            db.execute('DELETE FROM pending_feedback_comments WHERE user_id=? AND chat_id=?',
                       (user_id, chat_id))
            result = db.execute('''INSERT OR IGNORE INTO feedback_events
                (conversation_id,answer_message_id,rating,created_at,scenario,generation_status,
                 generation_reason,retrieval_json,collection,callback_id) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (cid, answer_id, rating, datetime.now(timezone.utc).isoformat(), d.get('scenario'),
                 d.get('generation_status'), d.get('generation_reason'), retrieval,
                 d.get('retrieval_collection'), callback_id))
            return result.rowcount > 0

    def request_feedback_comment(self, answer_id: int, user_id: int, chat_id: int) -> bool:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._event_context(db, answer_id, user_id, chat_id)
            latest = db.execute('SELECT rating FROM feedback_events WHERE answer_message_id=? '
                                'ORDER BY id DESC LIMIT 1', (answer_id,)).fetchone()
            if not latest or latest['rating'] != 'unhelpful':
                return False
            db.execute('''INSERT INTO pending_feedback_comments(user_id,chat_id,answer_message_id)
                VALUES(?,?,?) ON CONFLICT(user_id,chat_id) DO UPDATE SET
                answer_message_id=excluded.answer_message_id''', (user_id, chat_id, answer_id))
            return True

    def save_feedback_comment(self, user_id: int, chat_id: int, comment: str) -> bool:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            target = db.execute('SELECT answer_message_id FROM pending_feedback_comments '
                                'WHERE user_id=? AND chat_id=?', (user_id, chat_id)).fetchone()
            if not target:
                return False
            answer_id = target['answer_message_id']
            self._event_context(db, answer_id, user_id, chat_id)
            latest = db.execute('SELECT id,rating FROM feedback_events WHERE answer_message_id=? '
                                'ORDER BY id DESC LIMIT 1', (answer_id,)).fetchone()
            if not latest or latest['rating'] != 'unhelpful':
                db.execute('DELETE FROM pending_feedback_comments WHERE user_id=? AND chat_id=?',
                           (user_id, chat_id))
                return False
            db.execute('UPDATE feedback_events SET comment=?,comment_created_at=? WHERE id=?',
                       (comment.strip()[:2000], datetime.now(timezone.utc).isoformat(), latest['id']))
            db.execute('DELETE FROM pending_feedback_comments WHERE user_id=? AND chat_id=?',
                       (user_id, chat_id))
            return True

    def clear_pending_feedback_comment(self, user_id: int, chat_id: int) -> None:
        with self.connect() as db:
            db.execute('DELETE FROM pending_feedback_comments WHERE user_id=? AND chat_id=?',
                       (user_id, chat_id))

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
