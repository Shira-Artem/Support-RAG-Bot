"""Read-only evidence-first vertical prototype, without LLM or production changes.

The planner selects source units, not free-form instructions. Its renderer
copies exact approved text. This is an extractive offline baseline, not proof
that an LLM can make the same selection in an open conversation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.retrieval import lexical_token, tokens  # noqa: E402
from experiments.vnext.stage3_retrieval import ReadOnlyStage3  # noqa: E402

HERE = Path(__file__).resolve().parent
EXCLUDED_SECTIONS = ("вопрос", "симптом", "огранич", "эскалац", "передать", "когда обращаться", "важно")
PROCEDURE_SECTIONS = ("диагност", "провер", "созда", "поиск", "шаг", "действ", "подтвержден", "подтверждён", "первич")
HIGH_RISK = re.compile(r"перерегистр|закры(?:ть|вайте|тие)\s+архив|замен(?:ить|а)\s+фн|сброс\w*\s+настро|запис\w*\s+в\s+фн|пробн\w*\s+расч[её]т|повторн\w*\s+импорт", re.I)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.casefold().replace("ё", "е")).strip()


def index_documents() -> dict[str, tuple[Path, dict, str]]:
    index = {}
    for path in (ROOT / "data/knowledge").rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) != 3:
            continue
        meta = yaml.safe_load(parts[1]) or {}
        doc_id = meta.get("document_id")
        if doc_id:
            if doc_id in index:
                raise ValueError(f"duplicate document ID: {doc_id}")
            index[doc_id] = path, meta, parts[2].strip()
    return index


def sections(body: str) -> list[tuple[str, str]]:
    result = []
    heading = ""
    lines = []
    for line in body.splitlines():
        if line.startswith("## "):
            if heading and "\n".join(lines).strip():
                result.append((heading, "\n".join(lines).strip()))
            heading, lines = line[3:].strip(), []
        elif heading:
            lines.append(line)
    if heading and "\n".join(lines).strip():
        result.append((heading, "\n".join(lines).strip()))
    return result


def source_units(section_text: str) -> list[str]:
    """Keep each numbered step whole, including its conditions and warnings."""
    lines = [line.strip() for line in section_text.splitlines() if line.strip()]
    if any(re.match(r"^\d+[.)]\s+", line) for line in lines):
        return [re.sub(r"^\d+[.)]\s+", "", line) for line in lines
                if re.match(r"^\d+[.)]\s+", line)]
    return [re.sub(r"^[-*]\s+", "", line) for line in lines]


@dataclass(frozen=True)
class Card:
    document_id: str
    section: str
    text: str
    source_sha256: str
    source_path: str
    ordinal: int
    risk_flag: bool


def build_cards(doc_id: str, index: dict) -> list[Card]:
    path, meta, body = index[doc_id]
    if meta.get("status") != "approved" or meta.get("document_id") != doc_id:
        return []
    result = []
    for heading, content in sections(body):
        if any(term in norm(heading) for term in EXCLUDED_SECTIONS):
            continue
        for ordinal, unit in enumerate(source_units(content), 1):
            if unit and unit in body:
                result.append(Card(doc_id, heading, unit, sha256(path.read_bytes()).hexdigest(),
                                   str(path.relative_to(ROOT)).replace("\\", "/"), ordinal,
                                   bool(HIGH_RISK.search(unit) and not re.search(r"\bне\b", norm(unit)))))
    return result


def choose_section(cards: list[Card], question: str) -> list[Card]:
    grouped: dict[str, list[Card]] = {}
    for card in cards:
        grouped.setdefault(card.section, []).append(card)
    query_terms = {lexical_token(x) for x in tokens(question)}

    def rank(row: tuple[str, list[Card]]) -> tuple[int, int]:
        heading, units = row
        heading_norm = norm(heading)
        heading_terms = {lexical_token(x) for x in tokens(heading)}
        body_terms = {lexical_token(x) for x in tokens(" ".join(c.text for c in units))}
        procedure = 2 if any(term in heading_norm for term in PROCEDURE_SECTIONS) else 0
        return (procedure + 2 * len(query_terms & heading_terms) + min(2, len(query_terms & body_terms)),
                -len(units))

    if not grouped:
        return []
    _, selected = max(grouped.items(), key=rank)
    return selected[:4]


def verify_cards(cards: list[Card], index: dict) -> tuple[list[Card], list[dict]]:
    accepted, rejected = [], []
    for card in cards:
        path, meta, body = index[card.document_id]
        if meta.get("status") != "approved":
            rejected.append({"text": card.text, "reason": "source_not_approved"})
        elif card.source_sha256 != sha256(path.read_bytes()).hexdigest() or card.text not in body:
            rejected.append({"text": card.text, "reason": "source_text_changed"})
        elif card.risk_flag:
            rejected.append({"text": card.text, "reason": "high_risk_needs_context_review"})
        else:
            accepted.append(card)
    return accepted, rejected


def run_case(store: ReadOnlyStage3, index: dict, case: dict) -> dict:
    messages = case.get("messages") or [case["question"]]
    question = " ".join(messages)[-500:]
    context, retrieval = store.search_with_trace(question, messages, query_origin="raw_user_question")
    candidate_ids = list(dict.fromkeys(item["document_id"] for item in context))
    considered = []
    selected_doc = None
    selected_cards: list[Card] = []
    rejected_cards = []
    for doc_id in candidate_ids:
        if doc_id not in index:
            considered.append({"document_id": doc_id, "reason": "local_source_missing"})
            continue
        path, meta, body = index[doc_id]
        if meta.get("status") != "approved":
            considered.append({"document_id": doc_id, "reason": "local_source_not_approved"})
            continue
        selected = choose_section(build_cards(doc_id, index), question)
        accepted, rejected = verify_cards(selected, index)
        considered.append({"document_id": doc_id, "section": selected[0].section if selected else None,
                           "accepted": len(accepted), "rejected": len(rejected)})
        if accepted:
            selected_doc, selected_cards, rejected_cards = doc_id, accepted, rejected
            break
    if selected_cards:
        title = index[selected_doc][1].get("title") or selected_doc
        steps = "\n".join(f"{i}. {card.text}" for i, card in enumerate(selected_cards, 1))
        answer = f"По подтверждённому материалу «{title}»:\n{steps}\nЕсли эти проверки не решат вопрос, можно подключить специалиста."
        mode = "partial" if rejected_cards else "answer"
        reason = "source_exact_plan"
    else:
        # This text makes no technical claim and does not pretend to hand off.
        if not candidate_ids:
            mode, reason = "escalate", "no_applicable_approved_evidence"
        else:
            mode, reason = "escalate", "no_verified_source_action"
        answer = "В доступных подтверждённых материалах не нашёл применимого решения. Передам вопрос специалисту; вы также можете вызвать специалиста сами."
    return {"id": case["id"], "question": case["question"], "messages": messages,
            "mode": mode, "reason": reason, "answer": answer,
            "document_id": selected_doc, "cards": [asdict(card) for card in selected_cards],
            "rejected_cards": rejected_cards, "considered": considered,
            "retrieval": {"collection": store.receipt["collection"],
                          "context_document_ids": retrieval["context_document_ids"],
                          "candidate_reasons": [{"document_id": x["document_id"], "reason": x["reason"]}
                                                for x in retrieval["candidates"][:12]],
                          "retrieval_ms": retrieval["retrieval_ms"]}}


def main() -> None:
    here = HERE
    cases = json.loads((here / "new_cases.json").read_text(encoding="utf-8"))
    oracle = json.loads((ROOT / "experiments/oracle_rag/scenarios.json").read_text(encoding="utf-8"))
    for scenario in oracle:
        cases.append({"id": "oracle_" + scenario["id"], "question": scenario["turns"][-1],
                      "messages": scenario["turns"], "family": scenario["id"],
                      "expected_document_id": scenario["evidence_by_turn"][-1][0]
                      if scenario["evidence_by_turn"][-1] else None})
    env = dotenv_values(ROOT / ".env")  # read only; credentials are never emitted
    store = ReadOnlyStage3(os.getenv("QDRANT_URL") or env.get("QDRANT_URL") or "http://127.0.0.1:6333",
                           os.getenv("EMBEDDING_MODEL") or env.get("EMBEDDING_MODEL") or
                           "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    index = index_documents()
    result = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "retrieval_receipt": store.receipt,
              "new_cases_sha256": sha256((here / "new_cases.json").read_bytes()).hexdigest(),
              "groq_calls": 0, "cases": []}
    for case in cases:
        row = run_case(store, index, case)
        result["cases"].append(row)
        print(json.dumps({"id": row["id"], "mode": row["mode"], "document_id": row["document_id"],
                          "cards": len(row["cards"]), "reason": row["reason"]}, ensure_ascii=False), flush=True)
    (here / "trace.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
