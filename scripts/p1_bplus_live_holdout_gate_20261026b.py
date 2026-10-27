"""Bounded B+ live holdout gate. Never imports bot.py or sends Telegram; uses temp SQLite and read-only Qdrant."""
from __future__ import annotations

import argparse
import asyncio
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
from time import perf_counter
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from qdrant_client import QdrantClient
from app.ai_coordinator import coordinate
from app.config import get_settings
from app.conversation_store import ConversationStore
from app.dialogue_understanding import UnderstandingError, understanding_to_dict
import app.dialogue_understanding as understanding_module
from app.embeddings import SentenceTransformerEmbedding
from app.compat import RetrieverRAGAdapter
from app.retrieval import Retriever
from app.semantic_evidence_selector import build_evidence_units
import app.semantic_evidence_selector as selector_module
import app.source_first_service as source_first_module
from app.source_first_service import SourceFirstService, _source_sections, _focused_approved_sentence, _section_has_answer_bearing_content
from app.vector_store import QdrantStore

HOLDOUT_PATH = ROOT / "experiments/architecture_recovery_audit/p1_unified_live_gate_holdout_20261026b.json"
DEFAULT_OUTPUT = ROOT / "experiments/architecture_recovery_audit/p1_unified_live_gate_trace_20261026b.json"
STAGE3_COLLECTION = "knowledge_stage3_retrieval_20261022"
MAX_GROQ_HTTP_ATTEMPTS = 8
RATE_STAGE = ContextVar("rag_live_rate_stage", default="unclassified")
HTTP_ATTEMPTS: list[dict] = []
LATEST_RATE: dict = {}
QUOTA_STOP: str | None = None


class ReadOnlyQdrantClient:
    """Expose only read operations needed by the retriever."""
    def __init__(self, client): self.__client = client
    def collection_exists(self, collection): return self.__client.collection_exists(collection)
    def get_collection(self, collection): return self.__client.get_collection(collection)
    def scroll(self, collection, **kwargs): return self.__client.scroll(collection, **kwargs)
    def query_points(self, collection, **kwargs): return self.__client.query_points(collection, **kwargs)


class QuotaStop(RuntimeError):
    pass


def _rate_headers(response) -> dict:
    headers = getattr(response, "headers", {}) or {}
    keys = ("retry-after", "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
            "x-ratelimit-reset-requests", "x-ratelimit-limit-tokens",
            "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens")
    return {key: headers[key] for key in keys if key in headers}


def _quota_sufficient_for(payload: dict | None) -> tuple[bool, str | None]:
    if not LATEST_RATE:
        return False, "rate_limit_headers_unavailable"
    try:
        remaining_requests = int(LATEST_RATE["x-ratelimit-remaining-requests"])
        remaining_tokens = int(LATEST_RATE["x-ratelimit-remaining-tokens"])
    except (KeyError, ValueError, TypeError):
        return False, "required_remaining_quota_header_missing"
    # Groq's remaining-token header is TPM. Estimate this next request from the
    # serialized input plus a modest output reserve; actual usage is also saved.
    serialized = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))
    input_estimate = math.ceil(len(serialized) / 3)
    reserve = 512
    needed = input_estimate + reserve
    if remaining_requests < 1:
        return False, "no_remaining_request_quota"
    if remaining_tokens < needed:
        return False, f"remaining_token_quota_below_estimate:{remaining_tokens}<{needed}"
    return True, None


