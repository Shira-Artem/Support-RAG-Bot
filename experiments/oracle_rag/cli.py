"""Read-only oracle evidence experiment. No production pipeline or database writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from dotenv import dotenv_values
from qdrant_client import QdrantClient, models

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
COLLECTION = "knowledge_stage3_retrieval_20261022"
MODEL = "openai/gpt-oss-20b"
DOCUMENTS = {
    "batch-20261013-bank-directbank-all-accounts": ROOT / "data/knowledge/1c/bank/directbank-all-accounts.md",
    "platformaofd-lkk-receipt-search": ROOT / "data/knowledge/platformaofd/ofd/lkk-receipt-search.md",
    "aqsi-online-account-add-user": ROOT / "data/knowledge/aqsi_online/account/add-user.md",
    "platformaofd-tariff-activation": ROOT / "data/knowledge/platformaofd/ofd/tariff-activation.md",
}
SCOPES = {
    "batch-20261013-bank-directbank-all-accounts": "1С:Бухгалтерия 8",
    "platformaofd-lkk-receipt-search": "Платформа ОФД",
    "aqsi-online-account-add-user": "aQsi Online",
    "platformaofd-tariff-activation": "Платформа ОФД",
}
SYSTEM = ("Вы — русскоязычный специалист технической поддержки. Определите текущую проблему по всему диалогу и ответьте по существу. "
          "Используйте только подтверждённые ниже знания для конкретных процедур и фактов. "
          "Не выдумывайте кнопки, роли, настройки, даты или шаги. Если сведений не хватает, задайте один полезный вопрос; "
          "если безопасный ответ невозможен — объясните ограничение и предложите специалиста. "
          "Не предлагайте опасные изменения ФН, ККТ или учёта без подтверждённой процедуры. "
          "Пишите естественно по-русски, без JSON.")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def redact(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", text)
    text = re.sub(r"(?<!\d)(?:\+7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s()\-]*\d{2}[\s()\-]*\d{2}(?!\d)", "[REDACTED_PHONE]", text)
    return re.sub(r"(?i)(?:gsk_|sk-)[a-z0-9_-]{12,}", "[REDACTED_KEY]", text)


def read_document(doc_id: str) -> dict:
    path = DOCUMENTS[doc_id]
    source = path.read_text(encoding="utf-8")
    parts = source.split("---", 2)
    if len(parts) != 3:
        raise ValueError(f"No front matter: {path}")
    meta = yaml.safe_load(parts[1])
    if meta.get("document_id") != doc_id or meta.get("status") != "approved":
        raise ValueError(f"Unapproved or mismatched source: {doc_id}")
    if meta.get("service") != SCOPES[doc_id]:
        raise ValueError(f"Service mismatch: {doc_id}")
    return {"document_id": doc_id, "title": meta["title"], "service": meta["service"],
            "status": meta["status"], "sha256": sha(path), "path": str(path.relative_to(ROOT)),
            "evidence": parts[2].strip()}


def preflight(require_key: bool = False) -> tuple[dict, dict, str]:
    env = dotenv_values(ROOT / ".env")  # read only, never exported to report
    key = os.getenv("GROQ_API_KEY") or env.get("GROQ_API_KEY") or ""
    effort = os.getenv("GROQ_REASONING_EFFORT") or env.get("GROQ_REASONING_EFFORT") or "medium"
    model = os.getenv("GROQ_MODEL") or env.get("GROQ_MODEL") or MODEL
    if model != MODEL or effort != "medium":
        raise ValueError("Expected existing Groq model openai/gpt-oss-20b / medium")
    if require_key and not key:
        raise ValueError("GROQ_API_KEY missing")
    scenarios = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))
    ids = {doc_id for s in scenarios for row in s["evidence_by_turn"] for doc_id in row}
    if ids != set(DOCUMENTS) or len(scenarios) != 5 or sum(len(s["turns"]) for s in scenarios) != 15:
        raise ValueError("Scenario manifest differs from frozen 5/15 design")
    for s in scenarios:
        if len(s["turns"]) != len(s["evidence_by_turn"]):
            raise ValueError(f"Turn/evidence mismatch: {s['id']}")
    docs = {doc_id: read_document(doc_id) for doc_id in ids}
    url = os.getenv("QDRANT_URL") or env.get("QDRANT_URL") or "http://127.0.0.1:6333"
    client = QdrantClient(url=url, timeout=15)
    info = client.get_collection(COLLECTION)
    if info.points_count != 934:
        raise ValueError(f"Collection inventory changed: {info.points_count}")
    for doc_id in ids:
        points, _ = client.scroll(COLLECTION, scroll_filter=models.Filter(must=[models.FieldCondition(
            key="document_id", match=models.MatchValue(value=doc_id))]), limit=100,
            with_payload=True, with_vectors=False)
        if not points or any((p.payload or {}).get("status") != "approved" for p in points):
            raise ValueError(f"Qdrant document not wholly approved: {doc_id}")
        services = {str((p.payload or {}).get("service") or "") for p in points}
        if services != {SCOPES[doc_id]}:
            raise ValueError(f"Qdrant scope mismatch: {doc_id}: {services}")
        docs[doc_id]["qdrant_chunk_ids"] = [str(p.id) for p in points]
    receipt = {"date_utc": datetime.now(timezone.utc).isoformat(), "head": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "scenario_sha256": sha(HERE / "scenarios.json"), "criteria_sha256": sha(HERE / "criteria.md"),
        "cli_sha256": sha(HERE / "cli.py"), "collection": COLLECTION, "points": info.points_count,
        "model": MODEL, "reasoning_effort": effort, "temperature": 0.2,
        "max_completion_tokens": 3072, "source": "local approved files + read-only Qdrant verification",
        "documents": docs, "groq_key_present": bool(key)}
    return receipt, {"scenarios": scenarios, "documents": docs}, key


def prompt_for(scenario: dict, turn_index: int, docs: dict, history: list[dict]) -> list[dict]:
    evidence = scenario["evidence_by_turn"][turn_index]
    source_text = "\n\n".join(f"[{doc_id}] {docs[doc_id]['title']} | сервис: {docs[doc_id]['service']} | approved\n"
                              f"{docs[doc_id]['evidence']}" for doc_id in evidence)
    if not source_text:
        source_text = "Подтверждённых инструкций для этой задачи сейчас нет."
    return [{"role": "system", "content": SYSTEM + "\n\nПодтверждённые знания на этом ходе:\n" + source_text},
            *history, {"role": "user", "content": scenario["turns"][turn_index]}]


def run(max_calls: int, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite an existing result: {output}")
    receipt, prepared, key = preflight(require_key=True)
    scenarios, docs = prepared["scenarios"], prepared["documents"]
    result = {"receipt": receipt, "max_calls": max_calls, "calls_attempted": 0, "scenarios": []}
    last_call_at = 0.0
    stop = False
    for scenario in scenarios:
        history: list[dict] = []
        scenario_result = {"id": scenario["id"], "name": scenario["name"], "turns": []}
        result["scenarios"].append(scenario_result)
        for index, user in enumerate(scenario["turns"]):
            evidence_ids = scenario["evidence_by_turn"][index]
            prompt = prompt_for(scenario, index, docs, history)
            row = {"turn": index + 1, "user": user, "history": list(history),
                   "evidence_ids": evidence_ids,
                   "evidence": [{"document_id": i, "sha256": docs[i]["sha256"],
                                 "text": docs[i]["evidence"]} for i in evidence_ids],
                   "prompt": prompt, "raw_answer": None, "usage": None,
                   "latency_ms": None, "status": "unexecuted", "error": None,
                   "independent_review": "pending_manual_claim_and_safety_review"}
            scenario_result["turns"].append(row)
            if stop or result["calls_attempted"] >= max_calls:
                row["error"] = "call_cap_or_prior_provider_error"
                continue
            wait = max(0, 18 - (time.monotonic() - last_call_at)) if last_call_at else 0
            if wait:
                time.sleep(wait)
            payload = {"model": MODEL, "messages": prompt, "temperature": 0.2,
                       "reasoning_effort": "medium", "max_completion_tokens": 3072}
            result["calls_attempted"] += 1
            last_call_at = time.monotonic()
            start = time.perf_counter()
            try:
                with httpx.Client(timeout=httpx.Timeout(90, connect=15)) as client:
                    response = client.post("https://api.groq.com/openai/v1/chat/completions",
                                           headers={"Authorization": f"Bearer {key}"}, json=payload)
                row["latency_ms"] = round((time.perf_counter() - start) * 1000)
                if response.status_code != 200:
                    row["status"] = "provider_error"
                    row["error"] = f"Groq HTTP {response.status_code}"
                    stop = True
                else:
                    body = response.json()
                    answer = body["choices"][0]["message"]["content"]
                    if not isinstance(answer, str) or not answer.strip():
                        raise ValueError("Empty model content")
                    row["raw_answer"] = redact(answer.strip())
                    row["usage"] = body.get("usage")
                    row["finish_reason"] = body["choices"][0].get("finish_reason")
                    row["status"] = "generated"
                    history.extend([{"role": "user", "content": user},
                                    {"role": "assistant", "content": row["raw_answer"]}])
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                row["status"] = "provider_error"
                row["error"] = type(exc).__name__  # no response body or credentials
                stop = True
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{scenario['id']} {index+1}: {row['status']} ({row['latency_ms']} ms)", flush=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {output}; Groq attempts: {result['calls_attempted']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "smoke", "run"])
    parser.add_argument("--max-calls", type=int, default=15)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    if not 1 <= args.max_calls <= 15:
        parser.error("--max-calls must be 1..15")
    if args.mode in {"prepare", "smoke"}:
        receipt, prepared, _ = preflight()
        summary = {k: v for k, v in receipt.items() if k != "documents"}
        summary["documents"] = [{k: v for k, v in d.items() if k != "evidence"}
                                for d in prepared["documents"].values()]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        run(args.max_calls, args.output)


if __name__ == "__main__":
    main()
