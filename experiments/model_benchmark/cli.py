"""Paired Groq model benchmark on frozen Oracle scenarios; read-only source access."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from experiments.oracle_rag import cli as oracle  # noqa: E402

MODELS = ("openai/gpt-oss-20b", "openai/gpt-oss-120b")
SETTINGS = {"temperature": 0.2, "reasoning_effort": "medium", "max_completion_tokens": 3072}
API = "https://api.groq.com/openai/v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_access(key: str) -> dict:
    with httpx.Client(timeout=httpx.Timeout(20, connect=10)) as client:
        response = client.get(f"{API}/models", headers={"Authorization": f"Bearer {key}"})
    if response.status_code != 200:
        raise RuntimeError(f"Groq model listing HTTP {response.status_code}; no generation attempted")
    listed = {item.get("id"): item for item in response.json().get("data", [])}
    out = {name: {"listed": name in listed, "active": listed.get(name, {}).get("active")}
           for name in MODELS}
    if any(not x["listed"] or x["active"] is False for x in out.values()):
        raise RuntimeError(f"Requested model unavailable: {out}; no substitute and no generation")
    return out


def preflight() -> tuple[dict, dict, str]:
    oracle_receipt, prepared, key = oracle.preflight(require_key=True)
    original = json.loads((ROOT / "experiments/oracle_rag/results.json").read_text(encoding="utf-8"))
    original_scenarios = original["scenarios"]
    if [s["id"] for s in prepared["scenarios"]] != [s["id"] for s in original_scenarios]:
        raise ValueError("Scenario order differs from Oracle result")
    for scenario, old in zip(prepared["scenarios"], original_scenarios):
        if scenario["turns"] != [t["user"] for t in old["turns"]]:
            raise ValueError(f"Oracle turns changed: {scenario['id']}")
        for index, turn in enumerate(old["turns"]):
            if scenario["evidence_by_turn"][index] != turn["evidence_ids"]:
                raise ValueError(f"Oracle evidence changed: {scenario['id']} {index+1}")
            if oracle.prompt_for(scenario, index, prepared["documents"], turn["history"]) != turn["prompt"]:
                raise ValueError(f"Oracle prompt construction differs: {scenario['id']} {index+1}")
    for name, field in (("scenarios.json", "scenario_sha256"), ("criteria.md", "criteria_sha256"),
                        ("cli.py", "cli_sha256")):
        if sha(ROOT / "experiments/oracle_rag" / name) != original["receipt"][field]:
            raise ValueError(f"Frozen Oracle file changed: {name}")
    for doc_id, doc in prepared["documents"].items():
        if doc["sha256"] != original["receipt"]["documents"][doc_id]["sha256"]:
            raise ValueError(f"Oracle approved document changed: {doc_id}")
    access = model_access(key)
    receipt = {"date_utc": datetime.now(timezone.utc).isoformat(),
               "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "benchmark_cli_sha256": sha(HERE / "cli.py"),
               "benchmark_criteria_sha256": sha(HERE / "criteria.md"),
               "oracle_raw_sha256": sha(ROOT / "experiments/oracle_rag/results.json"),
               "oracle_scenario_sha256": oracle_receipt["scenario_sha256"],
               "oracle_criteria_sha256": oracle_receipt["criteria_sha256"],
               "oracle_cli_sha256": oracle_receipt["cli_sha256"],
               "approved_documents": {i: {"sha256": d["sha256"], "service": d["service"],
                                        "qdrant_chunk_ids": d["qdrant_chunk_ids"]}
                                      for i, d in prepared["documents"].items()},
               "collection": oracle_receipt["collection"], "points": oracle_receipt["points"],
               "models": access, "settings": SETTINGS,
               "model_parameter_reference": "https://console.groq.com/docs/api-reference",
               "generation_limit": 30, "oracle_prompt_replay_verified": True}
    return receipt, prepared, key


def save(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def run(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    receipt, prepared, key = preflight()
    result = {"receipt": receipt, "successful_calls": 0, "attempted_calls": 0,
              "scenarios": [], "completed": False}
    recent: list[tuple[float, int]] = []
    last_call_at = 0.0
    stop_all = False
    for scenario in prepared["scenarios"]:
        item = {"id": scenario["id"], "name": scenario["name"], "models": {}}
        result["scenarios"].append(item)
        for model in MODELS:
            history: list[dict] = []
            turns = []
            item["models"][model] = turns
            stop_history = False
            for index, user in enumerate(scenario["turns"]):
                ids = scenario["evidence_by_turn"][index]
                prompt = oracle.prompt_for(scenario, index, prepared["documents"], history)
                row = {"turn": index + 1, "model_requested": model, "model_returned": None,
                       "user": user, "history": list(history), "evidence_ids": ids,
                       "evidence": [{"document_id": i, "sha256": prepared["documents"][i]["sha256"],
                                     "text": prepared["documents"][i]["evidence"]} for i in ids],
                       "prompt": prompt, "settings": SETTINGS, "raw_answer": None,
                       "redaction_applied": False, "usage": None, "latency_ms": None,
                       "finish_reason": None, "status": "unexecuted", "error": None}
                turns.append(row)
                if stop_all or stop_history:
                    row["error"] = "prior_error_or_cap"
                    continue
                if result["attempted_calls"] >= 30:
                    row["error"] = "attempt_cap_30"
                    stop_all = True
                    continue
                # One attempt per turn. Pacing is preventive, never a retry.
                now = time.monotonic()
                recent = [(t, n) for t, n in recent if now - t < 65]
                wait = max(0.0, 20 - (now - last_call_at)) if last_call_at else 0.0
                estimate = min(5500, sum(len(str(m["content"])) for m in prompt) // 3 + 512)
                if recent and sum(n for _, n in recent) + estimate > 6000:
                    wait = max(wait, 65 - (now - recent[0][0]))
                if wait > 0:
                    time.sleep(wait)
                payload = {"model": model, "messages": prompt, **SETTINGS}
                result["attempted_calls"] += 1
                last_call_at = time.monotonic()
                start = time.perf_counter()
                try:
                    with httpx.Client(timeout=httpx.Timeout(90, connect=15)) as client:
                        response = client.post(f"{API}/chat/completions",
                                               headers={"Authorization": f"Bearer {key}"}, json=payload)
                    row["latency_ms"] = round((time.perf_counter() - start) * 1000)
                    if response.status_code != 200:
                        row["status"] = "provider_error"
                        row["error"] = {"http_status": response.status_code,
                                        "retry_after": response.headers.get("retry-after")}
                        stop_history = True
                    else:
                        body = response.json()
                        answer = body["choices"][0]["message"]["content"]
                        if not isinstance(answer, str) or not answer.strip():
                            raise ValueError("Empty model response")
                        safe = oracle.redact(answer.strip())
                        row.update({"raw_answer": safe, "redaction_applied": safe != answer.strip(),
                                    "model_returned": body.get("model"), "usage": body.get("usage"),
                                    "finish_reason": body["choices"][0].get("finish_reason"),
                                    "status": "generated"})
                        history.extend([{"role": "user", "content": user},
                                        {"role": "assistant", "content": safe}])
                        result["successful_calls"] += 1
                        recent.append((time.monotonic(), int((row["usage"] or {}).get("total_tokens") or estimate)))
                except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                    row["status"] = "provider_error"
                    row["error"] = {"type": type(exc).__name__}  # never persist error body or credentials
                    stop_history = True
                save(path, result)
                print(f"{scenario['id']} {model.rsplit('-',1)[-1]} {index+1}: {row['status']} "
                      f"({row['latency_ms']} ms)", flush=True)
    result["completed"] = True
    save(path, result)
    print(f"Saved {path}; successful={result['successful_calls']}, attempted={result['attempted_calls']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "run"))
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    if args.mode == "smoke":
        receipt, _, _ = preflight()
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        run(args.output)


if __name__ == "__main__":
    main()
