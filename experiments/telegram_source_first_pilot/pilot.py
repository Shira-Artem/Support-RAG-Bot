from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from experiments.evidence_first_vertical.prototype import (  # noqa: E402
    index_documents, norm, sections,
)
from experiments.vnext.stage3_retrieval import ReadOnlyStage3, scope_compatible  # noqa: E402
from app.dialogue_state import DialogueManager, DialogueState  # noqa: E402
from app.response_grounding import unsafe_operation_issue  # noqa: E402

MODEL = "openai/gpt-oss-20b"
DB_PATH = HERE / "data" / "pilot.sqlite3"
TRACE_DIR = HERE / "traces"
FREE_MENU = ReplyKeyboardMarkup([["Новый диалог"]], resize_keyboard=True)
MAX_TURNS = 12
MAX_HISTORY_CHARS = 7000
MAX_SECTION_CHARS = 5000
MAX_TOTAL_SOURCE_CHARS = 16000

# Broad stop words for irreversible/fiscal/security-sensitive procedures. This
# is intentionally a deny gate, not a service-specific procedure catalog.
HIGH_RISK = re.compile(
    r"\b(?:перерегистр\w*.{0,50}(?:ккт|касс\w*|фн)|"
    r"(?:замен|сним|установ|запис|закры|обнул|инициализ|сброс|форматир)\w*.{0,40}"
    r"(?:фн|фискальн\w* накопител\w*|архив|ккт|касс\w*|настро\w*)|"
    r"(?:закры|закрой|заверш)\w*.{0,30}(?:смен\w*|архив)|"
    r"возврат\w*|сторно|удален\w*.{0,30}(?:касс\w*|чек\w*|фн|документ\w*))\b", re.I | re.S)


def risk_issue(text: str) -> str | None:
    return unsafe_operation_issue(text) or ("high_risk_action" if HIGH_RISK.search(text) else None)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_value(name: str, default: str = "") -> str:
    return os.getenv(name, _ENV.get(name, default)).strip()


_ENV = dotenv_values(HERE / ".env.pilot")


@dataclass
class Section:
    id: str
    document_id: str
    title: str
    heading: str
    service: str | None
    model: str | None
    rank: int
    text: str
    source_path: str
    source_sha256: str


def section_groups(retrieval: dict, messages: list[str], index: dict) -> tuple[list[Section], list[dict]]:
    groups, rejected, seen, used_chars = [], [], set(), 0
    for hit in retrieval.get("hybrid_raw_candidates", []):
        doc_id = hit.get("document_id")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        if doc_id not in index:
            rejected.append({"document_id": doc_id, "reason": "local_source_missing"})
            continue
        path, meta, body = index[doc_id]
        if meta.get("status") != "approved" or hit.get("status") != "approved":
            rejected.append({"document_id": doc_id, "reason": "not_approved"})
            continue
        ok, why = scope_compatible(hit, messages)
        if not ok:
            rejected.append({"document_id": doc_id, "reason": why})
            continue
        if len(groups) >= 28:
            break
        for heading, text in sections(body):
            if not text.strip() or len(text) > MAX_SECTION_CHARS:
                rejected.append({"document_id": doc_id, "section": heading, "reason": "section_empty_or_too_long"})
                continue
            if used_chars + len(text) > MAX_TOTAL_SOURCE_CHARS:
                rejected.append({"document_id": doc_id, "section": heading, "reason": "total_source_context_limit"})
                break
            groups.append(Section(f"G{len(groups)+1}", doc_id, meta.get("title") or doc_id,
                                 heading, meta.get("service"), meta.get("model"),
                                 int(hit.get("rank") or 999), text.strip(),
                                 str(path.relative_to(ROOT)).replace("\\", "/"),
                                 sha256(path.read_bytes()).hexdigest()))
            used_chars += len(text)
            if len(groups) >= 28:
                break
        if len(groups) >= 28:
            break
    return groups, rejected


def applicable(section: Section, messages: list[str], index: dict) -> tuple[bool, str]:
    path, meta, body = index[section.document_id]
    if meta.get("status") != "approved":
        return False, "source_not_approved"
    if sha256(path.read_bytes()).hexdigest() != section.source_sha256 or section.text not in body:
        return False, "source_changed_or_text_mismatch"
    ok, reason = scope_compatible({"service": section.service, "model": section.model}, messages)
    if not ok:
        return False, reason
    # Require the exact whole source section and never expose high-risk steps.
    if risk_issue(section.text):
        return False, "high_risk_procedure_requires_human"
    return True, "approved_exact_section_scope_compatible"


