"""Isolated source-section planner. Read-only Qdrant; bounded Groq experiment.

The model chooses an approved source section or abstains. Technical steps in the
answer are copied from verified source text, never composed by the model.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import time

import httpx
from dotenv import dotenv_values

from experiments.evidence_first_vertical.prototype import (
    HERE, ROOT, ReadOnlyStage3, build_cards, index_documents, norm, verify_cards,
)
from experiments.vnext.stage3_retrieval import scope_compatible

MODEL = "openai/gpt-oss-20b"
MAX_CALLS = 13
MAX_DOCUMENTS = 14
MAX_GROUPS = 28
TRACE = HERE / "llm_trace.jsonl"


def load_cases() -> list[dict]:
    cases = json.loads((HERE / "new_cases.json").read_text(encoding="utf-8"))
    oracle = json.loads((ROOT / "experiments/oracle_rag/scenarios.json").read_text(encoding="utf-8"))
    cases += [{"id": "oracle_" + row["id"], "question": row["turns"][-1],
               "messages": row["turns"], "family": row["id"]} for row in oracle]
    return cases


def evidence_groups(retrieval: dict, messages: list[str], index: dict) -> tuple[list[dict], list[dict]]:
    """Offer diverse raw hybrid hits; leave semantic choice to the planner."""
    seen, groups, rejected = set(), [], []
    for hit in retrieval["hybrid_raw_candidates"]:
        doc_id = hit["document_id"]
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        if len(seen) > MAX_DOCUMENTS:
            break
        if doc_id not in index:
            rejected.append({"document_id": doc_id, "reason": "local_source_missing"})
            continue
        path, meta, body = index[doc_id]
        if meta.get("status") != "approved" or hit.get("status") != "approved":
            rejected.append({"document_id": doc_id, "reason": "not_approved"})
            continue
        compatible, reason = scope_compatible(hit, messages)
        if not compatible:
            rejected.append({"document_id": doc_id, "reason": reason})
            continue
        by_section: dict[str, list] = {}
        for card in build_cards(doc_id, index):
            by_section.setdefault(card.section, []).append(card)
        # Whole sections preserve conditions and order. Limit is generic and
        # independent of case labels; no expected document ID enters the prompt.
        for section, cards in list(by_section.items())[:3]:
            cards = cards[:5]
            if not cards or sum(len(c.text) for c in cards) > 1600:
                continue
            group = {"id": f"G{len(groups)+1}", "document_id": doc_id,
                     "title": meta.get("title") or doc_id, "section": section,
                     "service": meta.get("service"), "model": meta.get("model"),
                     "rank": hit["rank"], "cards": [asdict(c) for c in cards]}
            groups.append(group)
            if len(groups) >= MAX_GROUPS:
                break
        if len(groups) >= MAX_GROUPS:
            break
    return groups, rejected


def make_prompt(case: dict, groups: list[dict]) -> dict:
    return {
        "task": "Choose evidence for this customer's exact request. Return JSON only.",
        "conversation": case.get("messages") or [case["question"]],
        "rules": [
            "Choose one group only when its source actually answers the requested operation/object. A related product, tariff, or article is insufficient.",
            "All technical steps will be copied exactly from the chosen group. You cannot add or rewrite instructions.",
            "If evidence covers only a safe partial diagnosis, choose partial. If a necessary fact is missing, choose clarify. If no directly applicable approved section exists, choose escalate.",
            "Do not repeat a clarification already answered as unknown. Do not infer one status, date, or entitlement from another unless the source explicitly establishes that relationship.",
            "Never choose a section to perform fiscal registration, FN writes, resets, duplicate sales, or other irreversible action without case-specific evidence.",
            "The customer can always ask for a specialist.",
        ],
        "groups": [{"id": g["id"], "document_id": g["document_id"],
                    "title": g["title"], "section": g["section"],
                    "service": g["service"], "model": g["model"],
                    "rank": g["rank"], "steps": [c["text"] for c in g["cards"]]}
                   for g in groups],
        "response_schema": {"mode": "answer|partial|clarify|escalate",
                            "group_id": "G-number or null",
                            "missing_slot": "service|model|operation|symptom|null",
                            "reason": "short explanation of applicability or gap"},
    }


def render(case: dict, proposal: dict, groups: list[dict], index: dict) -> dict:
    mode = proposal.get("mode")
    group = next((g for g in groups if g["id"] == proposal.get("group_id")), None)
    result = {"proposed_mode": mode, "proposed_group_id": proposal.get("group_id"),
              "proposed_reason": proposal.get("reason"), "mode": None,
              "document_id": None, "source_units": [], "rejected": []}
    if mode in ("answer", "partial"):
        if group is None:
            result["rejected"].append({"reason": "invalid_or_missing_group_id"})
        else:
            # Rebuild from disk, then compare every selected card and SHA.
            current = build_cards(group["document_id"], index)
            current_set = {(c.section, c.ordinal, c.text, c.source_sha256) for c in current}
            cards = [c for c in current if (c.section, c.ordinal, c.text, c.source_sha256)
                     in {(x["section"], x["ordinal"], x["text"], x["source_sha256"])
                         for x in group["cards"]}]
            if len(cards) != len(group["cards"]) or any(
                (x["section"], x["ordinal"], x["text"], x["source_sha256"]) not in current_set
                for x in group["cards"]
            ):
                result["rejected"].append({"reason": "source_group_changed"})
            else:
                accepted, rejected = verify_cards(cards, index)
                result["rejected"].extend(rejected)
                if accepted:
                    result["mode"] = "partial" if rejected else mode
                    result["document_id"] = group["document_id"]
                    result["source_units"] = [asdict(c) for c in accepted]
                    title = index[group["document_id"]][1].get("title") or group["document_id"]
                    steps = "\n".join(f"{i}. {c.text}" for i, c in enumerate(accepted, 1))
                    result["answer"] = (f"По подтверждённому материалу «{title}»:\n{steps}\n"
                                        "Если этого недостаточно, можно подключить специалиста.")
    if result["mode"] is None:
        slot = proposal.get("missing_slot")
        questions = {"service": "Какой сервис или оператор у вас используется?",
                     "model": "Уточните модель кассы и версию ПО.",
                     "operation": "Какое именно действие вы хотите выполнить?",
                     "symptom": "Какое точное сообщение об ошибке вы видите?"}
        asked = " ".join(case.get("messages") or [case["question"]])
        if mode == "clarify" and slot in questions and norm(questions[slot]) not in norm(asked):
            result["mode"] = "clarify"
            result["answer"] = questions[slot] + " Вы также можете сразу вызвать специалиста."
        else:
            result["mode"] = "escalate"
            result["answer"] = ("В доступных подтверждённых материалах не нашёл применимого решения. "
                                "По этому вопросу нужен специалист; вы можете вызвать его сами.")
    return result


def write_row(row: dict) -> None:
    with TRACE.open("a", encoding="utf-8") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
        out.flush()


def main() -> None:
    env = dotenv_values(ROOT / ".env")
    key = os.getenv("GROQ_API_KEY") or env.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY missing; no calls attempted")
    existing = [json.loads(line) for line in TRACE.read_text(encoding="utf-8").splitlines()] if TRACE.exists() else []
    attempts = sum(bool(row.get("api_attempt")) for row in existing)
    completed = {row["id"] for row in existing if row.get("result")}
    if attempts > MAX_CALLS:
        raise RuntimeError("call cap already exceeded in trace")
    store = ReadOnlyStage3(os.getenv("QDRANT_URL") or env.get("QDRANT_URL") or "http://127.0.0.1:6333",
                           os.getenv("EMBEDDING_MODEL") or env.get("EMBEDDING_MODEL") or
                           "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    index = index_documents()
    last_call = 0.0
    for case in load_cases():
        if case["id"] in completed:
            continue
        if attempts >= MAX_CALLS:
            break
        messages = case.get("messages") or [case["question"]]
        query = " ".join(messages)[-500:]
        _, retrieval = store.search_with_trace(query, messages, query_origin="raw_user_question")
        groups, rejected_candidates = evidence_groups(retrieval, messages, index)
        prompt = make_prompt(case, groups)
        if attempts and not last_call:
            # Resume after a provider TPM rejection without repeating other cases.
            time.sleep(45)
        pause = max(0.0, 18.0 - (time.monotonic() - last_call))
        if pause:
            time.sleep(pause)
        payload = {"model": MODEL, "reasoning_effort": "medium", "temperature": 0,
                   "max_completion_tokens": 1600, "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}]}
        row = {"id": case["id"], "question": case["question"], "messages": messages,
               "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "new_cases_sha256": sha256((HERE / "new_cases.json").read_bytes()).hexdigest(),
               "retrieval_receipt": store.receipt, "retrieval": retrieval,
               "rejected_candidates": rejected_candidates, "groups": groups, "prompt": prompt,
               "request": payload, "api_attempt": True}
        attempts += 1
        last_call = time.monotonic()
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=httpx.Timeout(90, connect=15)) as client:
                response = client.post("https://api.groq.com/openai/v1/chat/completions",
                                       headers={"Authorization": f"Bearer {key}"}, json=payload)
            row["llm_ms"] = round((time.perf_counter() - start) * 1000)
            row["http_status"] = response.status_code
            if response.status_code != 200:
                row["error"] = response.text[:300]
            else:
                body = response.json()
                row["usage"] = body.get("usage")
                row["raw_content"] = body["choices"][0]["message"].get("content")
                proposal = json.loads(row["raw_content"])
                row["proposal"] = proposal
                row["result"] = render(case, proposal, groups, index)
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        write_row(row)
        print(json.dumps({"id": case["id"], "attempts": attempts,
                          "mode": (row.get("result") or {}).get("mode"),
                          "document_id": (row.get("result") or {}).get("document_id"),
                          "error": row.get("error")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