def _install_http_accounting() -> None:
    original_post = httpx.AsyncClient.post

    async def tracked_post(client, url, *args, **kwargs):
        global LATEST_RATE, QUOTA_STOP
        if not str(url).startswith("https://api.groq.com/"):
            return await original_post(client, url, *args, **kwargs)
        if len(HTTP_ATTEMPTS) >= MAX_GROQ_HTTP_ATTEMPTS:
            QUOTA_STOP = "hard_groq_http_attempt_cap_reached"
            raise QuotaStop(QUOTA_STOP)
        request_json = kwargs.get("json") if isinstance(kwargs.get("json"), dict) else {}
        enough, reason = _quota_sufficient_for(request_json) if HTTP_ATTEMPTS else (True, None)
        if not enough:
            QUOTA_STOP = reason
            raise QuotaStop(reason)
        attempt = {"number": len(HTTP_ATTEMPTS) + 1, "stage": RATE_STAGE.get(),
                   "started_at_utc": datetime.now(timezone.utc).isoformat(),
                   "http_status": None, "latency_ms": None, "usage": None,
                   "rate_limit_headers": {}, "error_type": None}
        HTTP_ATTEMPTS.append(attempt)  # count every attempted POST before network I/O
        started = perf_counter()
        try:
            response = await original_post(client, url, *args, **kwargs)
            attempt["http_status"] = response.status_code
            attempt["rate_limit_headers"] = _rate_headers(response)
            LATEST_RATE = attempt["rate_limit_headers"]
            try:
                payload = response.json()
                usage = payload.get("usage") if isinstance(payload, dict) else None
                if isinstance(usage, dict):
                    attempt["usage"] = {key: usage.get(key) for key in
                        ("prompt_tokens", "completion_tokens", "total_tokens")
                        if isinstance(usage.get(key), int)}
            except (ValueError, TypeError):
                pass
            return response
        except Exception as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                attempt["http_status"] = getattr(response, "status_code", None)
                attempt["rate_limit_headers"] = _rate_headers(response)
                LATEST_RATE = attempt["rate_limit_headers"]
            attempt["error_type"] = type(exc).__name__
            raise
        finally:
            attempt["latency_ms"] = round((perf_counter() - started) * 1000)

    httpx.AsyncClient.post = tracked_post

    original_understanding = understanding_module.understand_message
    async def tracked_understanding(*args, **kwargs):
        token = RATE_STAGE.set("understanding")
        try: return await original_understanding(*args, **kwargs)
        finally: RATE_STAGE.reset(token)
    understanding_module.understand_message = tracked_understanding

    original_selector_generate = selector_module.generate
    async def tracked_selector_generate(*args, **kwargs):
        token = RATE_STAGE.set("evidence_decision")
        try: return await original_selector_generate(*args, **kwargs)
        finally: RATE_STAGE.reset(token)
    selector_module.generate = tracked_selector_generate

    original_source_generate = source_first_module.generate
    async def tracked_source_generate(*args, **kwargs):
        token = RATE_STAGE.set("source_first_planner_or_composer")
        try: return await original_source_generate(*args, **kwargs)
        finally: RATE_STAGE.reset(token)
    source_first_module.generate = tracked_source_generate


def _preflight(settings) -> dict:
    issues=[]
    if settings.llm_provider != "groq" or not settings.groq_api_key: issues.append("groq_not_configured")
    if settings.rag_engine != "source_first" or not settings.ai_coordinator_enabled: issues.append("source_first_coordinator_not_enabled")
    if not settings.semantic_evidence_selector_enabled: issues.append("semantic_evidence_selector_not_enabled_for_harness")
    if os.getenv("RAG_BACKEND", "qdrant").strip().lower() != "qdrant": issues.append("qdrant_backend_required")
    if os.getenv("RAG_DEMO_MODE", "0").strip().lower() in {"1", "true", "yes"}: issues.append("demo_mode_must_be_off")
    collection=os.getenv("QDRANT_COLLECTION", "")
    if collection != STAGE3_COLLECTION: issues.append("stage3_collection_required")
    if issues: return {"configured":False,"issues":issues,"qdrant_collection":collection}
    try:
        client=QdrantClient(url=os.getenv("QDRANT_URL","http://127.0.0.1:6333"), timeout=8)
        exists=client.collection_exists(collection)
        info=client.get_collection(collection) if exists else None
    except Exception as exc:
        return {"configured":False,"issues":["qdrant_read_only_preflight_failed"],"failure_type":type(exc).__name__,"qdrant_collection":collection}
    result={"configured":bool(exists and info and (info.points_count or 0)>0
                             and str(info.status)=="green"),"issues":[],
            "qdrant_collection":collection,"qdrant_exists":exists,
            "qdrant_points":(info.points_count or 0) if info else 0,
            "qdrant_status":str(info.status) if info else "missing",
            "qdrant_mode":"read-only; collection_exists/get_collection only in preflight"}
    if not result["configured"]: result["issues"]=["qdrant_collection_missing_or_empty"]
    return result


