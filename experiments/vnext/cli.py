"""Isolated LangGraph + Groq + read-only Stage3 prototype; no Telegram or production writes.

Run with the project's .venv Python. LangGraph is installed only under .local/vnext-deps.
The graph has three nodes: understand, retrieve, respond. In-memory checkpointing
keeps each scenario's exact user messages and confirmed user quotes independent.
"""
from __future__ import annotations

import argparse
import json
import operator
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Annotated, TypedDict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".local" / "vnext-deps"))

import httpx
from dotenv import dotenv_values
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from qdrant_client import QdrantClient, models

from app.embeddings import SentenceTransformerEmbedding
from app.response_grounding import claim_supported, instruction_issue, unsafe_operation_issue

COLLECTION = "knowledge_stage3_retrieval_20261022"
MODEL = "openai/gpt-oss-20b"
EFFORT = "medium"


class State(TypedDict, total=False):
    messages: Annotated[list[dict], operator.add]
    user_text: str
    task_messages: list[str]
    confirmed_quotes: list[str]
    asked_questions: list[str]
    original_problem: str
    route: str
    search_query: str
    proposed_question: str
    candidates: list[dict]
    applicability: list[dict]
    answer: str
    decision_reason: str
    llm_calls: int
    usage_tokens: int
    retrieval_ms: int
    llm_ms: int
    grounding_rejections: list[str]


