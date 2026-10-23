"""Compare retrieval collections on the checked-in expert question set.

This script is read-only: it does not index documents, call the LLM, Telegram,
or SQLite.  A separate indexing command creates STAGING before comparison.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict
import json
import os
from pathlib import Path

from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueManager, DialogueState
from app.knowledge import Chunker, DocumentLoader
from app.rag_query import QueryNeedsClarification, build_rag_query
from app.retrieval import Retriever
from app.retrieval_pipeline import _state_task_category
from app.runtime import build_store


def _questions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _source(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("\\", "/").removeprefix("data/knowledge/")


def _unique_documents(hits) -> list[dict]:
    rows, seen = [], set()
    for hit in hits:
        metadata = hit.metadata or {}
        key = metadata.get("document_id") or hit.source
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "document_id": metadata.get("document_id"),
            "source": hit.source,
            "service": metadata.get("service"),
            "task_category": metadata.get("task_category"),
            "operations": metadata.get("operations") or [],
            "score": hit.score,
        })
    return rows


def _evaluated_item(result, document_id: str | None):
    if not document_id:
        return None, None
    accepted = next((item for item in result.candidates
                     if item.document_id == document_id), None)
    rejected = next((item for item in result.rejected
                     if item.document_id == document_id), None)
    return accepted, rejected


def _context_documents(result) -> list[dict]:
    rows, seen = [], set()
    for hit in result.documents:
        metadata = hit.metadata or {}
        document_id = metadata.get("document_id")
        source = metadata.get("source") or hit.source
        key = document_id or source
        if key in seen:
            continue
        seen.add(key)
        rows.append({"document_id": document_id, "source": source})
    return rows


def _loss_category(*, raw_rank, accepted, rejected, candidate_position,
                   in_pipeline_selected, in_context):
    """Assign one first-loss category using the actual per-question state."""
    if raw_rank is None:
        return "document_absent_in_candidates"
    reasons = set(rejected.reasons if rejected else [])
    if rejected and not accepted:
        if any(reason.startswith(("service_", "procedure_service_", "ofd_", "manufacturer_", "equipment_"))
               or reason == "service_mismatch_or_unlabeled" for reason in reasons):
            return "erroneous_service_rejection"
        if any(reason.startswith("operation_") for reason in reasons):
            return "erroneous_operation_or_category_rejection"
        if any(reason.startswith(("task_",)) for reason in reasons):
            return "wrong_routing"
        return "erroneous_operation_or_category_rejection"
    if accepted and not in_pipeline_selected:
        if candidate_position is not None and candidate_position > 4:
            return "loss_at_rerank_or_deduplication"
        return "loss_at_context_assembly"
    if in_pipeline_selected and not in_context:
        return "loss_at_context_assembly"
    return None


def _chunk_order(adapter: RetrieverRAGAdapter, documents) -> dict:
    checked = mismatched = missing_index = missing_links = 0
    examples = []
    for document in documents:
        expected = Chunker().split(document)
        if document.status != "approved" or len(expected) < 2:
            continue
        checked += 1
        actual = adapter.article(document.document_id)
        actual_ids = [(item.metadata or {}).get("chunk_id") for item in actual]
        expected_ids = [item.id for item in expected]
        if actual_ids != expected_ids:
            mismatched += 1
            if len(examples) < 10:
                examples.append(document.source)
        for position, item in enumerate(actual):
            metadata = item.metadata or {}
            if not isinstance(metadata.get("chunk_index"), int):
                missing_index += 1
            if position and not metadata.get("previous_chunk_id"):
                missing_links += 1
            if position + 1 < len(actual) and not metadata.get("next_chunk_id"):
                missing_links += 1
    return {
        "documents_checked": checked,
        "documents_out_of_order": mismatched,
        "chunks_missing_index": missing_index,
        "links_missing": missing_links,
        "examples": examples,
    }


def evaluate(collection: str, questions: list[dict], documents) -> dict:
    store = build_store(collection=collection)
    adapter = RetrieverRAGAdapter(Retriever(store))
    original_search = adapter.search
    cache = {}

    def cached(query, top_k=5):
        key = (query, top_k)
        if key not in cache:
            cache[key] = original_search(query, top_k)
        return cache[key]

    adapter.search = cached
    by_source = {document.source: document for document in documents}
    rows = []
    for question in questions:
        expected_source = _source(question.get("expected_document"))
        expected = by_source.get(expected_source)
        state = DialogueManager().advance(DialogueState(), question["query"], question["id"])
        try:
            query = build_rag_query(state)
        except QueryNeedsClarification as exc:
            rows.append({"id": question["id"], "query_error": str(exc),
                         "expected_source": expected_source})
            continue
        raw = _unique_documents(adapter.search(query, top_k=100))
        result = adapter.search_for_state(state, query)
        selected = _unique_documents(result.documents)
        selected_ids = [item["document_id"] for item in selected]
        context_documents = _context_documents(result)
        context_ids = [item["document_id"] for item in context_documents]
        expected_id = expected.document_id if expected and expected.status == "approved" else None
        expected_rank = next((index + 1 for index, item in enumerate(raw)
                              if item["document_id"] == expected_id), None)
        accepted, rejected = _evaluated_item(result, expected_id)
        candidate_order = sorted(result.candidates,
                                 key=lambda item: (item.relevance.score,
                                                   item.retrieval.get("rrf", 0.0)),
                                 reverse=True)
        candidate_position = next((index + 1 for index, item in enumerate(candidate_order)
                                   if item.document_id == expected_id), None)
        pipeline_selected = bool(accepted and accepted.selected)
        in_context = expected_id in context_ids
        routing_service = state.routing_service
        declared_service = state.task_entity("service") or state.task_entity("ofd")
        selected_service_errors = [item["document_id"] for item in selected
                                   if declared_service and item["service"]
                                   and item["service"].casefold() != declared_service.casefold()]
        rows.append({
            "id": question["id"],
            "query": query,
            "expected_document_id": expected_id,
            "expected_source": expected_source,
            "expected_rank": expected_rank,
            "raw_top5": bool(expected_rank and expected_rank <= 5),
            "raw_top10": bool(expected_rank and expected_rank <= 10),
            "raw_top30": bool(expected_rank and expected_rank <= 30),
            "top_documents": raw[:5],
            "selected_documents": selected_ids,
            "context_documents": context_documents,
            "context_document_ids": context_ids,
            "pipeline_candidate": bool(accepted),
            "pipeline_selected": pipeline_selected,
            "expected_in_llm_context": in_context,
            "candidate_rank_after_gates": candidate_position,
            "extra_documents": [item for item in selected_ids if item != expected_id],
            "expected_rejected_reasons": rejected.reasons if rejected else [],
            "expected_filter_passed": bool(accepted),
            "expected_filter_relevance": (asdict(accepted.relevance) if accepted else
                                           asdict(rejected.relevance) if rejected else None),
            "routing_service": routing_service,
            "declared_service": declared_service,
            "expected_service": expected.service if expected else None,
            "selected_service_errors": selected_service_errors,
            "determined": {
                "intent": state.intent,
                "operation": state.operation,
                "task_category": _state_task_category(state, query),
                "routing_slot": state.routing_slot,
                "routing_service": routing_service,
                "task_entities": {slot: state.task_entity(slot)
                                   for slot in ("service", "ofd", "software", "manufacturer", "equipment")
                                   if state.task_entity(slot)},
            },
            "expected_metadata": ({
                "service": expected.service,
                "task_category": expected.task_category,
                "operation": (expected.operations[0] if expected.operations else None),
                "operations": expected.operations or [],
            } if expected else None),
            "evidence_status": result.evidence_status,
            "insufficiency_reason": result.insufficiency_reason,
        })
        rows[-1]["loss_category"] = _loss_category(
            raw_rank=expected_rank,
            accepted=accepted,
            rejected=rejected,
            candidate_position=candidate_position,
            in_pipeline_selected=pipeline_selected,
            in_context=in_context,
        )
    labeled = [row for row in rows if row.get("expected_document_id")]
    def _set(field):
        return {row["id"] for row in labeled if row.get(field)}

    raw5, raw10, raw30 = _set("raw_top5"), _set("raw_top10"), _set("raw_top30")
    pipeline_selected = _set("pipeline_selected")
    llm_context = _set("expected_in_llm_context")
    metrics = {
        "questions": len(rows),
        "approved_labeled_questions": len(labeled),
        "top1": sum(row.get("expected_rank") == 1 for row in labeled),
        "top5": sum(bool(row.get("expected_rank") and row["expected_rank"] <= 5) for row in labeled),
        "top10": len(raw10),
        "top30": len(raw30),
        "pipeline_selected_expected": sum(row["expected_document_id"] in row["selected_documents"]
                                          for row in labeled),
        "llm_context_expected": len(llm_context),
        "set_intersections": {
            "raw_top5_and_pipeline_selected": len(raw5 & pipeline_selected),
            "raw_top5_and_llm_context": len(raw5 & llm_context),
            "pipeline_selected_and_llm_context": len(pipeline_selected & llm_context),
            "raw_top5_and_pipeline_selected_and_llm_context": len(raw5 & pipeline_selected & llm_context),
        },
        "erroneous_rejections": sum(bool(row["expected_rejected_reasons"]) for row in labeled),
        "extra_selected_documents": sum(len(row["extra_documents"]) for row in labeled),
        "service_detection_errors": sum(bool(row["declared_service"] and row["expected_service"]
                                             and row["declared_service"].casefold()
                                             != row["expected_service"].casefold())
                                        for row in labeled),
        "selected_service_errors": sum(len(row.get("selected_service_errors", [])) for row in rows),
        "rejection_reasons": dict(Counter(reason for row in labeled
                                           for reason in row["expected_rejected_reasons"])),
        "loss_categories": dict(Counter(row["loss_category"] for row in labeled
                                         if row.get("loss_category"))),
    }
    return {"collection": collection, "metrics": metrics,
            "chunk_order": _chunk_order(adapter, documents), "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", action="append", required=True,
                        help="Collection to evaluate; repeat for CURRENT and STAGING")
    parser.add_argument("--questions", type=Path, default=Path("data/evaluation_questions.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path,
                        help="Optional compact per-question CSV for approved references")
    args = parser.parse_args()
    active = os.getenv("QDRANT_COLLECTION")
    documents = DocumentLoader(Path("data/knowledge")).load_all()
    report = {
        "active_collection": active,
        "llm_calls": 0,
        "questions_file": str(args.questions),
        "collections": [evaluate(name, _questions(args.questions), documents)
                        for name in args.collection],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.csv_output:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        fields = ["id", "expected_source", "expected_document_id", "expected_rank",
                  "raw_top5", "raw_top10", "raw_top30", "expected_filter_passed",
                  "expected_rejected_reasons", "pipeline_selected",
                  "expected_in_llm_context", "loss_category", "determined",
                  "expected_metadata", "selected_documents", "context_document_ids"]
        with args.csv_output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in next(item for item in report["collections"]
                            if item["collection"] == args.collection[-1])["rows"]:
                if not row.get("expected_document_id"):
                    continue
                writer.writerow({field: json.dumps(row[field], ensure_ascii=False)
                                 if isinstance(row.get(field), (dict, list)) else row.get(field)
                                 for field in fields})
    print(json.dumps({item["collection"]: {"metrics": item["metrics"],
                                             "chunk_order": item["chunk_order"]}
                      for item in report["collections"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
