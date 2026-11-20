"""Durable single-writer conversation gateway with revision and publication fencing.

Each accepted input is generated once. An ambiguous/crashed generation is never
rerun implicitly. CRM must acknowledge its durable publication before a new turn.
SQLite is the existing store, on a private persistent volume (one API process).
"""
import asyncio
from dataclasses import asdict
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from app.answer_service import Answer
from app.conversation_store import ConversationStore
from app.secret_safety import redact_client_secrets
from app.support_contract import AckRequest, ReplyRequest, ReplyResponse
from app.support_turn import run_turn


def safe_text(text):
    text = redact_client_secrets(text)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}', '[EMAIL]', text)
    return re.sub(r'(?<!\d)\+?\d(?:[ ()-]*\d){9,14}(?!\d)', '[PERSONAL_NUMBER]', text)


class SupportGateway:
    def __init__(self, path, runtime_factory=None, *, timeout=90):
        self.store = ConversationStore(Path(path))
        self.runtime_factory = runtime_factory
        self.runtime = None
        self.timeout = timeout
        with self.store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS crm_sessions (
                    ticket TEXT PRIMARY KEY, conversation TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS crm_replies (
                    ticket TEXT NOT NULL, message TEXT NOT NULL, digest TEXT NOT NULL,
                    reply_id TEXT UNIQUE NOT NULL, state TEXT NOT NULL, started REAL NOT NULL,
                    response TEXT, answer_json TEXT, assistant_id INTEGER,
                    PRIMARY KEY(ticket,message));
            ''')

    def state(self, ticket):
        with self.store.connect() as db:
            row = db.execute('SELECT revision FROM crm_sessions WHERE ticket=?', (ticket,)).fetchone()
            return {'revision': row['revision'] if row else 0, 'contract_version': '1'}

    def _finalize(self, request, reply_id, answer, assistant_id=None):
        status = ('error' if answer.generation_status == 'error' else
                  'escalate' if answer.scenario == 'escalate' or answer.generation_status == 'no_context' else
                  'clarify' if answer.scenario == 'clarify' else 'answered')
        # Only expose sources carried by the final validated answer, never raw top-k.
        sources = []
        seen_sources = set()
        diagnostics = answer.retrieval_diagnostics or {}
        evidence = diagnostics.get('coordinator_evidence') or {}
        selected_sources = set(evidence.get('sources') or [])
        if evidence.get('source'):
            selected_sources.add(evidence['source'])
        # Standard procedural answers cite the exact selected source in their
        # final text. Retrieval hits alone never become confirmed citations.
        if status == 'answered' and answer.validation_status not in ('not_run', 'rejected', 'failed'):
            for hit in answer.results:
                meta = hit.metadata or {}
                if meta.get('status') == 'approved' and (hit.source in selected_sources or hit.source in answer.text):
                    source_id = str(meta.get('document_id') or hit.source)
                    if source_id not in seen_sources:
                        sources.append({'id': source_id, 'title': meta.get('title')})
                        seen_sources.add(source_id)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE crm_sessions SET revision=revision+1 WHERE ticket=?', (request.ticket_id,))
            revision = db.execute('SELECT revision FROM crm_sessions WHERE ticket=?', (request.ticket_id,)).fetchone()[0]
            response = ReplyResponse(ticket_id=request.ticket_id, message_id=request.message_id,
                reply_id=reply_id, revision=revision, answer=answer.text, status=status, sources=sources,
                escalation_reason=(answer.scenario_reason or answer.generation_reason) if status in ('escalate', 'error') else None,
                diagnostics={'provider': answer.provider, 'model': answer.model,
                    'understanding_model': (answer.dialogue_understanding or {}).get('model'),
                    'answer_used_model': int(answer.used_model),
                    'generation_status': answer.generation_status, 'validation_status': answer.validation_status,
                    'duration_ms': answer.duration_ms, 'collection': answer.retrieval_collection})
            db.execute("UPDATE crm_replies SET state='ready',response=?,answer_json=?,assistant_id=? WHERE reply_id=?",
                       (response.model_dump_json(), json.dumps(asdict(answer), ensure_ascii=False), assistant_id, reply_id))
        return response

    async def reply(self, request):
        if not request.text.strip():
            raise HTTPException(422, 'text cannot be blank')
        payload = request.model_dump(exclude={'expected_revision'})
        payload['text'] = safe_text(request.text)
        digest = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        interrupted = False
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM crm_replies WHERE ticket=? AND message=?',
                             (request.ticket_id, request.message_id)).fetchone()
            if old:
                if old['digest'] != digest:
                    raise HTTPException(409, 'idempotency_conflict')
                if old['response']:
                    return ReplyResponse.model_validate_json(old['response'])
                if time.time() - old['started'] < self.timeout + 30:
                    raise HTTPException(409, 'request_in_progress', headers={'Retry-After': '2'})
                interrupted = True
                reply_id = old['reply_id']
                db.execute("UPDATE crm_replies SET state='processing',started=? WHERE reply_id=?", (time.time(), reply_id))
            else:
                row = db.execute('SELECT * FROM crm_sessions WHERE ticket=?', (request.ticket_id,)).fetchone()
                revision = row['revision'] if row else 0
                if request.expected_revision != revision:
                    raise HTTPException(409, 'revision_conflict')
                if db.execute("SELECT 1 FROM crm_replies WHERE ticket=? AND state IN ('processing','ready')", (request.ticket_id,)).fetchone():
                    raise HTTPException(409, 'previous_reply_requires_ack')
                if row is None:
                    conversation = uuid4().hex
                    db.execute('INSERT INTO conversations VALUES(?,?,?,?)', (conversation, 0, 0, str(time.time())))
                    db.execute('INSERT INTO crm_sessions VALUES(?,?,0)', (request.ticket_id, conversation))
                else:
                    conversation = row['conversation']
                reply_id = uuid4().hex
                db.execute("INSERT INTO crm_replies(ticket,message,digest,reply_id,state,started) VALUES(?,?,?,?,'processing',?)",
                           (request.ticket_id, request.message_id, digest, reply_id, time.time()))
        if interrupted:
            # Crash recovery closes pending events without inventing a shown check.
            with self.store.connect() as db:
                conversation = db.execute('SELECT conversation FROM crm_sessions WHERE ticket=?', (request.ticket_id,)).fetchone()[0]
                pending = [r[0] for r in db.execute("SELECT id FROM messages WHERE conversation_id=? AND status='pending'", (conversation,))]
            for mid in pending:
                self.store.fail_delivery(mid)
            return self._finalize(request, reply_id, Answer('Обработка была прервана. Передайте вопрос специалисту.',
                generation_status='error', scenario='escalate', scenario_reason='interrupted_generation'))
        assistant_id = None
        try:
            if self.runtime is None:
                if self.runtime_factory is None:
                    from app.support_runtime import build_support_runtime
                    self.runtime = build_support_runtime(self.store)
                else:
                    self.runtime = self.runtime_factory(self.store)
            async with asyncio.timeout(self.timeout):
                assistant_id, answer = await run_turn(self.runtime, conversation, payload['text'], 0, source_first=True)
        except Exception as exc:
            # Do not expose raw provider errors or retry ambiguous paid calls.
            with self.store.connect() as db:
                pending = [r[0] for r in db.execute("SELECT id FROM messages WHERE conversation_id=? AND status='pending'", (conversation,))]
            for mid in pending:
                self.store.fail_delivery(mid)
            answer = Answer('Сервис временно недоступен. Вопрос можно передать специалисту.',
                            generation_status='error', scenario='escalate', scenario_reason='service_unavailable',
                            generation_reason=type(exc).__name__)
        return self._finalize(request, reply_id, answer, assistant_id)

    def ack(self, ticket, ack):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM crm_replies WHERE ticket=? AND reply_id=?', (ticket, ack.reply_id)).fetchone()
            if row is None:
                raise HTTPException(404, 'reply_not_found')
            state = 'accepted' if ack.accepted else 'discarded'
            if row['state'] in ('accepted', 'discarded'):
                if row['state'] != state:
                    raise HTTPException(409, 'ack_conflict')
                return {'state': state}
            if row['state'] != 'ready':
                raise HTTPException(409, 'reply_not_ready')
            # Complete snapshot and publication receipt in one SQLite transaction.
            if row['assistant_id']:
                answer = json.loads(row['answer_json'])
                db.execute("UPDATE messages SET content=?,status=?,diagnostics_json=? WHERE id=? AND status='pending'",
                           (answer['text'], 'complete' if ack.accepted else 'failed', row['answer_json'], row['assistant_id']))
                conversation = db.execute('SELECT conversation FROM crm_sessions WHERE ticket=?', (ticket,)).fetchone()[0]
                self.store._sync_state(db, conversation)
            db.execute('UPDATE crm_replies SET state=? WHERE reply_id=?', (state, ack.reply_id))
        return {'state': state}


def support_router(gateway_factory=None):
    router = APIRouter()
    gateway = None

    def authorize(authorization: str | None = Header(default=None)):
        token = os.getenv('RAG_SERVICE_TOKEN', '')
        if len(token) < 32:
            raise HTTPException(503, 'service_auth_not_configured')
        if not hmac.compare_digest(authorization or '', 'Bearer ' + token):
            raise HTTPException(401, 'unauthorized')

    def service():
        nonlocal gateway
        if gateway is None:
            gateway = gateway_factory() if gateway_factory else SupportGateway(
                os.getenv('RAG_API_DB_PATH', '.local/crm-api/conversations.sqlite3'),
                timeout=float(os.getenv('RAG_API_TIMEOUT_SECONDS', '90')))
        return gateway

    @router.post('/v1/support/reply', response_model=ReplyResponse, dependencies=[Depends(authorize)])
    async def reply(request: ReplyRequest):
        return await service().reply(request)

    @router.get('/v1/support/state/{ticket}', dependencies=[Depends(authorize)])
    def state(ticket: str):
        return service().state(ticket)

    @router.post('/v1/support/ack/{ticket}', dependencies=[Depends(authorize)])
    def ack(ticket: str, request: AckRequest):
        return service().ack(ticket, request)

    @router.get('/readyz', dependencies=[Depends(authorize)])
    def ready():
        try:
            from app.config import get_settings
            from qdrant_client import QdrantClient
            settings = get_settings(require_telegram_allowlist=False)
            if settings.rag_engine != 'source_first':
                raise ValueError('SourceFirst not configured')
            if settings.llm_provider == 'hubris' and not settings.hubris_api_key:
                raise ValueError('Provider not configured')
            with service().store.connect() as db:
                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('State unavailable')
            client = QdrantClient(url=os.getenv('QDRANT_URL', 'http://127.0.0.1:6333'), timeout=3)
            try:
                index = client.get_collection(os.environ['QDRANT_COLLECTION'])
                if str(index.status) != 'green' or not index.points_count:
                    raise ValueError('Index unavailable')
            finally:
                client.close()
            return {'status': 'ok', 'state': 'ok', 'index': 'green'}
        except Exception:
            raise HTTPException(503, 'dependencies_unavailable') from None

    return router
