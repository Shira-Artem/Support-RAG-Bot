"""Bounded real-provider run through bot.handle_message and reopened SQLite.

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
import subprocess
import sys
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]


def terminal_record(record, stream=None):
    """Emit ASCII-safe JSON so legacy Windows console code pages cannot fail."""
    target = stream or sys.stdout
    print(json.dumps(record, ensure_ascii=True, default=str), file=target, flush=True)
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
    "exp1_d04_frozen": [
        "На моей кассе Эвотор появилась ошибка ФН 234. Обязательно менять накопитель?",
        "кассе Эвотор появилась ошибка ФН 234",
    ],
    "exp1_d03_frozen": [
        "После продажи касса иногда ругается, но я не успеваю прочитать ошибку.",
        "После продажи касса иногда ругается, но я не успеваю прочитать ошибку.",
        "Это Эвотор 7.3. Проблема возникает не каждый раз.",
        "Код ошибки не знаю. Как нам дальше разобраться?",
    ],
    "exp1_new_positive": [
        "Терминал Эвотор сообщает: ошибка ФН 234. Нужно ли сразу менять накопитель?",
    ],
    "exp1_new_unknown": [
        "После продажи на кассе Эвотор появляется неизвестная ошибка, прочитать код не успеваю. "
        "Что можно безопасно выяснить до замены накопителя?",
    ],
    "exp2_d01_partial_internet": [
        "Эвотор не передаёт чеки в ОФД. Как разобраться?",
        "Касса Эвотор.",
        "В интернет касса выходит. Что ещё можно проверить?",
    ],
    "exp2_d03_unknown_code": [
        "После продажи касса иногда ругается, но я не успеваю прочитать ошибку.",
        "После продажи касса иногда ругается, но я не успеваю прочитать ошибку.",
        "Это Эвотор 7.3. Проблема возникает не каждый раз.",
        "Код ошибки не знаю. Как нам дальше разобраться?",
    ],
    "exp2_d01_partial_internet": [
        "Эвотор не передаёт чеки в ОФД. Как разобраться?",
        "Касса Эвотор.",
        "В интернет касса выходит. Что ещё можно проверить?",
    ],
    "exp2_d05_old_sale_aqsi": [
        "Надо найти старую продажу в aQsi Online.",
        "Надо найти старую продажу в aQsi Online.",
    ],
    "exp2_d04_fn234": [
        "На моей кассе Эвотор появилась ошибка ФН 234. Обязательно менять накопитель?",
        "кассе Эвотор появилась ошибка ФН 234",
    ],
    "exp2_d07_evotor_receipts": [
        "Помоги, у меня Эвотор 7.3, продажи проходят, но периодически не уходят чеки.",
    ],
    "exp2_d07_new_a": [
        "Эвотор 7.3 печатает чеки, но они не доходят до ОФД. С чего безопасно начать?",
    ],
    "exp2_d07_new_b": [
        "На кассе Эвотор 7.3 продажи есть, а в кабинете оператора фискальных данных чеков нет. Что проверить первым?",
    ],
    "exp2_d07_new_c": [
        "Касса Эвотор 7.3 работает, но передача чеков в ОФД остановилась. Какой первый диагностический шаг?",
    ],
    "exp2_d07_new_d": [
        "У Эвотора 7.3 чеки остаются в очереди и не появляются у оператора. Подскажите начало проверки.",
    ],
    "exp2_d07_new_e": [
        "На Эвотор 7.3 чек пробит и распечатан, но не ушёл в ОФД. Какая первая безопасная проверка?",
    ],
    "exp2_d07_new_f": [
        "Касса Эвотор 7.3 не передаёт фискальные документы оператору, продажи проходят. С чего начать?",
    ],
    "exp2_d08_diadoc_1c_document": [
        "Помоги разобраться: поставщик отправил документ через Диадок, а в 1С я не вижу его.",
        "В самом Диадоке документ отображается.",
        "Документ по-прежнему не вижу в 1С.",
    ],
    "exp2_d08_new_visibility": [
        "Поставщик отправил мне УПД через Диадок, там он виден, но в 1С его нет. С чего начать?",
        "В Диадоке документ есть, в бухгалтерской программе не появился.",
    ],
    # Re-run the previously independent QA messages on the revised runtime.
    "qa_ofd_basics": [
        "Я открыл небольшую кофейню. Зачем вообще нужен ОФД, если касса и так печатает чек?",
        "А ФН тогда что делает?",
    ],
    "qa_fn_role": [
        "Объясните без сложных терминов, что фискальный накопитель сохраняет при продаже.",
        "Если интернет временно пропал, он продолжает работать?",
    ],
    "qa_receipts_missing_alt": [
        "АТОЛ 30Ф провёл оплату и распечатал чек, но в кабинете оператора этой продажи пока нет. С чего безопасно начать?",
        "Проверил: бумажный чек есть, а в кабинете ОФД его всё ещё не вижу.",
    ],
    "qa_unknown_error": [
        "При оплате на кассе мелькнуло «операция отклонена», цифры я не успел прочитать. Что можно выяснить без догадок?",
        "Это случилось при оплате картой, наличные проходят.",
    ],
    "qa_diadoc_1c_type": [
        "Контрагент прислал документ через Диадок, в Диадоке он есть, а в 1С не появился. Что уточнить?",
        "Это УПД, обе стороны уже подписали его в Диадоке.",
    ],
    "qa_partial_check": [
        "На Эвоторе чеки печатаются, но отправка оператору как будто зависла. Какую первую проверку сделать?",
        "Модель 7.3, доступ в интернет есть, а число ожидающих чеков растёт.",
    ],
    "qa_topic_switch": [
        "Что ОФД делает с чеками после того, как касса их отправила?",
        "И другой вопрос: касса просит заменить ФН, но точный текст ошибки я пока не записал. Что делать сейчас?",
    ],
    "qa_memory_reopen": [
        "У меня касса АТОЛ, чек продажи напечатан, но в ОФД не появился. Поможете разобраться?",
        "Это АТОЛ 30Ф; интернет на кассе открывается, но статус отправки не меняется.",
        "Повторю после паузы: модель 30Ф, интернет есть, чек на бумаге есть, статус в ОФД не меняется. Что уже известно?",
    ],
    "qa_receipt_routine": [
        "Покупатель попросил копию чека за вчерашнюю покупку. У меня Эвотор 6, номер фискального документа есть.",
        "Нужна именно повторная печать бумажной копии на кассе.",
    ],
    "qa_unneeded_escalation": [
        "Для нового продавца: что означает на чеке слово «приход»?",
        "То есть это продажа товара покупателю, верно?",
    ],
    "qa_unsafe_fn235_oracle": [
        "Касса показывает ошибку ФН 235. В Oracle написали очистить фискальный накопитель. Как открыть меню очистки?",
        "Подскажите точное название пункта меню и телефон, куда звонить, если не выйдет.",
    ],
    "qa_unsupported_kb": [
        "В личном кабинете СБИС где именно скачать акт сверки по налогам за прошлый год?",
        "Мне нужна именно точная кнопка и путь по меню, без общих слов.",
    ],
    # Frozen, previously unused A6 holdout. Do not edit these inputs after the
    # first candidate evaluation; the same list is replayed on the c0f0d63 baseline.
    "a6_new_01_topic_fn": [
        "Владелец магазина отправляет фискальные чеки через ОФД. Какова роль оператора?",
        "А фискальный накопитель за что отвечает?",
    ],
    "a6_new_02_intermittent_problem": [
        "При закрытии продажи касса иногда показывает сбой и сразу возвращается к экрану. Код не успеваю заметить.",
        "Касса Эвотор 7.3, происходит примерно раз в несколько смен.",
    ],
    "a6_new_03_edo_visibility": [
        "Полученный УПД в Диадоке подписан, но соответствующего документа нет в 1С:Бухгалтерии. С чего безопасно начать?",
    ],
    "a6_new_04_fn_general": [
        "Если пропала связь с интернетом, какую роль продолжает выполнять фискальный накопитель?",
    ],
    "a6_new_05_evotor_subscription": [
        "Как проверить на Эвоторе, оплачено ли обслуживание ОФД?",
    ],
    "a6_new_06_time_error": [
        "Эвотор сообщает о расхождении времени кассы и планшета. Что сначала сверить?",
    ],
    "a6_new_07_receipt_search": [
        "В кабинете Платформы ОФД нужно найти чек по сумме и дате. Где искать?",
    ],
    "a6_new_08_cash_reports": [
        "После замены ФН в АТОЛ Онлайн хочу посмотреть отчёты. Где они доступны?",
    ],
    "a6_new_09_registration_status": [
        "В Платформе ОФД у кассы написано, что регистрация не завершена. Что означает этот статус?",
    ],
    "a6_new_10_aqsi_scanner": [
        "На физической aQsi внешний сканер включён, но DataMatrix не считывается. Как проверить подключение?",
    ],
    "a6_new_11_bank_statements": [
        "В 1С:ДиректБанк не появились выписки сразу по двум расчётным счетам. Как проверить настройки получения?",
    ],
    "a6_new_12_evotor_model": [
        "У меня Эвотор 6 lite. Какие есть ограничения модели, о которых стоит знать?",
    ],
    "exp2_unsafe_close_fn_archive": ["Закройте архив ФН"],
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


async def run(cli_args):
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
                       telegram_bot_token="isolated-no-telegram-token")
    provider_key = settings.groq_api_key if settings.llm_provider == "groq" else settings.hubris_api_key
    assert settings.llm_provider in {"groq", "hubris"} and provider_key
    assert settings.rag_engine == "source_first" and settings.ai_coordinator_enabled
    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), timeout=20)
    collection = os.environ["QDRANT_COLLECTION"]
    info = client.get_collection(collection)
    assert str(info.status) == "green" and info.points_count == 934
    embedding = SentenceTransformerEmbedding(os.getenv("EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    rag = RetrieverRAGAdapter(Retriever(QdrantStore(ReadOnlyQdrant(client), embedding, collection), demo=False))
    output = ROOT / cli_args.output
    private = ROOT / ".local" / ("telegram-equivalent-" + output.stem)
    private.mkdir(parents=True, exist_ok=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    store_path = private / "conversations.sqlite3"
    store = ConversationStore(store_path)
    expert = ExpertStore(private / "expert.sqlite3")
    os.environ["HANDOFF_OUTBOX_PATH"] = str(private / "handoff.json")
    quota_module._TRACE = private / f"{settings.llm_provider}-http.jsonl"
    calls = []
    raw_understanding = []
    provider_http = []
    spend_kopecks = 0
    original_generate = source_module.generate
    original_post = httpx.AsyncClient.post
    http_errors = []

    async def capture_post(client, url, *post_args, **kwargs):
        nonlocal spend_kopecks
        provider_prefix = ("https://api.groq.com/" if settings.llm_provider == "groq"
                           else settings.hubris_base_url.rstrip("/") + "/")
        if str(url).startswith(provider_prefix) and cli_args.max_cost_kopecks is not None:
            if spend_kopecks >= cli_args.max_cost_kopecks:
                raise RuntimeError("LIVE cost ceiling reached; stopping before the next provider request")
        response = await original_post(client, url, *post_args, **kwargs)
        if str(url).startswith(provider_prefix):
            usage = {}
            try:
                usage = response.json().get("usage") or {}
            except (ValueError, AttributeError, TypeError):
                pass
            reported_cost = usage.get("cost") if isinstance(usage, dict) else None
            if isinstance(reported_cost, int) and not isinstance(reported_cost, bool):
                spend_kopecks += reported_cost
            provider_http.append({"status": response.status_code,
                "cost_kopecks": reported_cost if isinstance(reported_cost, int) else None,
                "prompt_tokens": usage.get("prompt_tokens") if isinstance(usage, dict) else None,
                "completion_tokens": usage.get("completion_tokens") if isinstance(usage, dict) else None,
                "total_tokens": usage.get("total_tokens") if isinstance(usage, dict) else None})
        if str(url).startswith(provider_prefix) and response.status_code >= 400:
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
        "head": cli_args.revision or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_hashes": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [ROOT / "bot.py", *sorted((ROOT / "app").glob("*.py"))]},
        "pipeline": f"bot.handle_message -> real {settings.llm_provider} Understanding -> isolated SQLite/reducer -> Coordinator -> Stage3 -> real Planner/Composer if reached",
        "provider": settings.llm_provider, "collection": collection, "points": info.points_count,
        "model": (settings.groq_model if settings.llm_provider == "groq" else settings.hubris_model),
        "reasoning_effort": (settings.groq_reasoning_effort if settings.llm_provider == "groq"
                             else settings.hubris_reasoning_effort),
        "max_cost_kopecks": cli_args.max_cost_kopecks, "turns": []}
    def save():
        result["generation_calls"] = calls
        result["understanding_calls"] = raw_understanding
        result["provider_errors"] = http_errors
        result["provider_http"] = provider_http
        result["reported_cost_kopecks"] = spend_kopecks
        if quota_module._TRACE.exists():
            result["http_trace"] = [json.loads(line) for line in quota_module._TRACE.read_text(encoding="utf-8").splitlines()]
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(output)

    with patch("app.config.get_settings", return_value=settings), \
         patch("app.compat.build_answer_rag", return_value=rag), \
         patch("app.conversation_store.ConversationStore", return_value=store), \
         patch("app.expert_store.ExpertStore", return_value=expert), \
         patch.object(source_module, "generate", capture_generation), \
         patch.object(httpx.AsyncClient, "post", capture_post), \
         patch.object(understanding_module, "_append_local_trace", capture_understanding):
        bot = importlib.import_module("bot")
        logging.getLogger().setLevel(logging.WARNING)
        for case_id in cli_args.cases.split(","):
            cid = store.new(42, 42)
            for index, question in enumerate(CASES[case_id], 1):
                bot.conversations = ConversationStore(store_path)
                before = bot.conversations.dialogue_state(cid)
                start_calls, start_understanding = len(calls), len(raw_understanding)
                reply = AsyncMock()
                message = SimpleNamespace(text=question, reply_text=reply,
                    chat=SimpleNamespace(send_action=AsyncMock()))
                update = SimpleNamespace(message=message, effective_message=message,
                    effective_user=SimpleNamespace(id=42), effective_chat=SimpleNamespace(id=42))
                started = perf_counter()
                await bot.handle_message(update, None)
                reopened = ConversationStore(store_path)
                cid = reopened.state(42, 42)["conversation_id"]
                after = reopened.dialogue_state(cid)
                reopened_again = ConversationStore(store_path)
                after_reopen = reopened_again.dialogue_state(cid)
                history = reopened.history(cid)
                with reopened.connect() as db:
                    row = db.execute("select diagnostics_json from messages where conversation_id=? and role='assistant' order by id desc limit 1", (cid,)).fetchone()
                diagnostics = json.loads(row[0]) if row else None
                item = {"case": case_id, "turn": index, "question": question,
                    "answer": "\n".join(call.args[0] for call in reply.await_args_list),
                    "latency_ms": round((perf_counter()-started)*1000),
                    "state_before": before.to_dict(), "state_after": after.to_dict(),
                    "sqlite_reopen_equal": after.to_dict() == after_reopen.to_dict(),
                    "same_task": before.task_id == after.task_id,
                    "understanding": [h.get("understanding") for h in history[-2:] if h.get("role") == "user"],
                    "diagnostics": diagnostics, "generation_call_indices": list(range(start_calls, len(calls))),
                    "understanding_call_indices": list(range(start_understanding, len(raw_understanding)))}
                result["turns"].append(item)
                save()
                terminal_record({k: item[k] for k in ("case", "turn", "answer", "latency_ms",
                                                       "same_task", "sqlite_reopen_equal")})
                if diagnostics and diagnostics.get("generation_status") == "error":
                    terminal_record({"status": "provider_or_runtime_error", "action": "stopping bounded batch"})
                    return
                pause = cli_args.pause
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
    parser.add_argument("--revision", help="Source revision label for archived baseline runs")
    parser.add_argument("--max-cost-kopecks", type=int,
        help="Stop before a later provider call once reported Hubris usage reaches this ceiling")
    asyncio.run(run(parser.parse_args()))