class PilotStore:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
              chat_id INTEGER NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active');
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
              role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, trace_json TEXT);
            CREATE INDEX IF NOT EXISTS pilot_messages_conversation ON messages(conversation_id,id);
            CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
              answer_id INTEGER NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
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

    def start(self, user: int, chat: int) -> str:
        cid = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO conversations VALUES(?,?,?,?,'active')", (cid, user, chat, now()))
        return cid

    def history(self, cid: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
        return [dict(r) for r in rows]

    def append(self, cid: str, role: str, content: str, trace: dict | None = None) -> int:
        with self.connect() as db:
            cur = db.execute("INSERT INTO messages(conversation_id,role,content,created_at,trace_json) VALUES(?,?,?,?,?)",
                             (cid, role, content, now(), json.dumps(trace, ensure_ascii=False) if trace else None))
            return cur.lastrowid

    def enqueue(self, cid: str, answer_id: int, reason: str) -> int:
        with self.connect() as db:
            cur = db.execute("INSERT INTO queue(conversation_id,answer_id,status,reason,created_at) VALUES(?,?,'open',?,?)",
                             (cid, answer_id, reason, now()))
            return cur.lastrowid


class SourceFirstPilot:
    def __init__(self, store: ReadOnlyStage3):
        self.store = store
        self.index = index_documents()

    def answer(self, conversation: list[dict]) -> tuple[str, dict]:
        all_user_messages = [m["content"] for m in conversation if m["role"] == "user"][-MAX_TURNS:]
        dialogue_state, task_start = DialogueState(), 0
        manager = DialogueManager()
        for index, message in enumerate(all_user_messages):
            previous_id = dialogue_state.task_id
            dialogue_state = manager.advance(dialogue_state, message, index + 1)
            if index and previous_id and dialogue_state.transition == "new_task":
                task_start = index
        messages = all_user_messages[task_start:]
        latest = messages[-1]
        task_text = "\n".join(messages)[-MAX_HISTORY_CHARS:]
        started = time.perf_counter()
        trace: dict = {"at": now(), "messages": conversation, "active_task": task_text,
                       "dialogue_state": dialogue_state.to_dict(),
                       "model": MODEL, "groq_usage": None, "errors": []}
        if risk_issue(task_text):
            trace.update({"retrieval":None,"applicability_safety":{"applicable":False,
                           "reason":"user_requested_high_risk_operation"},
                          "final_mode":"escalate","escalation_reason":"user_requested_high_risk_operation",
                          "final_answer":"Запрошенная операция требует проверки специалистом. Обращение можно сохранить в тестовую очередь; реальная доставка специалисту не подключена.",
                          "latency_ms":round((time.perf_counter()-started)*1000)})
            return trace["final_answer"], trace
        try:
            _, retrieval = self.store.search_with_trace(task_text[-500:], messages, query_origin="raw_user_question")
            trace["retrieval"] = retrieval
            groups, rejected = section_groups(retrieval, messages, self.index)
            trace["rejected_candidates"] = rejected
            trace["sections"] = [asdict(g) for g in groups]
        except Exception as exc:
            trace["errors"].append({"stage": "qdrant", "type": type(exc).__name__, "message": str(exc)[:240]})
            trace["latency_ms"] = round((time.perf_counter() - started) * 1000)
            trace.update({"final_mode":"escalate","escalation_reason":"qdrant_error",
                          "final_answer":"Не удалось безопасно проверить подтверждённые материалы. Я сохранил обращение в тестовую очередь; реальная доставка специалисту не подключена."})
            return trace["final_answer"], trace
        history = [{"role": x["role"], "content": x["content"]} for x in conversation[-MAX_TURNS*2:]]
        prompt = {"task": "Select source evidence for the customer's current task. Return JSON only.",
                  "conversation": history, "active_task": task_text,
                  "dialogue_state": dialogue_state.to_dict(),
                  "rules": ["Select one whole section only if it applies to the exact task; otherwise clarify once or escalate.",
                            "Technical instructions will be copied exactly from approved source, preserving all conditions, warnings, and order.",
                            "Never invent or rewrite technical steps. High risk procedures must escalate.",
                            "Do not repeat a question already answered or already asked. Escalate instead.",
                            "Different services, models, operations, and objects are not interchangeable.",
                            "There is no live specialist delivery; escalation means a pilot test queue only."],
                  "sections": [{k: getattr(g,k) for k in ("id","document_id","title","heading","service","model","rank","text")} for g in groups],
                  "schema": {"mode":"answer|clarify|escalate", "section_id":"G-number or null",
                             "clarification":"one short question or null", "reason":"short internal reason"}}
        trace["planner_prompt"] = prompt
        key = env_value("PILOT_GROQ_API_KEY")
        try:
            payload = {"model": MODEL, "reasoning_effort": "medium", "temperature": 0,
                       "max_completion_tokens": 1200, "response_format": {"type":"json_object"},
                       "messages":[{"role":"user","content":json.dumps(prompt,ensure_ascii=False)}]}
            t = time.perf_counter()
            response = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                                  headers={"Authorization":f"Bearer {key}"}, json=payload, timeout=75)
            trace["llm_ms"] = round((time.perf_counter()-t)*1000)
            if response.status_code != 200:
                raise RuntimeError(f"Groq HTTP {response.status_code}: {response.text[:200]}")
            body = response.json()
            trace["groq_usage"] = body.get("usage")
            proposal = json.loads(body["choices"][0]["message"]["content"])
            trace["proposal"] = proposal
        except Exception as exc:
            trace["errors"].append({"stage":"groq", "type":type(exc).__name__, "message":str(exc)[:240]})
            trace["latency_ms"] = round((time.perf_counter()-started)*1000)
            trace.update({"final_mode":"escalate","escalation_reason":"groq_error",
                          "final_answer":"Не удалось получить проверяемый план ответа. Я сохранил обращение в тестовую очередь; реальная доставка специалисту не подключена."})
            return trace["final_answer"], trace

        mode = proposal.get("mode")
        section = next((g for g in groups if g.id == proposal.get("section_id")), None)
        trace["applicability_safety"] = {"mode":mode, "section_id":proposal.get("section_id")}
        if mode == "answer" and section:
            ok, reason = applicable(section, messages, self.index)
            trace["applicability_safety"].update({"applicable":ok,"reason":reason})
            if ok:
                final = f"По подтверждённому материалу «{section.title}», раздел «{section.heading}»:\n{section.text}\n\nЕсли это не решит вопрос, можно нажать «Позвать специалиста»; обращение сохранится только в тестовой очереди."
                trace["final_mode"]="answer"
            else:
                mode = "escalate"
        elif mode == "clarify":
            question = proposal.get("clarification")
            asked = " ".join(m["content"] for m in conversation if m["role"] == "assistant")
            previous_questions = sum("?" in m["content"] or "？" in m["content"]
                                     for m in conversation if m["role"] == "assistant")
            if (isinstance(question,str) and question.strip() and len(question) <= 300
                    and norm(question) not in norm(asked) and previous_questions == 0):
                final = question.strip() + " Если хотите, можно сразу нажать «Позвать специалиста»."
                trace["final_mode"]="clarify"
                trace["clarification_reason"] = proposal.get("reason")
            else:
                mode = "escalate"
                trace["clarification_reason"]="invalid_or_repeated_clarification"
        if trace.get("final_mode") != "answer" and trace.get("final_mode") != "clarify":
            final = "В доступных подтверждённых материалах не получилось установить применимое решение. Обращение можно сохранить в тестовую очередь кнопкой ниже; реальная доставка специалисту не подключена."
            trace["final_mode"]="escalate"
            trace["escalation_reason"] = trace.get("clarification_reason") or proposal.get("reason") or "no_verified_applicable_section"
        trace["final_answer"] = final
        trace["latency_ms"] = round((time.perf_counter()-started)*1000)
        return final, trace