def _state_ledger(state) -> dict:
    full=state.to_dict()
    task=full.get("task_context") or {}
    return {"task_id":task.get("task_id"),"intent":task.get("intent"),"operation":task.get("operation"),
            "object":task.get("object"),"entities":task.get("entities"),"error":task.get("error"),
            "procedure_id":task.get("procedure_id"),"shown_units":task.get("shown_units"),
            "eligible_units":task.get("eligible_units"),"checks":task.get("checks"),
            "open_question":task.get("open_question"),"current_subgoal":task.get("current_subgoal"),
            "closed":task.get("closed"),"task_relation":task.get("relation")}


async def _run(settings, holdout: dict, preflight: dict) -> dict:
    global QUOTA_STOP
    os.environ["HF_HUB_OFFLINE"]="1"
    embedding=SentenceTransformerEmbedding(os.getenv("EMBEDDING_MODEL","sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    client=QdrantClient(url=os.getenv("QDRANT_URL","http://127.0.0.1:6333"),timeout=15)
    collection=preflight["qdrant_collection"]
    rag=RetrieverRAGAdapter(Retriever(QdrantStore(ReadOnlyQdrantClient(client),embedding,collection),demo=False))
    last_retrieval=[]
    raw_search=rag.search_for_state
    def recording_search(state,query):
        result=raw_search(state,query)
        last_retrieval.append(result)
        return result
    rag.search_for_state=recording_search
    service=SourceFirstService(rag,settings,settings.docs_dir.parent.parent)
    turns=[]
    usage_totals={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
    with tempfile.TemporaryDirectory(prefix="support-rag-stage4b-") as temp:
        for scenario in holdout["scenarios"]:
            store=ConversationStore(Path(temp)/(scenario["id"]+".sqlite3"))
            conversation=store.new(1,1)
            for turn_index,item in enumerate(scenario["turns"],1):
                if len(HTTP_ATTEMPTS)>=MAX_GROQ_HTTP_ATTEMPTS:
                    QUOTA_STOP="hard_groq_http_attempt_cap_reached"
                    return _result("STOPPED",scenario["id"],turns,usage_totals,preflight)
                question=item["question"]
                before=store.dialogue_state(conversation)
                history=store.history(conversation)
                attempt_start=len(HTTP_ATTEMPTS)
                try:
                    understanding=await understanding_module.understand_message(
                        question,"current",history,before,settings)
                except UnderstandingError as exc:
                    turns.append({"scenario":scenario["id"],"turn":turn_index,"question":question,
                        "understanding_status":"failed","provider_error":{"http_status":exc.http_status,
                        "error_type":exc.error_type,"duration_ms":exc.duration_ms},
                        "http_attempts":HTTP_ATTEMPTS[attempt_start:]})
                    return _result("BLOCKED",scenario["id"],turns,usage_totals,preflight)
                # The first planned Understanding request also serves as the
                # actual quota check; do not continue without live remaining headers.
                if not LATEST_RATE:
                    turns.append({"scenario":scenario["id"],"turn":turn_index,"question":question,
                        "understanding_raw":understanding.structured_response,
                        "understanding_validated":understanding_to_dict(understanding),
                        "status":"blocked_after_quota_probe","reason":"rate_limit_headers_unavailable",
                        "http_attempts":HTTP_ATTEMPTS[attempt_start:]})
                    QUOTA_STOP="rate_limit_headers_unavailable"
                    return _result("BLOCKED",scenario["id"],turns,usage_totals,preflight)
                try:
                    message_id=store.begin(conversation,question,semantic_mode=True,
                        understanding=understanding_to_dict(understanding))
                except Exception as exc:
                    turns.append({"scenario":scenario["id"],"turn":turn_index,"question":question,
                        "status":"state_write_failed","error_type":type(exc).__name__,
                        "http_attempts":HTTP_ATTEMPTS[attempt_start:]})
                    return _result("BLOCKED",scenario["id"],turns,usage_totals,preflight)
                state=store.dialogue_state(conversation)
                history=store.history(conversation)
                user_event=next((e for e in reversed(history) if e.get("role")=="user" and e.get("content")==question),{})
                decision=coordinate(user_event.get("understanding"),state)
                enough,reason=_quota_sufficient_for({"messages":[{"role":"user","content":"evidence decision"}]})
                if not enough:
                    QUOTA_STOP=reason
                    turns.append({"scenario":scenario["id"],"turn":turn_index,"question":question,
                        "understanding_raw":understanding.structured_response,
                        "understanding_validated":understanding_to_dict(understanding),
                        "coordinator_decision":decision.to_dict(),"progress_ledger_before":_state_ledger(before),
                        "progress_ledger_after_understanding":_state_ledger(state),
                        "status":"blocked_before_service_due_quota","reason":reason,
                        "http_attempts":HTTP_ATTEMPTS[attempt_start:]})
                    return _result("BLOCKED",scenario["id"],turns,usage_totals,preflight)
                diagnostics_before=len(last_retrieval)
                try:
                    answer=await service.answer(question,state=state,history=history,coordinator_decision=decision)
                except QuotaStop as exc:
                    QUOTA_STOP=str(exc)
                    answer=None
                except Exception as exc:
                    answer=None
                    service_error={"error_type":type(exc).__name__}
                else:
                    service_error=None
                if answer is None:
                    turns.append({"scenario":scenario["id"],"turn":turn_index,"question":question,
                        "understanding_raw":understanding.structured_response,
                        "understanding_validated":understanding_to_dict(understanding),
                        "coordinator_decision":decision.to_dict(),"progress_ledger_before":_state_ledger(before),
                        "progress_ledger_after_understanding":_state_ledger(state),"status":"provider_or_budget_blocked",
                        "reason":QUOTA_STOP,"service_error":service_error,
                        "http_attempts":HTTP_ATTEMPTS[attempt_start:]})
                    return _result("BLOCKED",scenario["id"],turns,usage_totals,preflight)
                store.complete(message_id,answer)
                after=store.dialogue_state(conversation)
                new_retrieval=last_retrieval[diagnostics_before:]
                lexical=None
                if new_retrieval:
                    retrieved=new_retrieval[-1]
                    sections=_source_sections(rag,retrieved,settings.docs_dir.parent.parent)
                    if state.intent=="general" and state.operation=="explain":
                        sections=[section for section in sections if _section_has_answer_bearing_content(section)]
                    focus=decision.current_subgoal or question
                    match=_focused_approved_sentence(sections,focus)
                    lexical={"answer":match[1] if match else None,
                             "document_id":match[0].get("document_id") if match else None,
                             "source":match[0].get("source") if match else None,
                             "section":match[0].get("section") if match else None,
                             "source_sha256":match[0].get("source_sha256") if match else None,
                             "same_saved_retrieval":True}
                diagnostics=answer.retrieval_diagnostics or {}
                selector=diagnostics.get("semantic_evidence_selector") or {}
                calls=HTTP_ATTEMPTS[attempt_start:]
                for call in calls:
                    for key in usage_totals:
                        n=(call.get("usage") or {}).get(key)
                        if isinstance(n,int): usage_totals[key]+=n
                rec={"scenario":scenario["id"],"turn":turn_index,"question":question,
                    "expected_behavior":item["expected"],
                    "understanding_raw":understanding.structured_response,
                    "understanding_validated":understanding_to_dict(understanding),
                    "coordinator_decision":decision.to_dict(),
                    "progress_ledger_before":_state_ledger(before),
                    "progress_ledger_after":_state_ledger(after),
                    "user_reply":answer.text,"answer_scenario":answer.scenario,
                    "answer_scenario_reason":answer.scenario_reason,
                    "answer_validation_status":answer.validation_status,
                    "answer_validation_reason":answer.validation_reason,
                    "answer_generation_error":answer.generation_error,
                    "b2_selector":{"decision":selector.get("decision"),
                        "selected_ids_verified":selector.get("selected_ids_verified"),
                        "candidate_ids":selector.get("candidate_ids"),
                        "rejection_reason":selector.get("rejection_reason"),
                        "source_sha_verified":selector.get("source_sha_verified"),
                        "coordinator_evidence":diagnostics.get("coordinator_evidence")},
                    "planner_selection":{"mode":(diagnostics.get("planner") or {}).get("mode"),
                        "section_id":(diagnostics.get("planner") or {}).get("section_id"),
                        "reason":(diagnostics.get("planner") or {}).get("reason")},
                    "lexical_source_first_same_retrieval":lexical,
                    "retrieval_diagnostics":diagnostics,
                    "source_integrity":{"approved_ids_verified":selector.get("source_sha_verified"),
                        "source_sha_verified":selector.get("source_sha_verified"),
                        "selected_sources":(diagnostics.get("coordinator_evidence") or {}).get("sources"),
                        "selected_sections":(diagnostics.get("coordinator_evidence") or {}).get("sections")},
                    "latency_ms":{"understanding":understanding.duration_ms,"answer":answer.duration_ms,
                        "http_attempts":[{k:c.get(k) for k in ("number","stage","http_status","latency_ms")} for c in calls]},
                    "usage":{"understanding":understanding.tokens,"provider_attempts":[c.get("usage") for c in calls]},
                    "http_attempts":calls}
                turns.append(rec)
                if any((c.get("http_status") or 0)>=400 or c.get("error_type") for c in calls):
                    return _result("BLOCKED",scenario["id"],turns,usage_totals,preflight)
                if QUOTA_STOP:
                    return _result("BLOCKED",scenario["id"],turns,usage_totals,preflight)
                # If selected source validation failed, stop before expanding further.
                if answer.scenario_reason in {"semantic_selector_validation_rejected","semantic_selector_safety_rejected",
                    "unsafe_operation","unsafe_source_section","source_integrity_mismatch"}:
                    return _result("STOPPED",scenario["id"],turns,usage_totals,preflight)
    return _result("COMPLETED",None,turns,usage_totals,preflight)


def _result(status,active_scenario,turns,usage,preflight):
    return {"status":status,"active_scenario":active_scenario,"gate_result":"PENDING_MANUAL_SCORING",
        "provider":"groq","model":os.getenv("GROQ_MODEL","openai/gpt-oss-20b"),
        "qdrant_collection":STAGE3_COLLECTION,"qdrant_mode":"read-only facade",
        "groq_http_attempts":len(HTTP_ATTEMPTS),"groq_http_attempt_limit":MAX_GROQ_HTTP_ATTEMPTS,
        "automatic_retries":0,"quota_stop_reason":QUOTA_STOP,
        "rate_limit_quota_latest":LATEST_RATE,"usage_totals":usage,"turns":turns,
        "preflight":preflight,"all_http_attempts":HTTP_ATTEMPTS,
        "created_at_utc":datetime.now(timezone.utc).isoformat()}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args()
    settings=get_settings()
    preflight=_preflight(settings)
    holdout=json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
    if not args.execute:
        print(json.dumps({"mode":"preflight_only","will_make_groq_calls":False,
            "configured":preflight.get("configured"),"issues":preflight.get("issues"),
            "provider_configured":settings.llm_provider=="groq" and bool(settings.groq_api_key),
            "model":settings.groq_model,"rag_engine":settings.rag_engine,
            "coordinator":settings.ai_coordinator_enabled,"selector":settings.semantic_evidence_selector_enabled,
            "qdrant":preflight},ensure_ascii=True,indent=2))
        return 0 if preflight.get("configured") else 2
    if not preflight.get("configured"):
        print(json.dumps({"status":"BLOCKED","preflight":preflight},ensure_ascii=True,indent=2)); return 2
    _install_http_accounting()
    try:
        result=asyncio.run(_run(settings,holdout,preflight))
    except Exception as exc:
        result=_result("BLOCKED",None,[],{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0},preflight)
        result["runner_error_type"]=type(exc).__name__
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"turns","all_http_attempts"}},ensure_ascii=True,indent=2))
    print("trace_path",args.output)
    return 0 if result["status"]=="COMPLETED" else 1

if __name__=="__main__":
    raise SystemExit(main())
