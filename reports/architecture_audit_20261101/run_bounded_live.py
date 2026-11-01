"""Five isolated real-Groq cases; at most 12 HTTP requests, stop at first 429.

No Telegram module is imported. The test store lives under ignored .local and
all Qdrant operations are reads against the existing Stage3 collection.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx
import psutil
from qdrant_client import QdrantClient
from app.ai_coordinator import coordinate
from app.compat import RetrieverRAGAdapter
from app.config import get_settings
from app.conversation_store import ConversationStore
from app.dialogue_understanding import UnderstandingError, understand_message, understanding_to_dict
from app.embeddings import SentenceTransformerEmbedding
from app.groq_rate_limit import allowlist_local_tpm_bypass
from app.llm_client import _generate_once
from app.retrieval import Retriever
from app.source_first_service import SourceFirstService
from app.vector_store import QdrantStore
import app.source_first_service as source_module

HERE = Path(__file__).resolve().parent
COLLECTION = "knowledge_stage3_retrieval_20261022"
MAX_HTTP = 12
IDS = ("EV01", "AQ02", "DB02", "AT01", "SA01")


async def main():
    receipt = json.loads((ROOT / ".local/bot-runtime.json").read_text(encoding="utf-8"))
    worker = psutil.Process(receipt["pid"])
    assert worker.is_running() and receipt["collection"] == COLLECTION
    worker_env = worker.environ()
    for key in ("LLM_PROVIDER", "GROQ_MODEL", "GROQ_REASONING_EFFORT", "RAG_ENGINE",
                "AI_COORDINATOR_ENABLED", "SEMANTIC_EVIDENCE_SELECTOR_ENABLED", "QDRANT_COLLECTION"):
        if key in worker_env:
            os.environ[key] = worker_env[key]
    settings = get_settings()
    assert settings.llm_provider == "groq" and settings.groq_api_key
    assert settings.rag_engine == "source_first" and settings.ai_coordinator_enabled
    assert not settings.semantic_evidence_selector_enabled
    client = QdrantClient(url="http://127.0.0.1:6333", timeout=15)
    info = client.get_collection(COLLECTION)
    assert info.status.value == "green" and info.points_count == 934
    store = object.__new__(QdrantStore)
    store.client, store.embedding, store.collection = (client,
        SentenceTransformerEmbedding("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"), COLLECTION)
    rag = RetrieverRAGAdapter(Retriever(store, demo=False))
    service = SourceFirstService(rag, settings, ROOT)
    source_module.generate = _generate_once  # suppress the normal 429 retry for this bounded experiment
    isolated = ConversationStore(Path(tempfile.mkdtemp(prefix="architecture-audit-", dir=ROOT / ".local")) / "test.sqlite3")
    all_cases = {x["id"]: x for x in (json.loads(line) for line in
        (HERE / "holdout_cases.jsonl").read_text(encoding="utf-8").splitlines())}
    prior_run = (json.loads((HERE / "bounded_live_results.json").read_text(encoding="utf-8"))
                 if (HERE / "bounded_live_results.json").exists() else {"http_used": 0, "cases": []})
    counters = {"http": prior_run["http_used"], "seen_429": prior_run.get("stopped_on_429", False)}
    original_post = httpx.AsyncClient.post

    async def bounded_post(self, url, *args, **kwargs):
        if "api.groq.com" in str(url):
            if counters["http"] >= MAX_HTTP or counters["seen_429"]:
                raise RuntimeError("audit_http_budget_or_429_stop")
            counters["http"] += 1
        response = await original_post(self, url, *args, **kwargs)
        if "api.groq.com" in str(url) and response.status_code == 429:
            counters["seen_429"] = True
        return response

    httpx.AsyncClient.post = bounded_post
    rows = list(prior_run["cases"])
    try:
        for index, case_id in enumerate(IDS, 1):
            if any(x["case_id"] == case_id for x in rows):
                continue
            if counters["http"] >= MAX_HTTP or counters["seen_429"]:
                break
            case = all_cases[case_id]
            question = case["question"]
            uid = 100000 + index  # synthetic identity only in isolated SQLite
            cid = isolated.new(uid, uid)
            before_http = counters["http"]
            before = isolated.dialogue_state(cid)
            try:
                with allowlist_local_tpm_bypass(True):
                    understanding = await understand_message(question, "current", [], before, settings)
                error = None
            except UnderstandingError as exc:
                understanding = None
                error = {"code": exc.code, "phase": exc.phase,
                         "http_status": exc.http_status, "type": type(exc).__name__}
            except Exception as exc:
                understanding = None
                error = {"type": type(exc).__name__}
            answer_id = isolated.begin(cid, question, semantic_mode=True,
                understanding=understanding_to_dict(understanding) if understanding else None,
                understanding_error=error)
            state = isolated.dialogue_state(cid)
            decision = None
            if understanding and not error:
                current = isolated.history(cid)[-1]
                decision = coordinate(current.get("understanding"), state)
                try:
                    with allowlist_local_tpm_bypass(True):
                        answer = await service.answer(question, state=state,
                            history=isolated.history(cid), coordinator_decision=decision)
                except Exception as exc:
                    answer = None
                    error = {"type": type(exc).__name__, "stage": "source_first"}
            else:
                answer = None
            if answer:
                isolated.complete(answer_id, answer)
            rd = answer.retrieval_diagnostics if answer else {}
            rows.append({"case_id": case_id, "question": question, "expected": case["expected"],
                "expected_source": case["source"], "http_calls": counters["http"] - before_http,
                "understanding": (understanding_to_dict(understanding).get("observation")
                                  if understanding else None),
                "state": {"intent": state.intent, "operation": state.operation,
                          "relation": state.relation},
                "coordinator": decision.to_dict() if decision else None,
                "answer": answer.text if answer else None,
                "scenario": answer.scenario if answer else None,
                "scenario_reason": answer.scenario_reason if answer else None,
                "rag_query": answer.rag_query if answer else None,
                "selected_sources": [x.get("source") for x in (rd or {}).get("selected", [])],
                "evidence_status": (rd or {}).get("evidence_status"),
                "error": error})
            print(case_id, "http", counters["http"] - before_http,
                  "scenario", rows[-1]["scenario"], "reason", rows[-1]["scenario_reason"], flush=True)
            if counters["seen_429"] or (error and error.get("type") == "RuntimeError"):
                break
    finally:
        httpx.AsyncClient.post = original_post
    output = {"collection": COLLECTION, "points": info.points_count,
              "http_budget": MAX_HTTP, "http_used": counters["http"],
              "stopped_on_429": counters["seen_429"], "attempted": len(rows),
              "cases": rows}
    (HERE / "bounded_live_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in output.items() if k != "cases"}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