def allowed_ids() -> set[int]:
    raw = env_value("PILOT_TELEGRAM_USER_IDS")
    return {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}


def redact(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}", "[EMAIL]", text)
    text = re.sub(r"(?<!\d)(?:\+?\d[\s()-]*){10,15}(?!\d)", "[PHONE_OR_ID]", text)
    text = re.sub(r"\b\d{10,12}\b", "[LONG_ID]", text)
    return text


def scrub_trace(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [scrub_trace(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub_trace(item) for key, item in value.items()
                if key not in {"telegram_user_id", "telegram_chat_id", "at", "created_at"}}
    return value


def export_anonymized(path: Path) -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute("SELECT c.id,m.role,m.content,m.trace_json,m.created_at FROM messages m JOIN conversations c ON c.id=m.conversation_id ORDER BY m.id").fetchall()
    grouped: dict[str,list[dict]] = {}
    for cid, role, content, raw, created in rows:
        trace = json.loads(raw) if raw else None
        if trace:
            trace.pop("messages", None)
            trace.pop("active_task", None)
            trace = scrub_trace(trace)
        grouped.setdefault(cid, []).append({"role":role,"content":redact(content),"trace":trace})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w",encoding="utf-8") as out:
        for turns in grouped.values():
            out.write(json.dumps({"messages":turns},ensure_ascii=False)+"\n")
    return len(grouped)


def run_smoke() -> dict:
    index = index_documents()
    approved = [(doc_id, item) for doc_id, item in index.items() if item[1].get("status") == "approved"]
    assert approved, "No local approved source documents found"
    doc_id, (path, meta, body) = approved[0]
    parsed = sections(body)
    assert parsed and all(heading and text.strip() for heading, text in parsed)
    eligible = None
    for candidate_id, (candidate_path, candidate_meta, candidate_body) in approved:
        for heading, text in sections(candidate_body):
            candidate = Section("G1", candidate_id, candidate_meta.get("title") or candidate_id,
                                heading, candidate_meta.get("service"), candidate_meta.get("model"),
                                1, text.strip(), str(candidate_path.relative_to(ROOT)).replace("\\", "/"),
                                sha256(candidate_path.read_bytes()).hexdigest())
            context = " ".join(str(candidate_meta.get(k) or "") for k in
                               ("service", "manufacturer", "model", "title", "document_id"))
            if applicable(candidate, [context], index)[0]:
                eligible = candidate
                break
        if eligible:
            break
    assert eligible, "No locally applicable exact approved section found for the verifier smoke"
    altered = Section(**{**asdict(eligible), "source_sha256":"0" * 64})
    assert applicable(altered, [eligible.service or eligible.title], index) == (False, "source_changed_or_text_mismatch")
    assert risk_issue("Не выполнять сброс ФН")
    assert not risk_issue("Ошибка ФН, касса не отправляет данные")
    assert "[EMAIL]" in redact("mail a@example.com")
    exported_trace = scrub_trace({"at":"2026-10-25T12:00:00Z","text":"a@example.com"})
    assert "at" not in exported_trace and exported_trace["text"] == "[EMAIL]"
    long_answer = "Первый шаг.\n" + ("Условие и предупреждение. " * 220)
    telegram_parts = split_message(long_answer)
    assert len(telegram_parts) > 1 and all(len(part) <= 3900 for part in telegram_parts)
    assert "Условие и предупреждение." in " ".join(telegram_parts)
    class FailingSearch:
        def search_with_trace(self, *args, **kwargs):
            raise RuntimeError("simulated Qdrant unavailable")
    guarded = SourceFirstPilot(FailingSearch())
    fallback, failed_trace = guarded.answer([{"role":"user","content":"Касса не передаёт данные"}])
    assert failed_trace["final_mode"] == "escalate" and failed_trace["errors"][0]["stage"] == "qdrant"
    assert "тестовую очередь" in fallback and "не подключена" in fallback
    dangerous, dangerous_trace = guarded.answer([{"role":"user","content":"Как закрыть архив ФН?"}])
    assert dangerous_trace["escalation_reason"] == "user_requested_high_risk_operation"
    assert "тестовую очередь" in dangerous and dangerous_trace["retrieval"] is None
    with tempfile.TemporaryDirectory(prefix="source-first-pilot-") as tmp:
        isolated = PilotStore(Path(tmp) / "pilot.sqlite3")
        cid = isolated.start(10001, 20002)
        uid = isolated.append(cid, "user", "Тестовый вопрос")
        aid = isolated.append(cid, "assistant", "Тестовый ответ", {"final_mode":"answer"})
        queue_id = isolated.enqueue(cid, aid, "smoke")
        assert isolated.history(cid) == [{"role":"user","content":"Тестовый вопрос"},
                                         {"role":"assistant","content":"Тестовый ответ"}]
        with isolated.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 1
    return {"passed":True,"checks":["local_approved_source_index", "whole_section_parser",
            "approved_sha_scope_applicability_gate", "source_hash_mutation_rejection",
            "high_risk_gate", "qdrant_error_safe_escalation", "dangerous_request_safe_escalation",
            "PII_redaction_and_timestamp_removal", "telegram_length_splitting",
            "isolated_sqlite_conversation_and_queue"],
            "sample_document_id":doc_id,"sample_section_count":len(parsed),"database":"temporary_only",
            "qdrant_touched":False,"external_llm_calls":0,"telegram_worker":"not_started"}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in allowed_ids():
        await update.effective_message.reply_text("Пилот закрыт для этого аккаунта.")
        return
    context.user_data.pop("conversation_id", None)
    await new_dialogue(update, context)


async def identify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(f"Ваш Telegram user ID: {update.effective_user.id}")


async def new_dialogue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in allowed_ids():
        await update.effective_message.reply_text("Пилот закрыт для этого аккаунта.")
        return
    context.user_data["conversation_id"] = STORE.start(update.effective_user.id, update.effective_chat.id)
    await update.effective_message.reply_text("Начат новый тестовый диалог. Напишите вопрос своими словами.", reply_markup=FREE_MENU)


def split_message(text: str, max_len: int = 3900) -> list[str]:
    parts = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at <= 0:
            split_at = max_len
        parts.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if update.effective_user.id not in allowed_ids():
        return
    try:
        _, raw = q.data.split(":",1)
        answer_id=int(raw)
        with STORE.connect() as db:
            row=db.execute("SELECT conversation_id FROM messages WHERE id=? AND role='assistant'",(answer_id,)).fetchone()
            own=db.execute("SELECT id FROM conversations WHERE id=? AND user_id=? AND chat_id=?",
                           (row["conversation_id"],update.effective_user.id,update.effective_chat.id)).fetchone() if row else None
        if not own:
            raise ValueError("not owner")
        item=STORE.enqueue(row["conversation_id"],answer_id,"user_requested_specialist")
        await q.message.reply_text(f"Обращение №{item} сохранено в тестовой очереди. Реальная доставка специалисту не подключена.")
    except Exception:
        await q.message.reply_text("Не удалось сохранить обращение в тестовую очередь.")


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in allowed_ids():
        return
    text=(update.effective_message.text or "").strip()
    if text == "Новый диалог":
        await new_dialogue(update,context); return
    cid=context.user_data.get("conversation_id")
    if not cid:
        await new_dialogue(update,context); return
    history=STORE.history(cid)
    STORE.append(cid,"user",text)
    conversation=history+[{"role":"user","content":text}]
    result,trace=await asyncio.to_thread(ENGINE.answer,conversation)
    aid=STORE.append(cid,"assistant",result,trace)
    trace_dir=TRACE_DIR/cid
    trace_dir.mkdir(parents=True,exist_ok=True)
    with (trace_dir/"turns.jsonl").open("a",encoding="utf-8") as f:
        f.write(json.dumps({"answer_id":aid,**trace},ensure_ascii=False)+"\n")
    if trace.get("final_mode")=="escalate" or trace.get("errors"):
        STORE.enqueue(cid,aid,trace.get("escalation_reason","system_error"))
    markup=InlineKeyboardMarkup([[InlineKeyboardButton("Позвать специалиста",callback_data=f"sp:{aid}")]])
    parts=split_message(result)
    for position, part in enumerate(parts):
        await update.effective_message.reply_text(part,reply_markup=markup if position==len(parts)-1 else None)


def build_receipt() -> dict:
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    files=[HERE/"__init__.py",HERE/"pilot.py",ROOT/"app/dialogue_state.py",
           ROOT/"app/response_grounding.py",ROOT/"app/retrieval.py",ROOT/"app/embeddings.py",ROOT/"experiments/evidence_first_vertical/planner.py",
           ROOT/"experiments/evidence_first_vertical/prototype.py",ROOT/"experiments/vnext/stage3_retrieval.py"]
    return {"commit":head,"files_sha256":{str(p.relative_to(ROOT)).replace("\\","/"):sha256(p.read_bytes()).hexdigest()
              for p in files if p.exists()},"model":MODEL,"qdrant_collection":"knowledge_stage3_retrieval_20261022",
            "embedding_model":env_value("PILOT_EMBEDDING_MODEL","sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
            "worker":"not_started","token_present":bool(env_value("PILOT_TELEGRAM_BOT_TOKEN")),
            "groq_key_present":bool(env_value("PILOT_GROQ_API_KEY")),
            "allowlist_count":len(allowed_ids()),"database":str(DB_PATH.relative_to(ROOT)),"created_at":now()}


@contextmanager
def single_pilot_instance(token: str):
    lock_path = HERE / "data" / ("polling-" + sha256(token.encode()).hexdigest()[:20] + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if lock_path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("A pilot polling worker already holds this token lock") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def main():
    global STORE, ENGINE
    if len(sys.argv)>1 and sys.argv[1]=="export":
        output=Path(sys.argv[2]) if len(sys.argv)>2 else HERE/"exports"/f"pilot-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        print(f"Exported {export_anonymized(output)} conversations to {output}"); return
    if len(sys.argv)>1 and sys.argv[1]=="preflight":
        report=build_receipt()
        report["preflight"]={"python":sys.version.split()[0],"required_env":["PILOT_TELEGRAM_BOT_TOKEN","PILOT_TELEGRAM_USER_IDS","PILOT_GROQ_API_KEY"],
                             "external_llm_calls":0,"qdrant_touched":False,"worker":"not_started"}
        print(json.dumps(report,ensure_ascii=False,indent=2)); return
    if len(sys.argv)>1 and sys.argv[1]=="preflight-qdrant":
        qurl=env_value("PILOT_QDRANT_URL","http://127.0.0.1:6333")
        if qurl != "http://127.0.0.1:6333":
            raise SystemExit("Pilot is pinned to the local read-only Qdrant endpoint http://127.0.0.1:6333")
        try:
            store=ReadOnlyStage3(qurl,env_value("PILOT_EMBEDDING_MODEL","sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
        except Exception as exc:
            print(json.dumps({"read_only_inventory_check":"failed","endpoint":qurl,
                              "error_type":type(exc).__name__,"error":str(exc)[:240],
                              "writes_performed":False,"external_llm_calls":0,
                              "telegram_worker":"not_started"},ensure_ascii=False,indent=2))
            raise SystemExit(2)
        print(json.dumps({"read_only_inventory_check":"passed","qdrant":store.receipt,
                          "search_performed":False,"writes_performed":False,
                          "external_llm_calls":0,"telegram_worker":"not_started"},ensure_ascii=False,indent=2))
        return
    if len(sys.argv)>1 and sys.argv[1]=="smoke":
        print(json.dumps(run_smoke(),ensure_ascii=False,indent=2)); return
    if len(sys.argv)>1 and sys.argv[1]=="identify":
        token=env_value("PILOT_TELEGRAM_BOT_TOKEN")
        if not token:
            raise SystemExit("PILOT_TELEGRAM_BOT_TOKEN is required; production TELEGRAM_BOT_TOKEN is never read")
        app=Application.builder().token(token).concurrent_updates(False).build()
        app.add_handler(CommandHandler("id",identify))
        with single_pilot_instance(token):
            app.run_polling()
        return
    token=env_value("PILOT_TELEGRAM_BOT_TOKEN")
    raw_ids=env_value("PILOT_TELEGRAM_USER_IDS")
    ids=allowed_ids()
    if not token: raise SystemExit("PILOT_TELEGRAM_BOT_TOKEN is required; production TELEGRAM_BOT_TOKEN is never read")
    if not ids: raise SystemExit("PILOT_TELEGRAM_USER_IDS must contain at least one numeric Telegram user ID")
    if any(not item.strip().isdigit() for item in raw_ids.split(",")):
        raise SystemExit("PILOT_TELEGRAM_USER_IDS must be comma-separated numeric IDs only")
    if not env_value("PILOT_GROQ_API_KEY"):
        raise SystemExit("PILOT_GROQ_API_KEY is required; no fallback answer generation is enabled")
    qurl=env_value("PILOT_QDRANT_URL","http://127.0.0.1:6333")
    if qurl != "http://127.0.0.1:6333":
        raise SystemExit("Pilot is pinned to the local read-only Qdrant endpoint http://127.0.0.1:6333")
    STORE=PilotStore()
    qdrant=ReadOnlyStage3(qurl,env_value("PILOT_EMBEDDING_MODEL","sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    ENGINE=SourceFirstPilot(qdrant)
    receipt=build_receipt(); receipt.update({"worker":"starting","qdrant":qdrant.receipt})
    (HERE/"preflight-receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    app=Application.builder().token(token).concurrent_updates(False).build()
    app.add_handler(CommandHandler("id",identify)); app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("new",new_dialogue))
    app.add_handler(CommandHandler("export",lambda u,c: u.effective_message.reply_text("Для безопасного экспорта выполните локально: python -m experiments.telegram_source_first_pilot.pilot export")))
    app.add_handler(CallbackQueryHandler(callback,pattern=r"^sp:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle))
    with single_pilot_instance(token):
        app.run_polling()


if __name__ == "__main__":
    main()
