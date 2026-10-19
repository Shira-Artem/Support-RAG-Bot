"""Durable expert sessions, immutable generated answers and editable reviews."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.answer_service import Answer


DEFAULT_DB = Path(__file__).resolve().parents[1] / "data/evaluations/expert_reviews.sqlite3"
DEFAULT_QUESTIONS = Path(__file__).resolve().parents[1] / "data/evaluation_questions.jsonl"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_questions(path: Path = DEFAULT_QUESTIONS) -> list[dict]:
    questions = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    required = {"id", "category", "query", "expected_topic", "expected_behavior", "notes"}
    if not questions or any(not required <= q.keys() for q in questions):
        raise ValueError("Invalid evaluation question set")
    if len({q["id"] for q in questions}) != len(questions):
        raise ValueError("Duplicate evaluation question ID")
    return questions


class ExpertStore:
    def __init__(self, path: Path = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS experts (
                    id TEXT PRIMARY KEY, telegram_id INTEGER NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, expert_id INTEGER NOT NULL, specialist_id TEXT REFERENCES experts(id),
                    started_at TEXT NOT NULL,
                    finished_at TEXT, position INTEGER NOT NULL DEFAULT 0, comment_target INTEGER
                );
                CREATE TABLE IF NOT EXISTS items (
                    session_id TEXT NOT NULL REFERENCES sessions(id), ordinal INTEGER NOT NULL,
                    question_id TEXT NOT NULL, category TEXT NOT NULL, query TEXT NOT NULL,
                    expected_topic TEXT, expected_behavior TEXT NOT NULL, notes TEXT NOT NULL,
                    question_type TEXT, expected_document TEXT,
                    skipped_at TEXT, PRIMARY KEY(session_id, question_id), UNIQUE(session_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                    question_id TEXT NOT NULL, attempt_no INTEGER NOT NULL,
                    created_at TEXT NOT NULL, completed_at TEXT, generation_status TEXT NOT NULL,
                    answer_text TEXT, results_json TEXT NOT NULL DEFAULT '[]', model TEXT,
                    provider TEXT, api_call_id TEXT,
                    duration_ms INTEGER, rag_chunks INTEGER, context_chars INTEGER,
                    prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER,
                    reasoning_tokens INTEGER, cached_tokens INTEGER,
                    raw_model_text TEXT, validation_status TEXT, validation_reason TEXT,
                    generation_reason TEXT, scenario TEXT, scenario_reason TEXT,
                    UNIQUE(session_id, question_id, attempt_no),
                    FOREIGN KEY(session_id, question_id) REFERENCES items(session_id, question_id)
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    attempt_id INTEGER PRIMARY KEY REFERENCES attempts(id), score INTEGER NOT NULL
                        CHECK(score BETWEEN 1 AND 10), reason TEXT, comment TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_expert ON sessions(expert_id, started_at);
            """)
            # Additive migrations preserve existing session, answer, and review rows.
            migrations = {
                "sessions": {"specialist_id": "TEXT", "comment_target": "INTEGER"},
                "items": {"skipped_at": "TEXT", "question_type": "TEXT", "expected_document": "TEXT"},
                "attempts": {
                    "provider": "TEXT", "api_call_id": "TEXT", "duration_ms": "INTEGER",
                    "rag_chunks": "INTEGER", "context_chars": "INTEGER", "prompt_tokens": "INTEGER",
                    "completion_tokens": "INTEGER", "total_tokens": "INTEGER",
                    "reasoning_tokens": "INTEGER", "cached_tokens": "INTEGER",
                    "raw_model_text": "TEXT", "validation_status": "TEXT",
                    "validation_reason": "TEXT", "generation_reason": "TEXT",
                    "scenario": "TEXT", "scenario_reason": "TEXT",
                },
            }
            for table, columns in migrations.items():
                existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                for column, sql_type in columns.items():
                    if column not in existing:
                        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
            for row in db.execute("SELECT DISTINCT expert_id FROM sessions").fetchall():
                db.execute("INSERT OR IGNORE INTO experts(id, telegram_id) VALUES(?,?)",
                           (uuid4().hex, row["expert_id"]))
            db.execute("""UPDATE sessions SET specialist_id=(SELECT id FROM experts
                WHERE experts.telegram_id=sessions.expert_id) WHERE specialist_id IS NULL""")

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

    def start(self, expert_id: int, questions: list[dict]) -> str:
        session_id = uuid4().hex
        with self.connect() as db:
            # Keep one resumable session per tester. Starting a new run closes the
            # previous run without removing any of its answers or reviews.
            db.execute("UPDATE sessions SET finished_at=COALESCE(finished_at,?) WHERE expert_id=?",
                       (now(), expert_id))
            db.execute("INSERT OR IGNORE INTO experts(id, telegram_id) VALUES(?,?)", (uuid4().hex, expert_id))
            specialist_id = db.execute("SELECT id FROM experts WHERE telegram_id=?", (expert_id,)).fetchone()["id"]
            db.execute("INSERT INTO sessions(id, expert_id, specialist_id, started_at) VALUES(?,?,?,?)",
                       (session_id, expert_id, specialist_id, now()))
            db.executemany("""INSERT INTO items(session_id, ordinal, question_id, category, query,
                expected_topic, expected_behavior, notes, question_type, expected_document)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                [(session_id, i, q["id"], q["category"], q["query"], q.get("expected_topic"),
                  q["expected_behavior"], q.get("notes", ""), q.get("question_type"),
                  q.get("expected_document")) for i, q in enumerate(questions)])
        return session_id

    def active(self, expert_id: int):
        with self.connect() as db:
            return db.execute("""SELECT * FROM sessions WHERE expert_id=? AND finished_at IS NULL
                ORDER BY started_at DESC LIMIT 1""", (expert_id,)).fetchone()

    def active_sessions(self, expert_id: int):
        with self.connect() as db:
            return db.execute("""SELECT * FROM sessions WHERE expert_id=? AND finished_at IS NULL
                ORDER BY started_at DESC""", (expert_id,)).fetchall()

    def session(self, session_id: str, expert_id: int):
        with self.connect() as db:
            return db.execute("SELECT * FROM sessions WHERE id=? AND expert_id=?", (session_id, expert_id)).fetchone()

    def current(self, session_id: str, expert_id: int):
        with self.connect() as db:
            return db.execute("""SELECT i.*, s.position, s.finished_at,
                (SELECT COUNT(*) FROM items WHERE session_id=s.id) AS total
                FROM sessions s JOIN items i ON i.session_id=s.id AND i.ordinal=s.position
                WHERE s.id=? AND s.expert_id=?""", (session_id, expert_id)).fetchone()

    def move(self, session_id: str, expert_id: int, delta: int, *, skip: bool = False) -> bool:
        with self.connect() as db:
            row = db.execute("""SELECT s.position, COUNT(i.question_id) AS total FROM sessions s
                JOIN items i ON i.session_id=s.id WHERE s.id=? AND s.expert_id=?
                AND s.finished_at IS NULL GROUP BY s.id""", (session_id, expert_id)).fetchone()
            if not row:
                return False
            if skip:
                db.execute("""UPDATE items SET skipped_at=COALESCE(skipped_at,?)
                    WHERE session_id=? AND ordinal=?""", (now(), session_id, row["position"]))
            position = max(0, min(row["total"] - 1, row["position"] + delta))
            db.execute("UPDATE sessions SET position=?, comment_target=NULL WHERE id=?", (position, session_id))
            return True

    def finish(self, session_id: str, expert_id: int) -> None:
        with self.connect() as db:
            db.execute("UPDATE sessions SET finished_at=COALESCE(finished_at,?), comment_target=NULL WHERE id=? AND expert_id=?",
                       (now(), session_id, expert_id))

    def latest(self, session_id: str, question_id: str):
        with self.connect() as db:
            return db.execute("""SELECT a.*, r.score, r.reason, r.comment FROM attempts a
                LEFT JOIN reviews r ON r.attempt_id=a.id WHERE a.session_id=? AND a.question_id=?
                ORDER BY a.attempt_no DESC LIMIT 1""", (session_id, question_id)).fetchone()

    def claim(self, session_id: str, expert_id: int, question_id: str,
              *, provider: str | None = None, model: str | None = None,
              force: bool = False) -> int | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("""SELECT i.question_id FROM sessions s JOIN items i
                ON i.session_id=s.id AND i.ordinal=s.position WHERE s.id=? AND s.expert_id=?
                AND s.finished_at IS NULL""", (session_id, expert_id)).fetchone()
            if not current or current["question_id"] != question_id:
                return None
            latest = db.execute("""SELECT attempt_no, generation_status FROM attempts
                WHERE session_id=? AND question_id=? ORDER BY attempt_no DESC LIMIT 1""",
                (session_id, question_id)).fetchone()
            if latest and (latest["generation_status"] == "pending" or
                           (latest["generation_status"] == "generated" and not force)):
                return None
            attempt_no = latest["attempt_no"] + 1 if latest else 1
            cursor = db.execute("""INSERT INTO attempts(session_id, question_id, attempt_no,
                created_at, generation_status, provider, model) VALUES(?,?,?,?, 'pending', ?, ?)""",
                (session_id, question_id, attempt_no, now(), provider, model))
            return cursor.lastrowid

    def save_answer(self, attempt_id: int, answer: Answer) -> None:
        # Only this pending attempt can be completed. Generated text is never updated thereafter.
        with self.connect() as db:
            db.execute("""UPDATE attempts SET completed_at=?, generation_status=?, answer_text=?,
                results_json=?, model=?, provider=?, api_call_id=?, duration_ms=?, rag_chunks=?, context_chars=?,
                prompt_tokens=?, completion_tokens=?, total_tokens=?, reasoning_tokens=?, cached_tokens=?,
                raw_model_text=?, validation_status=?, validation_reason=?, generation_reason=?,
                scenario=?, scenario_reason=?
                WHERE id=? AND generation_status='pending'""", (
                    now(), answer.generation_status, answer.text,
                    json.dumps([asdict(result) for result in answer.results], ensure_ascii=False),
                    answer.model, answer.provider, answer.api_call_id, answer.duration_ms,
                    answer.rag_chunks, answer.context_chars, answer.prompt_tokens,
                    answer.completion_tokens, answer.total_tokens, answer.reasoning_tokens,
                    answer.cached_tokens, answer.raw_model_text, answer.validation_status,
                    answer.validation_reason, answer.generation_reason, answer.scenario,
                    answer.scenario_reason, attempt_id))

    def save_error(self, attempt_id: int, duration_ms: int | None = None) -> None:
        with self.connect() as db:
            db.execute("""UPDATE attempts SET completed_at=?, generation_status='error', duration_ms=?,
                generation_reason='unexpected_exception'
                WHERE id=? AND generation_status='pending'""", (now(), duration_ms, attempt_id))

    def recover_pending(self) -> int:
        """Call once when the single local bot process starts after an interruption."""
        with self.connect() as db:
            cursor = db.execute("""UPDATE attempts SET completed_at=?, generation_status='error',
                generation_reason='process_interrupted'
                WHERE generation_status='pending'""", (now(),))
            return cursor.rowcount

    def rate(self, session_id: str, expert_id: int, attempt_id: int, score: int) -> bool:
        if score not in range(1, 11):
            return False
        with self.connect() as db:
            row = db.execute("""SELECT a.id FROM attempts a JOIN sessions s ON s.id=a.session_id
                WHERE a.id=? AND a.session_id=? AND s.expert_id=? AND s.finished_at IS NULL
                AND a.generation_status IN ('generated','clarification')""",
                (attempt_id, session_id, expert_id)).fetchone()
            if not row:
                return False
            db.execute("""INSERT INTO reviews(attempt_id, score, updated_at) VALUES(?,?,?)
                ON CONFLICT(attempt_id) DO UPDATE SET score=excluded.score, updated_at=excluded.updated_at""",
                (attempt_id, score, now()))
            return True

    def reason(self, session_id: str, expert_id: int, attempt_id: int, reason: str) -> bool:
        with self.connect() as db:
            cursor = db.execute("""UPDATE reviews SET reason=?, updated_at=? WHERE attempt_id=?
                AND EXISTS (SELECT 1 FROM attempts a JOIN sessions s ON s.id=a.session_id
                    WHERE a.id=reviews.attempt_id AND a.session_id=? AND s.expert_id=?
                    AND s.finished_at IS NULL)""", (reason, now(), attempt_id, session_id, expert_id))
            return cursor.rowcount == 1

    def request_comment(self, session_id: str, expert_id: int, attempt_id: int) -> bool:
        with self.connect() as db:
            cursor = db.execute("""UPDATE sessions SET comment_target=? WHERE id=? AND expert_id=?
                AND finished_at IS NULL AND EXISTS (SELECT 1 FROM reviews r JOIN attempts a
                ON a.id=r.attempt_id WHERE r.attempt_id=? AND a.session_id=sessions.id)""",
                (attempt_id, session_id, expert_id, attempt_id))
            return cursor.rowcount == 1

    def save_comment(self, expert_id: int, comment: str) -> bool:
        with self.connect() as db:
            session = db.execute("""SELECT id, comment_target FROM sessions WHERE expert_id=?
                AND finished_at IS NULL AND comment_target IS NOT NULL ORDER BY started_at DESC LIMIT 1""",
                (expert_id,)).fetchone()
            if not session:
                return False
            db.execute("UPDATE reviews SET comment=?, updated_at=? WHERE attempt_id=?",
                       (comment[:2000], now(), session["comment_target"]))
            db.execute("UPDATE sessions SET comment_target=NULL WHERE id=?", (session["id"],))
            return True

    def rows(self, expert_id: int | None = None) -> list[dict]:
        with self.connect() as db:
            query = """SELECT s.id AS session_id, s.specialist_id, s.expert_id AS telegram_id,
                s.started_at, s.finished_at,
                i.ordinal, i.question_id, i.category, i.query, i.expected_topic,
                i.expected_behavior, i.notes, i.question_type, i.expected_document, i.skipped_at,
                a.id AS attempt_id, a.attempt_no,
                a.created_at AS answered_at, a.generation_status, a.answer_text, a.results_json,
                a.model, a.provider, a.api_call_id, a.duration_ms, a.rag_chunks, a.context_chars,
                a.prompt_tokens, a.completion_tokens, a.total_tokens, a.reasoning_tokens, a.cached_tokens,
                a.raw_model_text, a.validation_status, a.validation_reason, a.generation_reason,
                a.scenario, a.scenario_reason,
                r.score, r.reason, r.comment, r.updated_at AS reviewed_at
                FROM sessions s JOIN items i ON i.session_id=s.id
                LEFT JOIN attempts a ON a.session_id=i.session_id AND a.question_id=i.question_id
                LEFT JOIN reviews r ON r.attempt_id=a.id"""
            params = ()
            if expert_id is not None:
                query += " WHERE s.expert_id=?"
                params = (expert_id,)
            query += " ORDER BY s.started_at, i.ordinal, a.attempt_no"
            return [dict(row) for row in db.execute(query, params)]

    def progress(self, session_id: str, expert_id: int) -> tuple[int, int]:
        with self.connect() as db:
            row = db.execute("""SELECT COUNT(DISTINCT r.attempt_id) AS reviewed,
                COUNT(DISTINCT i.question_id) AS total FROM sessions s
                JOIN items i ON i.session_id=s.id LEFT JOIN attempts a
                ON a.session_id=i.session_id AND a.question_id=i.question_id
                LEFT JOIN reviews r ON r.attempt_id=a.id
                WHERE s.id=? AND s.expert_id=?""", (session_id, expert_id)).fetchone()
            return row["reviewed"], row["total"]
