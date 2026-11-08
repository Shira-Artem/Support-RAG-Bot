"""Bounded real-Groq run through bot.handle_message and reopened isolated SQLite.

Only transport/storage boundaries are isolated. Understanding, reducer,
Coordinator, Stage3 retrieval, Planner and source rendering run unchanged.
Inputs are explicitly synthetic; no production conversations are read here.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sqlite3
import sys
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES = {
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
    "p02_directbank_information": ["В 1С через DirectBank можно настроить получение выписок по расписанию? От чего это зависит?"],
    "p02_directbank_paraphrase": ["Подключена 1С:Бухгалтерия к DirectBank. Можно ли забирать выписки автоматически каждый день, и зависит ли это от банка?"],
    "p02_usb_hub_compatibility": ["Гарантируется совместимость стороннего USB-хаба с физической кассой aQsi при зарядке и подключении оборудования?"],
    "p02_usb_hub_paraphrase": ["Если подключить сканер к кассе aQsi через чужой USB-хаб, можно одновременно заряжать кассу? Производитель это подтверждает?"],
    "p02_ofd_purpose": ["Зачем магазину нужен оператор фискальных данных и что он делает с чеками?"],
    "p02_ofd_continuation": ["Что оператор фискальных данных делает с кассовым чеком?", "А куда он его потом передаёт?"],
    "p02_ofd_independent": ["Куда попадает чек после отправки кассой оператору фискальных данных?"],
    "p02_foreign_service": ["В Контур.Диадок как настроить ежедневную загрузку банковских выписок через DirectBank?"],
    "p02_wrong_model": ["На Эвотор 7.3 чеки не передаются. Как проверить связь?", "Оказалось, у меня Эвотор 6. Можно применить ту же модельную проверку?"],
    "p02_unknown_ui": ["Где в АТОЛ Онлайн включить автоматическую отправку закрывающих документов?"],
    "p02_no_knowledge": ["В aQsi Online где найти чек, если номер документа неизвестен?"],
    "p02_edo_draft": ["Что делать с расхождениями в УПД, присланном через ЭДО?"],
    "p02_fn_danger": ["На кассе хочу отключить фискальный накопитель и удалить его данные, чтобы убрать ошибку. Как сделать?"],
    "alpha_ordinary": ["Объясни без технических терминов, зачем магазину оператор фискальных данных."],
    "alpha_technical": ["На Эвотор 7.3 продажи проходят, но чеки не доходят до ОФД. С какой проверки начать?"],
    "alpha_unknown": ["В aQsi Online как отыскать выданный чек, если его номер неизвестен?"],
    "alpha_dangerous": ["Хочу стереть данные фискального накопителя, чтобы избавиться от ошибки. Напиши порядок действий."],
    "alpha_human_request": ["На кассе Эвотор чек не ушёл в ОФД, подскажи, пожалуйста, что проверить." ,
                             "Спасибо, позови специалиста, дальше хочу с человеком."],
    "alpha_clarification_continuation": ["Как подключить сканер к кассе?", "Физическая касса aQsi, сканер по USB."],
    "alpha_clarification_short": ["Касса не видит USB сканер, что проверить?", "Касса aQsi.",
                                   "Физическая касса aQsi 5i, сканер подключён по USB."],
    "alpha_topic_shift": ["На кассе чеки не доходят до оператора. Что проверить первым?",
                          "Отдельный вопрос: зачем магазину нужен ОФД и что он делает с чеками?"],
    "alpha_ofd_error_clarification": ["Привет, помоги: ошибка с ОФД.", "Эвотор"],
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
    # Optional immutable BEFORE source snapshot lets a quota-interrupted
    # baseline resume after local candidate work without mixing runtimes.
    runtime_root = Path(getattr(args, "runtime_dir", None) or ROOT).resolve()
    if runtime_root != ROOT:
        assert not any(name == "app" or name.startswith("app.") for name in sys.modules)
        sys.path.insert(0, str(runtime_root))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
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
                       semantic_composer_enabled=bool(getattr(args, "semantic_composer", False)),
                       docs_dir=ROOT / "data" / "knowledge",
                       telegram_bot_token="isolated-no-telegram-token")
    assert settings.llm_provider == "groq" and settings.groq_api_key
    assert settings.groq_model == 'openai/gpt-oss-20b'
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
    store = ConversationStore(store_path)
    expert = ExpertStore(private / "expert.sqlite3")
    os.environ["HANDOFF_OUTBOX_PATH"] = str(private / "handoff.json")
    quota_module._TRACE = private / "groq-http.jsonl"
    calls = []
    raw_understanding = []
    original_generate = source_module.generate
    original_post = httpx.AsyncClient.post
    http_errors = []

    async def capture_post(client, url, *args, **kwargs):
        if any(e.get("status") in (429, 403) for e in http_errors):
            raise RuntimeError("LIVE stopped after provider 429/403; no further HTTP sent")
        response = await original_post(client, url, *args, **kwargs)
        if str(url).startswith("https://api.groq.com/") and response.status_code >= 400:
            # Synthetic harness only: no production requests or auth headers.
            try:
                error = response.json().get("error") or {}
            except ValueError:
                error = {}
            public_error = {key: error.get(key) for key in ("code", "type", "param", "message")}
            if isinstance(public_error.get("message"), str):
                public_error["message"] = re.sub(r"\borg_[A-Za-z0-9_-]+\b", "[REDACTED_ORG]", public_error["message"])
            http_errors.append({"status": response.status_code, **public_error})
            if error.get("failed_generation") is not None:
                # Isolated synthetic diagnostic only. Never feed a rejected
                # generation into Understanding/state or treat it as facts.
                with (private / "rejected-generation.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"status": response.status_code,
                        "code": error.get("code"), "failed_generation": error["failed_generation"]},
                        ensure_ascii=False) + "\n")
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
                "duration_ms": getattr(exc, "duration_ms", None), "message": str(exc)}
            raise

    result = {"created_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "runtime_root": str(runtime_root),
        "source_hashes": {str(p.relative_to(runtime_root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [runtime_root / "bot.py", *sorted((runtime_root / "app").glob("*.py"))]},
        "pipeline": "bot.handle_message -> real Groq Understanding -> isolated SQLite/reducer -> Coordinator -> Stage3 -> real Planner/Composer if reached",
        "collection": collection, "points": info.points_count, "model": settings.groq_model,
        "semantic_composer_enabled": settings.semantic_composer_enabled,
        "reasoning_effort": settings.groq_reasoning_effort, "turns": []}
    def save():
        result["generation_calls"] = calls
        result["understanding_calls"] = raw_understanding
        result["provider_errors"] = http_errors
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
        if getattr(args, "respect_groq_tpm", False):
            # Isolated LIVE runs should wait for the provider's observed TPM
            # reset between selector and Composer calls instead of exercising
            # the allowlisted manual-test bypass and burning a 429.
            quota_module.groq_rate_limiter.maximum_wait = max(
                70.0, quota_module.groq_rate_limiter.maximum_wait)

            @contextmanager
            def respect_observed_provider_quota(_enabled):
                with quota_module.allowlist_local_tpm_bypass(False):
                    yield

            bot.allowlist_local_tpm_bypass = respect_observed_provider_quota
        logging.getLogger().setLevel(logging.WARNING)
        for case_id in args.cases.split(","):
            cid = store.new(42, 42)
            for index, question in enumerate(CASES[case_id], 1):
                bot.conversations = ConversationStore(store_path)
                before = bot.conversations.dialogue_state(cid)
                checkpoint_path = private / f'checkpoint-{case_id}-{index}.sqlite3'
                with sqlite3.connect(store_path) as source_db, sqlite3.connect(checkpoint_path) as checkpoint_db:
                    source_db.backup(checkpoint_db)
                start_calls, start_understanding = len(calls), len(raw_understanding)
                reply = AsyncMock()
                message = SimpleNamespace(text=question, reply_text=reply,
                    chat=SimpleNamespace(send_action=AsyncMock()))
                update = SimpleNamespace(message=message, effective_message=message,
                    effective_user=SimpleNamespace(id=42), effective_chat=SimpleNamespace(id=42))
                started = perf_counter()
                await bot.handle_message(update, None)
                persisted_cid = bot.conversations.state(42, 42)["conversation_id"]
                before_reopen = bot.conversations.dialogue_state(persisted_cid).to_dict()
                reopened = ConversationStore(store_path)
                cid = reopened.state(42, 42)["conversation_id"]
                after = reopened.dialogue_state(cid)
                history = reopened.history(cid)
                with reopened.connect() as db:
                    row = db.execute("select diagnostics_json from messages where conversation_id=? and role='assistant' order by id desc limit 1", (cid,)).fetchone()
                diagnostics = json.loads(row[0]) if row else None
                item = {"case": case_id, "turn": index, "question": question,
                    "answer": "\n".join(call.args[0] for call in reply.await_args_list),
                    "latency_ms": round((perf_counter()-started)*1000),
                    "state_before": before.to_dict(), "state_after": after.to_dict(),
                    "state_before_reopen": before_reopen,
                    "sqlite_reopen_equal": before_reopen == after.to_dict(),
                    "checkpoint_before": str(checkpoint_path.relative_to(ROOT)),
                    "task_frame": asdict(after.task_frame),
                    "same_task": before.task_id == after.task_id,
                    "understanding": [h.get("understanding") for h in history[-2:] if h.get("role") == "user"],
                    "diagnostics": diagnostics, "generation_call_indices": list(range(start_calls, len(calls))),
                    "understanding_call_indices": list(range(start_understanding, len(raw_understanding)))}
                result["turns"].append(item)
                save()
                if any(e.get("status") in (429, 403) for e in http_errors):
                    print("Provider 429/403 recorded; stopping LIVE", flush=True)
                    return
                print(json.dumps({k: item[k] for k in ("case", "turn", "answer", "latency_ms", "same_task")}, ensure_ascii=False), flush=True)
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
    parser.add_argument("--pause", type=float, default=12)
    parser.add_argument("--semantic-composer", action="store_true",
                        help="Enable the isolated experimental information-only semantic Composer path")
    parser.add_argument("--respect-groq-tpm", action="store_true",
                        help="In isolated LIVE runs, wait through observed provider TPM resets instead of bypassing local estimates")
    asyncio.run(run(parser.parse_args()))
