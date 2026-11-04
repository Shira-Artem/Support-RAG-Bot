"""Bounded real-Groq run through bot.handle_message and reopened isolated SQLite.

Only transport/storage boundaries are isolated. Understanding, reducer,
Coordinator, Stage3 retrieval, Planner and source rendering run unchanged.
Inputs are explicitly synthetic; no production conversations are read here.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CASES = {
    "b1_3a_s1_open": [
        "На Эвотор 7.3 чеки остаются на кассе и не доходят до ОФД. Какую проверку сделать первой?"],
    "b1_3a_s1_result": [
        "Диагностический отчёт напечатал."],
    "b1_3a_s1_negative": [
        "Очередь неотправленных документов не уменьшается."],
    "b1_3a_s1_partial": [
        "Интернет работает."],
    "b1_3a_s2_open": [
        "Эвотор 6 печатает чеки, но оператор их не видит. С какой проверки начать?"],
    "b1_3a_s2_open_alt": [
        "На Эвотор 7.3 фискальные документы остаются в очереди и у оператора их нет. Что проверить?"],
    "b1_3a_s2_ambiguous": [
        "Проверил."],
    "b1_3a_s2_explicit": [
        "Диагностический отчёт напечатал."],
    "b1_3a_s2_correction": [
        "Я ошибся: диагностический отчёт не напечатался."],
    "b1_3b_s1": [
        "Очередь неотправленных документов не уменьшается.",
        "Что делать дальше?"],
    "b1_3b_s1_continuation": [
        "Очередь неотправленных документов не уменьшается.",
        "EoU работает, интернет работает, адрес, порт и ИНН ОФД совпадают с актуальными настройками оператора.",
        "Что делать дальше?"],
    "b1_3b_s1_what_next": ["Что делать дальше?"],
    "b1_3b_s2": [
        "Проверил.",
        "Диагностический отчёт напечатал.",
        "Что дальше?"],
    "b1_3b_s2_after_ambiguous": [
        "Диагностический отчёт напечатал."],
    "b1_3b_s2_what_next": ["Что дальше?"],
    "b1_2_saby_final": [
        "Уточнил у поставщика: он отправил УПД, но у меня во входящих его всё ещё нет."],
    "b1_2_evotor": [
        "Эвотор печатает чеки, но оператор ОФД их не получает.",
        "Посмотрел маркировку корпуса: это Эвотор 7.3.",
        "Заодно заметил, что очередь фискальных документов не сокращается."],
    "b1_2_correction": [
        "На Эвотор 7.3 чеки остаются в очереди и не доходят до оператора.",
        "Поправлю себя: модель кассы Эвотор 6, номер 7.3 назвал ошибочно."],
    "b1_2_saby": [
        "В Saby не появился входящий УПД от поставщика, подскажите, где проверить получение.",
        "Номер документа сейчас не знаю; поставщик отправил его сегодня утром.",
        "Уточнил у поставщика: он отправил УПД, но у меня во входящих его всё ещё нет."],
    "b1_1_final_switch_followup": ["В Saby не вижу входящий УПД"],
    "b1_1_final_a": [
        "Помогите разобраться с кассой, пока не знаю, что именно сломалось",
        "Это Эвотор, чеки перестали доходить до ОФД",
        "Модель Эвотор 6, чеки по-прежнему не видны у оператора"],
    "b1_1_final_implicit": [
        "Эвотор 7.3 не отправляет чеки в ОФД",
        "В Saby не вижу входящий УПД"],
    "b1_1_a": [
        "Помогите разобраться с кассой, пока не знаю, что именно сломалось.",
        "Это Эвотор, чеки перестали доходить до ОФД.",
        "Модель Эвотор 6, чеки по-прежнему не видны у оператора."],
    "b1_1_b": [
        "На Эвотор 7.3 чеки пробиваются, но не отправляются в ОФД.",
        "Модель именно Эвотор 7.3.",
        "Проверил подключение к интернету, оно работает. Очередь не уменьшается."],
    "b1_1_c": [
        "Эвотор 7.3 не передаёт чеки в ОФД.",
        "Отдельный вопрос: в Saby не вижу входящий УПД.",
        "Теперь другая задача: в 1С через DirectBank не загружается выписка."],
    "b1_evotor": [
        "На кассе Эвотор чеки оформляются, но до ОФД не доходят. С чего начать?",
        "Модель 7.3. Интернет работает, проверил подключение.",
        "Адрес и порт ОФД сверил с оператором, они совпадают. Что проверить затем?",
        "Очередь документов не уменьшается, отправка не прошла.",
        "Проверку очереди уже выполнил. Какой следующий безопасный шаг?"],
    "b1_clarification": [
        "Помогите разобраться с кассой, не понимаю, что случилось.",
        "Это Эвотор, модель пока не знаю.",
        "Продажи проходят, а фискальные документы оператору не поступают.",
        "Нашёл модель: Эвотор 6. Как проверить передачу?"],
    "b1_switch": [
        "Эвотор 7.3 не отправляет чеки в ОФД, очередь растёт.",
        "Новый вопрос: в Saby не вижу входящий УПД от контрагента.",
        "Ещё отдельная задача: через DirectBank в 1С не загружается выписка. С чего начать?"],
    "b1_contradiction": [
        "На Эвотор 7.3 не уходят чеки в ОФД, интернет работает.",
        "Проверил ещё раз: интернет теперь нестабилен, связь пропадает.",
        "Я ошибся с моделью: это Эвотор 6. Очередь чеков всё ещё растёт.",
        "Интернет восстановил, но передача чеков всё ещё не проходит."],
    "b1_reopen": [
        "В Платформе ОФД хочу найти чек, но не знаю где смотреть.",
        "У меня есть номер фискального документа, модель кассы неизвестна.",
        "После повторного открытия истории: как искать этот чек по номеру ФД?"],
    "b1_repeat_clarification": [
        "С кассой беда, помогите понять причину.",
        "Касса Эвотор 7.3, чеки не доходят до ОФД."],
    "b1_repeat_switch": [
        "В Saby не вижу входящий документ от поставщика.",
        "Теперь другой вопрос: DirectBank перестал загружать выписки в 1С."],
    "b1_fresh_evotor": [
        "На Эвотор 7.3 пробитые чеки висят и не появляются у ОФД. Куда смотреть сначала?",
        "Касса в сети, доступ в интернет есть. Модель именно 7.3.",
        "Сведения о сервере ОФД и порт сверил: они верные.",
        "После проверки очередь отправки осталась той же, чеки не передались.",
        "Что логично проверить дальше, если это уже сделано?"],
    "b1_fresh_clarification": [
        "Нужна помощь с кассовым аппаратом, пока не могу описать сбой.",
        "Это Эвотор, фискальные чеки перестали доходить оператору.",
        "Нашёл шильдик: модель Эвотор 6. Как продолжить проверку?"],
    "b1_fresh_switch": [
        "Эвотор 7.3 перестал передавать чеки в ОФД.",
        "Отдельный вопрос про Saby: поставщик прислал УПД, но я не вижу входящий документ."],
    "pilot_evotor73_exact": ["Эвотор 7.3 пробивает чеки, но они не уходят оператору ОФД. Что посмотреть первым делом?"],
    "pilot_evotor73_prior": ["На Эвотор 7.3 чеки пробиваются, но не передаются в ОФД. С чего начать проверку?"],
    "pilot_evotor73_free_a": ["На кассе Эвотор 7.3 продажи проходят, а у оператора фискальных данных чеков нет. С чего начать диагностику?"],
    "pilot_evotor73_free_b": ["Эвотор 7.3 печатает фискальные документы, но в ОФД они отсутствуют. Какие первые проверки?"],
    "pilot_other_model": ["На Эвотор 6 чеки пробиваются, но не доходят до ОФД. Что проверить вначале?"],
    "pilot_other_vendor": ["АТОЛ 30Ф пробивает чеки, но у ОФД их нет. С чего начать проверку?"],
    "pilot_evotor6": ["У меня Эвотор 6, нужно повторно распечатать старый чек. Номер ФД есть. Как это сделать?"],
    "pilot_ofd_purpose": ["Привет! Объясни простыми словами, зачем нужен ОФД владельцу магазина?"],
    "saby": ["В Saby не могу найти входящий документ."],
    "diadoc": ["Диадок: контрагент не видит отправленный УПД, хочу проверить статус."],
    "ofd": ["Что такое ОФД?"],
    "evotor6": ["Как на Эвотор 6 напечатать копию чека по номеру ФД?"],
    "bifit": ["Нужно протестировать в БИФИТ Общепит работу со столами."],
    "evotor_memory": [
        "На Эвотор 7.3 чеки пробиваются, но не передаются в ОФД. С чего начать проверку?",
        "Интернет проверил, он работает. Подписка ОФД активна. Очередь не уменьшается.",
        "Этот шаг уже проверил, очередь всё ещё не уменьшается. Что дальше?"],
    "evotor_report_memory": [
        "На Эвотор 7.3 чеки пробиваются, но не передаются в ОФД. С чего начать проверку?",
        "Диагностический отчёт напечатал. Интернет работает. Подписка ОФД активна. Очередь не уменьшается.",
        "В отчёте EoU работает, доступ в интернет есть. Адрес, порт и ИНН ОФД совпадают с настройками оператора. Очередь не уменьшается. Что дальше?"],
    "scope_memory": [
        "Как найти чек по номеру фискального документа?",
        "Платформа ОФД.",
        "Нет, теперь ищу тот же чек в АТОЛ Онлайн.",
        "Новый вопрос: что такое ОФД?"],
    "unknown_memory": [
        "На Эвотор чеки не передаются в ОФД. Как проверить связь?",
        "Модель кассы не знаю.",
        "Не знаю модель, уточнить её сейчас не могу.",
        "Новый диалог", "Что такое ОФД?"],
    "platforma": ["В Платформе ОФД хочу проверить статус отправки чека в ФНС. Где посмотреть и что означает статус?"],
    "aqsi": ["Как подключить внешний сканер к физической кассе aQsi?"],
    "aqsi_receipt": ["Где в aQsi Online найти ранее выданный чек?"],
    "aqsi_existing": ["На физической кассе aQsi перестал работать сканер штрихкодов. Как проверить подключение?"],
    "directbank": ["В 1С через DirectBank перестали загружаться банковские выписки. С чего начать?"],
    "atol_api_incident": ["АТОЛ Онлайн: после подтверждённой оплаты API чек не найден."],
    "evotor_combined_payment": ["Эвотор: как работает комбинированная оплата?"],
}


class ReadOnlyQdrant:
    def __init__(self, client):
        self._client = client

    def collection_exists(self, *args, **kwargs):
        return self._client.collection_exists(*args, **kwargs)

    def get_collection(self, *args, **kwargs):
        return self._client.get_collection(*args, **kwargs)

    def scroll(self, *args, **kwargs):
        return self._client.scroll(*args, **kwargs)

    def query_points(self, *args, **kwargs):
        return self._client.query_points(*args, **kwargs)


async def run(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    selected_key = os.getenv(args.api_key_env, "").strip()
    if not selected_key:
        raise ValueError(f"Selected API key variable is empty: {args.api_key_env}")
    # The application reads one Groq key. This bounded test runner can choose
    # either explicitly configured organization without logging its value.
    os.environ["GROQ_API_KEY"] = selected_key
    os.environ.update({"RAG_BACKEND": "qdrant", "QDRANT_COLLECTION": "knowledge_stage3_retrieval_20261022",
        "RAG_DEMO_MODE": "0", "RAG_ENGINE": "source_first", "AI_COORDINATOR_ENABLED": "1",
        "SEMANTIC_EVIDENCE_SELECTOR_ENABLED": "0", "HANDOFF_ENABLED": "0", "HF_HUB_OFFLINE": "1"})
    from qdrant_client import QdrantClient
    from app.compat import RetrieverRAGAdapter
    from app.config import get_settings
    from app.conversation_store import ConversationStore
    from app.expert_store import ExpertStore
    from app.embeddings import SentenceTransformerEmbedding
    from app.retrieval import Retriever
    from app.vector_store import QdrantStore
    import app.source_first_service as source_module
    import app.dialogue_understanding as understanding_module
    import app.groq_rate_limit as quota_module
    import httpx

    settings = replace(get_settings(), source_first_telegram_ids=frozenset({42}),
                       telegram_bot_token="isolated-no-telegram-token")
    assert settings.llm_provider == "groq" and settings.groq_api_key
    assert settings.rag_engine == "source_first" and settings.ai_coordinator_enabled
    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), timeout=20)
    collection = os.environ["QDRANT_COLLECTION"]
    info = client.get_collection(collection)
    assert str(info.status) == "green" and info.points_count == 934
    embedding = SentenceTransformerEmbedding(os.getenv("EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    rag = RetrieverRAGAdapter(Retriever(QdrantStore(ReadOnlyQdrant(client), embedding, collection), demo=False))
    output = ROOT / args.output
    private = ROOT / ".local" / ("telegram-equivalent-" + output.stem)
    private.mkdir(parents=True, exist_ok=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    store_path = private / "conversations.sqlite3"
    if args.resume_sqlite:
        source = Path(args.resume_sqlite).resolve()
        local_root = (ROOT / ".local").resolve()
        if not source.is_file() or local_root not in source.parents or source.name != "conversations.sqlite3":
            raise ValueError("Resume source must be an existing isolated .local conversations.sqlite3")
        with sqlite3.connect(source) as source_db, sqlite3.connect(store_path) as target_db:
            source_db.backup(target_db)
    store = ConversationStore(store_path)
    expert = ExpertStore(private / "expert.sqlite3")
    os.environ["HANDOFF_OUTBOX_PATH"] = str(private / "handoff.json")
    quota_module._TRACE = private / "groq-http.jsonl"
    calls = []
    raw_understanding = []
    original_generate = source_module.generate
    original_post = httpx.AsyncClient.post
    http_errors = []
    http_attempts = []
    rate_limit_pacing = []
    last_rate_limit_headers = {}
    stopped_on_429 = False

    async def capture_post(client, url, *post_args, **kwargs):
        nonlocal stopped_on_429, last_rate_limit_headers
        if not str(url).startswith("https://api.groq.com/"):
            return await original_post(client, url, *post_args, **kwargs)
        if len(http_attempts) >= args.max_http or stopped_on_429:
            raise RuntimeError("B1 live HTTP budget exhausted or provider 429")
        request_json = kwargs.get("json") or {}
        raw_remaining = last_rate_limit_headers.get("x-ratelimit-remaining-tokens")
        remaining = int(raw_remaining) if raw_remaining is not None else None
        token_limit = int(last_rate_limit_headers.get("x-ratelimit-limit-tokens") or 0)
        estimated = quota_module.estimate_tokens(request_json)
        if token_limit and remaining is not None and estimated > remaining:
            reset = quota_module._seconds(
                last_rate_limit_headers.get("x-ratelimit-reset-tokens"))
            wait_seconds = (reset if reset is not None else 60.0) + 1.0
            rate_limit_pacing.append({"before_http_attempt": len(http_attempts) + 1,
                "estimated_tokens": estimated, "remaining_tokens": remaining,
                "token_limit": token_limit,
                "estimate_exceeds_full_window": estimated > token_limit,
                "reset_seconds": reset,
                "wait_seconds": round(wait_seconds, 2), "reason": "observed_tpm_headroom"})
            print(json.dumps({"rate_limit_wait_seconds": round(wait_seconds, 2),
                "reason": "observed_tpm_headroom"}), flush=True)
            await asyncio.sleep(wait_seconds)
        attempt = {"number": len(http_attempts) + 1, "status": None}
        http_attempts.append(attempt)
        try:
            response = await original_post(client, url, *post_args, **kwargs)
        except Exception as exc:
            attempt["error_type"] = type(exc).__name__
            raise
        attempt["status"] = response.status_code
        last_rate_limit_headers = quota_module.public_headers(response.headers)
        if response.status_code == 429:
            stopped_on_429 = True
        if response.status_code >= 400:
            try:
                error = response.json().get("error") or {}
            except ValueError:
                error = {}
            http_errors.append({"status": response.status_code,
                "code": error.get("code") if isinstance(error.get("code"), str) else None,
                "type": error.get("type") if isinstance(error.get("type"), str) else None,
                "param": error.get("param") if isinstance(error.get("param"), str) else None,
                "category": ("provider_json_generation_failed"
                    if error.get("code") == "json_validate_failed" else
                    "provider_rejected_request_schema"
                    if error.get("param") in {"response_format", "messages"} else None),
                "message": (re.sub(r"org_[A-Za-z0-9_-]+", "[REDACTED_ORG]",
                            re.sub(r"gsk_[A-Za-z0-9_-]+", "[REDACTED_KEY]", error["message"]))[:500]
                            if isinstance(error.get("message"), str) else None),
                "failed_generation_present": error.get("failed_generation") is not None})
        return response

    def capture_understanding(**record):
        # Safe synthetic inputs only; retain provider JSON and field decisions.
        raw_understanding.append(record)
        with (private / "understanding.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    async def capture_generation(messages, config, *, call_stage="generation"):
        record = {"stage": call_stage, "input": messages}
        calls.append(record)
        try:
            result = await original_generate(messages, config, call_stage=call_stage)
            record["result"] = asdict(result)
            return result
        except Exception as exc:
            record["error"] = {"type": type(exc).__name__, "http_status": getattr(exc, "http_status", None),
                "duration_ms": getattr(exc, "duration_ms", None), "message": str(exc),
                "provider_error_category": getattr(exc, "provider_error_category", None),
                "schema_error": getattr(exc, "schema_error", None),
                "provider_error_code": getattr(exc, "provider_error_code", None),
                "provider_error_param": getattr(exc, "provider_error_param", None),
                "provider_usage": getattr(exc, "provider_usage", None)}
            raise

    result = {"created_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "api_key_env": args.api_key_env,
        "source_hashes": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [ROOT / "bot.py", *sorted((ROOT / "app").glob("*.py"))]},
        "pipeline": "bot.handle_message -> real Groq Understanding -> isolated SQLite/reducer -> Coordinator -> Stage3 -> real Planner/Composer if reached",
        "collection": collection, "points": info.points_count, "model": settings.groq_model,
        "reasoning_effort": settings.groq_reasoning_effort, "turns": []}
    def save():
        result["generation_calls"] = calls
        result["understanding_calls"] = raw_understanding
        result["provider_errors"] = http_errors
        result["http_attempts"] = http_attempts
        result["rate_limit_pacing"] = list(rate_limit_pacing)
        result["stopped_on_429"] = stopped_on_429
        if quota_module._TRACE.exists():
            result["http_trace"] = [json.loads(line) for line in quota_module._TRACE.read_text(encoding="utf-8").splitlines()]
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    with patch("app.config.get_settings", return_value=settings), \
         patch("app.compat.build_answer_rag", return_value=rag), \
         patch("app.conversation_store.ConversationStore", return_value=store), \
         patch("app.expert_store.ExpertStore", return_value=expert), \
         patch.object(source_module, "generate", capture_generation), \
         patch.object(httpx.AsyncClient, "post", capture_post), \
         patch.object(understanding_module, "_append_local_trace", capture_understanding):
        bot = importlib.import_module("bot")
        logging.getLogger().setLevel(logging.WARNING)
        for case_index, case_id in enumerate(args.cases.split(",")):
            cid = (store.state(42, 42)["conversation_id"]
                   if args.resume_sqlite and case_index == 0 else store.new(42, 42))
            if not cid:
                raise ValueError("Isolated resume SQLite has no active conversation")
            for index, question in enumerate(CASES[case_id], 1):
                bot.conversations = ConversationStore(store_path)
                before = bot.conversations.dialogue_state(cid)
                start_calls, start_understanding, start_http = len(calls), len(raw_understanding), len(http_attempts)
                reply = AsyncMock()
                message = SimpleNamespace(text=question, reply_text=reply,
                    chat=SimpleNamespace(send_action=AsyncMock()))
                update = SimpleNamespace(message=message, effective_message=message,
                    effective_user=SimpleNamespace(id=42), effective_chat=SimpleNamespace(id=42))
                started = perf_counter()
                await bot.handle_message(update, None)
                persisted = bot.conversations.dialogue_state(cid)
                reopened = ConversationStore(store_path)
                cid = reopened.state(42, 42)["conversation_id"]
                after = reopened.dialogue_state(cid)
                roundtrip_equal = persisted.to_dict() == after.to_dict()
                history = reopened.history(cid)
                with reopened.connect() as db:
                    row = db.execute("select diagnostics_json from messages where conversation_id=? and role='assistant' order by id desc limit 1", (cid,)).fetchone()
                diagnostics = json.loads(row[0]) if row else None
                item = {"case": case_id, "turn": index, "conversation_id": cid,
                    "question": question,
                    "answer": "\n".join(call.args[0] for call in reply.await_args_list),
                    "latency_ms": round((perf_counter()-started)*1000),
                    "state_before": before.to_dict(), "state_after": after.to_dict(),
                    "state_before_reopen": persisted.to_dict(),
                    "frame_before": asdict(before.task_frame), "frame_after": asdict(after.task_frame),
                    "sqlite_reopened": True, "sqlite_roundtrip_equal": roundtrip_equal,
                    "http_attempts": http_attempts[start_http:],
                    "same_task": before.task_id == after.task_id,
                    "understanding": [h.get("understanding") for h in history[-2:] if h.get("role") == "user"],
                    "diagnostics": diagnostics, "generation_call_indices": list(range(start_calls, len(calls))),
                    "understanding_call_indices": list(range(start_understanding, len(raw_understanding)))}
                result["turns"].append(item)
                save()
                print(json.dumps({k: item[k] for k in ("case", "turn", "answer", "latency_ms", "same_task")}, ensure_ascii=True), flush=True)
                if stopped_on_429 or len(http_attempts) >= args.max_http:
                    print("Provider 429 or hard HTTP budget reached; stopping live batch", flush=True)
                    return
                if diagnostics and diagnostics.get("generation_status") == "error":
                    print("Provider/runtime error recorded; stopping bounded batch", flush=True)
                    return
                pause = args.pause
                # Use observed provider TPM headroom between synthetic turns.
                # This harness scheduling does not alter runtime retry policy.
                if result.get("http_trace"):
                    headers = result["http_trace"][-1].get("rate_limit_headers") or {}
                    limit = int(headers.get("x-ratelimit-limit-tokens") or 0)
                    remaining = int(headers.get("x-ratelimit-remaining-tokens") or 0)
                    if limit:
                        pause = max(pause, (limit * .92 - remaining) * 60 / limit + 2)
                await asyncio.sleep(max(0, pause))
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="saby,diadoc,ofd,evotor6,bifit")
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-key-env", choices=("GROQ_API_KEY", "GROQ_API_KEY_2"),
                        default="GROQ_API_KEY")
    parser.add_argument("--pause", type=float, default=12)
    parser.add_argument("--max-http", type=int, default=58)
    parser.add_argument("--resume-sqlite")
    asyncio.run(run(parser.parse_args()))