class Groq:
    def __init__(self, key: str, max_calls: int):
        if not key:
            raise RuntimeError("GROQ_API_KEY is missing")
        self.key, self.max_calls, self.calls = key, max_calls, 0
        self.last_call_at = 0.0
        self.recent: list[tuple[float, int]] = []

    def json(self, prompt: dict) -> tuple[dict, int, int]:
        if self.calls >= self.max_calls:
            raise RuntimeError(f"Groq call cap reached: {self.max_calls}")
        payload = {"model": MODEL, "reasoning_effort": EFFORT, "temperature": 0,
                   "max_completion_tokens": 3072, "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}]}
        estimate = min(5500, len(payload["messages"][0]["content"]) // 3 + 512)
        while True:
            now = time.monotonic()
            self.recent = [(t, n) for t, n in self.recent if now-t < 66]
            pause = max(0, 18.0 - (now - self.last_call_at))
            if self.recent and sum(n for _, n in self.recent) + estimate > 6000:
                pause = max(pause, 66 - (now - self.recent[0][0]))
            if pause <= 0:
                break
            time.sleep(min(pause, 20))
        self.calls += 1
        self.last_call_at = time.monotonic()
        start = time.perf_counter()
        with httpx.Client(timeout=httpx.Timeout(90, connect=15)) as client:
            response = client.post("https://api.groq.com/openai/v1/chat/completions",
                                   headers={"Authorization": f"Bearer {self.key}"}, json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"Groq HTTP {response.status_code}; call {self.calls}")
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Groq returned a non-object")
        tokens = int((body.get("usage") or {}).get("total_tokens") or estimate)
        self.recent.append((time.monotonic(), tokens))
        return parsed, tokens, round((time.perf_counter()-start)*1000)


class ReadOnlyStage3:
    def __init__(self, url: str, embedding_name: str):
        self.client = QdrantClient(url=url, timeout=15)
        info = self.client.get_collection(COLLECTION)  # never create a collection
        if info.points_count != 934 or info.config.params.vectors.size != 384:
            raise RuntimeError("Stage3 inventory differs from verified receipt")
        self.embedding = SentenceTransformerEmbedding(embedding_name)
        if self.embedding.dimension != 384:
            raise RuntimeError("Embedding dimension mismatch")
        approved_filter = models.Filter(must=[models.FieldCondition(
            key="status", match=models.MatchValue(value="approved"))])
        approved = self.client.count(COLLECTION, count_filter=approved_filter, exact=True).count
        if approved != 672:
            raise RuntimeError("Approved inventory differs from verified receipt")
        self.approved_filter = approved_filter
        self.receipt = {"collection": COLLECTION, "points": info.points_count,
                        "approved_points": approved, "embedding": embedding_name,
                        "model": MODEL, "reasoning_effort": EFFORT}

    def search(self, query: str) -> list[dict]:
        vector = self.embedding.embed([query[:500]])[0]
        points = self.client.query_points(COLLECTION, query=vector, limit=40,
                                          query_filter=self.approved_filter,
                                          with_payload=True).points
        # Dense search identifies documents; read their sibling chunks so a
        # highly similar "Question" heading cannot hide the actual procedure.
        top_docs: dict[str, float] = {}
        for point in points:
            x = point.payload or {}
            doc_id = str(x.get("document_id") or "")
            if x.get("status") == "approved" and doc_id and doc_id not in top_docs:
                top_docs[doc_id] = float(point.score)
            if len(top_docs) == 6:
                break
        result = []
        for doc_id, score in top_docs.items():
            doc_filter = models.Filter(must=[
                models.FieldCondition(key="status", match=models.MatchValue(value="approved")),
                models.FieldCondition(key="document_id", match=models.MatchValue(value=doc_id))])
            chunks, _ = self.client.scroll(COLLECTION, limit=64, scroll_filter=doc_filter,
                                           with_payload=True, with_vectors=False)
            chunks.sort(key=lambda p: (p.payload.get("chunk_index")
                                      if isinstance(p.payload.get("chunk_index"), int) else 999,
                                      str(p.id)))
            useful = [p for p in chunks if _norm(str(p.payload.get("section") or ""))
                      not in {"вопрос", "вопрос клиента", "вопрос пользователя", "симптомы"}]
            for point in useful[:3]:
                x = point.payload or {}
                result.append({"id": str(point.id), "document_id": doc_id,
                               "title": x.get("title"), "section": x.get("section"),
                               "service": x.get("service"), "model": x.get("model"),
                               "operations": x.get("operations"), "status": x.get("status"),
                               "text": str(x.get("text") or "")[:1400],
                               "score": round(score, 4)})
        return result


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("ё", "е")).strip()


def _question_repeated(question: str, asked: list[str]) -> bool:
    a = set(re.findall(r"[a-zа-яё]{4,}", _norm(question)))
    for old in asked:
        b = set(re.findall(r"[a-zа-яё]{4,}", _norm(old)))
        if _norm(question) == _norm(old) or (a and b and len(a & b) / min(len(a), len(b)) >= .7):
            return True
        if SequenceMatcher(None, _norm(question), _norm(old)).ratio() >= .8:
            return True
    return False


def _scope_compatible(candidate: dict, task: list[str]) -> tuple[bool, str]:
    """Conservative service/model incompatibility guard after broad retrieval."""
    context = _norm(" ".join(task))
    service = _norm(str(candidate.get("service") or ""))
    model = _norm(str(candidate.get("model") or ""))
    # This is an after-retrieval incompatibility check, not an intent router.
    named_services = (
        ("платформа офд", ("платформа офд",)),
        ("aqsi online", ("aqsi online", "акси онлайн")),
        ("aqsi", ("aqsi", "акси")),
        ("атол онлайн", ("атол онлайн",)),
        ("атол", ("атол",)),
        ("эвотор", ("эвотор",)),
        ("первый офд", ("первый офд",)),
        ("штрих", ("штрих",)),
        ("1с", ("1с",)),
    )
    for name, aliases in named_services:
        if name in service and not any(alias in context for alias in aliases):
            return False, "service_unconfirmed_or_other"
        if name in service:
            break
    if model and any(ch.isdigit() for ch in model) and not ("1с" in model and "1с" in context):
        digits = re.findall(r"\b\d+(?:\.\d+)?\b", model)
        if digits and not any(d in context for d in digits):
            return False, "equipment_model_unconfirmed"
    return True, "scope_compatible"


def build_graph(store: ReadOnlyStage3, groq: Groq):
    def understand(state: State) -> dict:
        current = state["user_text"]
        transcript = state.get("messages", [])
        prior_task = state.get("task_messages", [])
        prompt = {"role": "Russian support dialogue understanding; return JSON only",
                  "current_user_message": current,
                  "conversation_messages": transcript[-10:],
                  "current_task_user_messages": prior_task,
                  "previous_confirmed_user_quotes": state.get("confirmed_quotes", []),
                  "questions_already_asked": state.get("asked_questions", []),
                  "rules": [
                      "Decide whether this is a new topic or continuation. A new explicit topic resets active task, not transcript.",
                      "Preserve the original problem, subsequent user clarifications and constraints. Never treat an assistant guess as a confirmed fact.",
                      "For a comprehensible issue choose search even when some parameters are unknown. Do not ask for service before searching.",
                      "Choose clarify only when the requested operation itself is unsafe/ambiguous (for example unspecified FN change) or impossible to identify.",
                      "Ask exactly one specific question when clarifying. Do not repeat a previous question unless new information makes it necessary.",
                      "Return search_query with original problem plus relevant user clarifications. No operation enum or evidence spans.",
                      "fact_quotes must be exact substrings of CURRENT user message, only facts/constraints explicitly confirmed by the user."],
                  "output_keys": {"new_topic": "boolean", "route": "search or clarify",
                                  "search_query": "string", "question": "string if clarify",
                                  "fact_quotes": ["exact current-message substring"], "reason": "short string"}}
        result, tokens, ms = groq.json(prompt)
        new_topic = result.get("new_topic") is True or not prior_task
        task = [current] if new_topic else prior_task + [current]
        raw_quotes = result.get("fact_quotes") or []
        quotes = [] if new_topic else list(state.get("confirmed_quotes", []))
        if isinstance(raw_quotes, list):
            quotes.extend(q for q in raw_quotes if isinstance(q, str) and q and q in current)
        route = result.get("route") if result.get("route") in {"search", "clarify"} else "search"
        query = str(result.get("search_query") or " ".join(task))[:500]
        if new_topic and current not in query:
            query = current[:500]
        question = str(result.get("question") or "").strip()
        asked = [] if new_topic else list(state.get("asked_questions", []))
        if route == "clarify" and _question_repeated(question, asked):
            route = "search"  # never loop on the same clarification
        updates: dict = {"task_messages": task, "original_problem": task[0],
                         "confirmed_quotes": list(dict.fromkeys(quotes)),
                         "route": route, "search_query": query,
                         "proposed_question": question, "asked_questions": asked,
                         "decision_reason": str(result.get("reason") or "semantic_decision"),
                         "llm_calls": 1, "usage_tokens": tokens, "llm_ms": ms,
                         "retrieval_ms": 0, "candidates": [], "applicability": [],
                         "grounding_rejections": []}
        if route == "clarify":
            if not question.endswith("?"):
                question = "Какое именно действие с ФН вы хотите выполнить и какая модель кассы?" if "фн" in _norm(current) else "Что именно требуется уточнить?"
            updates["answer"] = question
            updates["asked_questions"] = asked + [question]
        return updates

    def retrieve(state: State) -> dict:
        start = time.perf_counter()
        candidates = store.search(state["search_query"])
        return {"candidates": candidates, "retrieval_ms": round((time.perf_counter()-start)*1000)}

    def respond(state: State) -> dict:
        candidates = state.get("candidates", [])
        scoped = []
        scope_notes = []
        for c in candidates:
            okay, reason = _scope_compatible(c, state["task_messages"])
            scope_notes.append({"document_id": c["document_id"], "scope": reason})
            if okay:
                scoped.append(c)
        if not scoped:
            question = "Какой ОФД или кассовый сервис вы используете?"
            if _question_repeated(question, state.get("asked_questions", [])):
                question = ""
            suffix = (" " + question) if question else ""
            return {"answer": "В найденных approved-материалах нет применимой инструкции для этой задачи." + suffix,
                    "asked_questions": state.get("asked_questions", []) + ([question] if question else []),
                    "applicability": [{**x, "status": "incompatible"} for x in scope_notes],
                    "decision_reason": "no_scope_compatible_approved_source"}
        prompt = {"role": "Russian support RAG answer with applicability assessment; return JSON only",
                  "original_problem": state["original_problem"],
                  "all_current_task_user_messages": state["task_messages"],
                  "confirmed_user_quotes": state["confirmed_quotes"],
                  "previous_questions": state.get("asked_questions", []),
                  "candidate_approved_fragments": scoped,
                  "rules": [
                      "Assess actual applicability of EACH candidate to the user's service, equipment, goal and procedure. Topic similarity is insufficient.",
                      "A tariff activation article does not prove how to check the legal contract expiration date. A registration article does not prove FN settings change.",
                      "Mark fragments usable, partial or incompatible and explain briefly. Use only usable evidence for client instructions.",
                      "Give useful safe diagnostic checks if grounded. For missing knowledge state the precise gap and ask one meaningful next question.",
                      "Do not invent menu labels, dates, service capabilities, fiscal steps or document content.",
                      "Never advise FN replacement/closure, KKT re-registration, closing shift or any other risky fiscal operation.",
                      "Every client-facing positive fact/action goes in claims with an exact quote from ONE candidate and its id. No claim may combine fragments.",
                      "One or two short claims are enough. Limitation and question can be plain text, but cannot contain new technical claims."],
                  "output_keys": {"applicability": [{"id": "candidate id", "status": "usable|partial|incompatible", "reason": "short"}],
                                  "claims": [{"text": "one client-facing sentence", "id": "candidate id", "quote": "exact supporting substring"}],
                                  "limitation": "precise missing evidence, if any", "question": "one next question, if needed",
                                  "reason": "why answer or limit"}}
        result, tokens, ms = groq.json(prompt)
        by_id = {c["id"]: c for c in scoped}
        decisions = {str(a.get("id")): a for a in result.get("applicability", []) if isinstance(a, dict)}
        applicability = []
        for c in candidates:
            local_scope = next((x["scope"] for x in scope_notes if x["document_id"] == c["document_id"]), "unknown")
            a = decisions.get(c["id"], {})
            status = a.get("status") if local_scope == "scope_compatible" else "incompatible"
            if status not in {"usable", "partial", "incompatible"}:
                status = "unassessed"
            applicability.append({"id": c["id"], "document_id": c["document_id"],
                                  "status": status, "reason": a.get("reason") or local_scope})
        valid, rejected = [], []
        for claim in result.get("claims", []):
            if not isinstance(claim, dict):
                continue
            c = by_id.get(str(claim.get("id")))
            a = decisions.get(str(claim.get("id")), {})
            sentence = str(claim.get("text") or "").strip()
            quote = str(claim.get("quote") or "").strip()
            if not c or a.get("status") != "usable" or not sentence or not quote or quote not in c["text"]:
                rejected.append("missing_usable_exact_evidence")
                continue
            if unsafe_operation_issue(sentence) or instruction_issue(sentence, quote):
                rejected.append("unsafe_or_unsupported_action")
                continue
            if not claim_supported(sentence, quote):
                rejected.append("claim_not_grounded")
                continue
            valid.append(sentence)
        limitation = str(result.get("limitation") or "").strip()
        question = str(result.get("question") or "").strip()
        if valid:
            answer = " ".join(valid[:2])
            if limitation and not unsafe_operation_issue(limitation):
                answer += " " + limitation
            mode = "answer" if not limitation else "partial_answer"
        else:
            answer = limitation or "По найденным approved-фрагментам не подтверждается инструкция именно для вашей задачи."
            mode = "limitation"
        if question and question.endswith("?") and not _question_repeated(question, state.get("asked_questions", [])):
            answer += " " + question
            asked = state.get("asked_questions", []) + [question]
        else:
            asked = state.get("asked_questions", [])
        if unsafe_operation_issue(answer):
            rejected.append("unsafe_final_response")
            answer = "Не могу безопасно предложить фискальные действия без уточнения операции и оборудования. Какое именно действие требуется?"
            mode = "safety_limitation"
        return {"answer": answer, "asked_questions": asked,
                "applicability": applicability, "grounding_rejections": rejected,
                "decision_reason": mode + ": " + str(result.get("reason") or "model_assessment"),
                "llm_calls": state.get("llm_calls", 0) + 1,
                "usage_tokens": state.get("usage_tokens", 0) + tokens,
                "llm_ms": state.get("llm_ms", 0) + ms}

    graph = StateGraph(State)
    graph.add_node("understand", understand)
    graph.add_node("retrieve", retrieve)
    graph.add_node("respond", respond)
    graph.add_edge(START, "understand")
    graph.add_conditional_edges("understand", lambda state: END if state["route"] == "clarify" else "retrieve")
    graph.add_edge("retrieve", "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=MemorySaver())


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--scenarios", type=Path, default=Path(__file__).with_name("scenarios.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("results.json"))
    parser.add_argument("--max-groq-calls", type=int, default=30)
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    env = dotenv_values(ROOT / ".env")  # read only; never changes the worker environment
    url = os.getenv("QDRANT_URL") or env.get("QDRANT_URL") or "http://127.0.0.1:6333"
    embedding = os.getenv("EMBEDDING_MODEL") or env.get("EMBEDDING_MODEL") or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    store = ReadOnlyStage3(url, embedding)
    print(json.dumps(store.receipt, ensure_ascii=False), flush=True)
    if args.preflight:
        return
    assert (os.getenv("GROQ_MODEL") or env.get("GROQ_MODEL")) == MODEL
    assert (os.getenv("GROQ_REASONING_EFFORT") or env.get("GROQ_REASONING_EFFORT")) == EFFORT
    groq = Groq(os.getenv("GROQ_API_KEY") or env.get("GROQ_API_KEY") or "", args.max_groq_calls)
    graph = build_graph(store, groq)
    results = {"config": store.receipt, "scenarios": []}
    scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))
    if args.interactive:
        scenarios = [{"id": "cli", "name": "CLI", "turns": []}]
    try:
        for scenario in scenarios:
            record = {"id": scenario["id"], "name": scenario["name"], "turns": []}
            results["scenarios"].append(record)
            config = {"configurable": {"thread_id": scenario["id"]}}
            inputs = scenario["turns"] if not args.interactive else iter(lambda: input("Вы> "), "/quit")
            for message in inputs:
                start = time.perf_counter()
                state = graph.invoke({"user_text": message,
                                      "messages": [{"role": "user", "content": message}]}, config)
                # Add assistant message to the same checkpoint without re-running nodes.
                graph.update_state(config, {"messages": [{"role": "assistant", "content": state["answer"]}]})
                selected = [{"document_id": c["document_id"], "section": c["section"],
                             "status": c["status"], "score": c["score"]} for c in state.get("candidates", [])]
                turn = {"user": message, "answer": state["answer"], "documents": selected,
                        "applicability": state.get("applicability", []),
                        "llm_calls": state.get("llm_calls", 0), "tokens": state.get("usage_tokens", 0),
                        "llm_used": state.get("llm_calls", 0) > 0,
                        "decision": state.get("decision_reason"),
                        "context": {"original_problem": state.get("original_problem"),
                                    "task_messages": state.get("task_messages", []),
                                    "confirmed_quotes": state.get("confirmed_quotes", []),
                                    "questions_asked": state.get("asked_questions", [])},
                        "grounding_rejections": state.get("grounding_rejections", []),
                        "elapsed_ms": round((time.perf_counter()-start)*1000),
                        "retrieval_ms": state.get("retrieval_ms", 0),
                        "llm_ms": state.get("llm_ms", 0)}
                record["turns"].append(turn)
                print(json.dumps({"scenario": scenario["id"], "turn": len(record["turns"]), **turn}, ensure_ascii=False), flush=True)
                if not args.interactive:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        print(f"Groq calls attempted: {groq.calls}/{groq.max_calls}", flush=True)


if __name__ == "__main__":
    run()
