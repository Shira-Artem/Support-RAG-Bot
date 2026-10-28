from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient
from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueManager, DialogueState
from app.embeddings import SentenceTransformerEmbedding
from app.knowledge import DocumentLoader
from app.rag_query import QueryNeedsClarification, build_rag_query
from app.retrieval import Retriever
from app.retrieval_pipeline import _matches_entity, _state_task_category, normalize_metadata
from app.vector_store import QdrantStore


CASES = [
    # All 16 frozen Sprint 3 staging cases.
    ("bifit_terminal", "В БИФИТ Касса подключён банковский терминал, но карта не проходит.", "candidate-kbqs3-bifit-pos-terminal-scope", "negative"),
    ("bifit_tables", "В БИФИТ Касса Общепит нужно проверить тестирование столов.", "candidate-kbqs3-bifit-horeca-tables-scope", "negative"),
    ("diadoc_status", "Диадок: контрагент не видит отправленный УПД, хочу проверить статус.", "candidate-kbqs3-diadoc-outgoing-status", "negative"),
    ("saby_incoming", "В Saby не могу найти входящий документ.", "candidate-kbqs3-saby-incoming-status", "negative"),
    ("evotor_marking", "Эвотор отклонил код маркировки при онлайн-проверке.", "candidate-kbqs3-evotor-marking-refusal", "positive"),
    ("evotor_combo", "Эвотор: как работает комбинированная оплата?", "candidate-kbqs3-evotor-combined-payment", "positive"),
    ("tspiot_generic", "Как диагностировать ошибку ТС ПиОТ?", "candidate-kbqs3-tspiot-api-scope", "negative"),
    ("atol_api", "АТОЛ Онлайн: после подтверждённой оплаты API чек не найден.", "candidate-kbqs3-atol-api-receipt-not-found", "negative"),
    ("negative_atol_evotor", "Эвотор: как работает комбинированная оплата?", "candidate-kbqs3-atol-api-receipt-not-found", "negative"),
    ("negative_bifit_evotor", "Эвотор отклонил код маркировки.", "candidate-kbqs3-bifit-pos-terminal-scope", "negative"),
    ("negative_diadoc_saby", "В Saby не могу найти входящий документ.", "candidate-kbqs3-diadoc-outgoing-status", "negative"),
    ("negative_status_atol", "АТОЛ Онлайн: как посмотреть статус подписания УПД?", "candidate-kbqs3-atol-api-receipt-not-found", "negative"),
    ("real_bifit", "Здравствуйте. Нам нужно протестировать в программе БИФИТ систему общепит со столами.", None, "negative"),
    ("real_marking", "При пробитии чека не считался код маркировки и эта позиция исчезла из чека.", None, "positive"),
    ("real_edo", "Не получаем документы по ЭДО в Честный ЗНАК.", None, "positive"),
    ("real_terminal", "В приложении не подключен ни один банковский терминал.", None, "positive"),
    # Independent wording, negative routing and scope controls.
    ("saby_paraphrase_1", "В кабинете СБИС не отображается входящий УПД от контрагента.", None, "negative"),
    ("saby_paraphrase_2", "Где в Saby посмотреть документы, которые пришли от поставщика?", None, "negative"),
    ("diadoc_paraphrase_1", "В Диадоке отправили УПД — где проверить, дошёл ли он до контрагента?", None, "negative"),
    ("diadoc_paraphrase_2", "Контрагент не видит наш исходящий документ в Диадоке. Какой у него статус?", None, "negative"),
    ("bifit_paraphrase_1", "Работаем в БИФИТ Касса: как проверить настройку столов в Общепите?", None, "negative"),
    ("bifit_paraphrase_2", "В программе БИФИТ не получается настроить рабочее место.", None, "negative"),
    ("unnamed_service", "Как найти входящий документ и проверить его статус?", None, "negative"),
    ("foreign_service", "В Saby ищу входящий УПД. Эвотор: как проверить код маркировки?", None, "negative"),
    ("same_vendor_distinct_product", "В АТОЛ Онлайн не вижу чек API, как проверить журнал?", None, "negative"),
    ("ambiguous_bifit_product", "В БИФИТ не работает терминал, как подключить?", None, "negative"),
    # Keep baseline product regressions on known current services.
    ("reg_atol_online", "В АТОЛ Онлайн как найти чек за вчера?", None, "positive"),
    ("reg_evotor", "Эвотор 6: как распечатать копию чека по ФД 123?", None, "positive"),
    ("reg_aqsi", "aQsi Online не вижу входящие документы по 1С.", None, "negative"),
    ("reg_aqsi_online_integration", "aQsi Online, как подключить к 1С:УНФ?", None, "positive"),
    ("reg_platformaofd", "В личном кабинете Платформа ОФД нужно найти чек за вчера.", None, "positive"),
]


def _facts(values):
    return [{"value": f.value, "quote": f.quote, "start": f.start, "end": f.end}
            for f in values]


def _unique_hits(hits):
    out, seen = [], set()
    for hit in hits:
        meta = hit.metadata or {}
        key = meta.get("document_id") or hit.source
        if key in seen:
            continue
        seen.add(key)
        out.append({"document_id": meta.get("document_id"), "source": meta.get("source") or hit.source,
                    "service": meta.get("service"), "manufacturer": meta.get("manufacturer"),
                    "software": meta.get("software"), "task_category": meta.get("task_category"),
                    "operations": meta.get("operations") or [], "score": hit.score})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    loader = DocumentLoader(ROOT / "data/knowledge")
    approved = [doc for doc in loader.load_all() if doc.status == "approved"]
    candidate_loader = DocumentLoader(ROOT / "reports/kb_quality_sprint_20261028/sprint3_candidates")
    candidates = [replace(candidate_loader.load(path), status="approved")
                  for path in sorted((ROOT / "reports/kb_quality_sprint_20261028/sprint3_candidates").glob("*.md"))]
    client = QdrantClient(":memory:")
    embedding = SentenceTransformerEmbedding("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    adapters = {}
    for name, docs in (("approved", approved), ("staging", approved + candidates)):
        store = QdrantStore(client, embedding, "routing_" + name)
        store.index(docs, remove_missing=True)
        adapters[name] = RetrieverRAGAdapter(Retriever(store, demo=False))

    manager = DialogueManager()
    results = []
    for case_id, message, forbidden_target, expected_scope in CASES:
        observation = manager.analyzer.analyze(message, case_id, DialogueState())
        state = manager.advance(DialogueState(), message, case_id, observation=observation)
        row = {
            "case_id": case_id, "message": message, "forbidden_target": forbidden_target,
            "case_scope_expectation": expected_scope,
            "lexical_observation": {
                "raw_entities": {slot: _facts(facts) for slot, facts in observation.entities.items()},
                "raw_intent": observation.intent, "raw_object": observation.object,
                "raw_operation": observation.operation, "raw_relation": observation.relation,
                "uncertain": observation.uncertain,
            },
            "validated_state": {
                "entities": {slot: _facts(facts) for slot, facts in state.task_entities.items()},
                "intent": state.intent, "object": state.object, "operation": state.operation,
                "relation": state.relation, "active_route": state.routing_slot,
                "routing_service": state.routing_service, "analysis_required": state.analysis_required,
            },
        }
        try:
            query = build_rag_query(state)
            row["rag_query"] = query
            row["expected_task"] = _state_task_category(state, query)
        except QueryNeedsClarification as exc:
            row["query_error"] = str(exc)
            query = None
        row["retrieval"] = {}
        for collection, adapter in adapters.items():
            if query is None:
                row["retrieval"][collection] = None
                continue
            raw = _unique_hits(adapter.search(query, top_k=adapter.pipeline.candidate_k))
            result = adapter.search_for_state(state, query)
            candidate_rows = []
            for item in result.candidates:
                candidate_rows.append({"document_id": item.document_id, "service": item.metadata.get("service"),
                    "task_category": item.metadata.get("task_category"), "reasons": item.reasons,
                    "selected": item.selected, "score": item.relevance.score})
            rejected_rows = [{"document_id": item.document_id, "service": item.metadata.get("service"),
                "task_category": item.metadata.get("task_category"), "reasons": item.reasons}
                for item in result.rejected]
            finals = [{"document_id": (hit.metadata or {}).get("document_id"),
                       "service": (hit.metadata or {}).get("service"), "source": hit.source}
                      for hit in result.documents]
            route = state.routing_service or state.task_entity("ofd")
            foreign = [item for item in finals if item.get("service") and route
                       and not _matches_entity(route, item.get("service"))]
            route_candidates = [item for item in finals if item.get("service") and route
                                and _matches_entity(route, item.get("service"))]
            row["retrieval"][collection] = {
                "raw_top_k": raw, "final_evidence": finals, "candidates": candidate_rows,
                "rejected": rejected_rows, "sufficient": result.sufficient,
                "evidence_status": result.evidence_status,
                "insufficiency_reason": result.insufficiency_reason,
                "forbidden_target_final": bool(forbidden_target and any(
                    item.get("document_id") == forbidden_target for item in finals)),
                "other_on_route_candidate_final": route_candidates,
                "foreign_service_candidate_final": foreign,
            }
        results.append(row)

    negative_pair_ids = {"negative_atol_evotor", "negative_bifit_evotor",
        "negative_diadoc_saby", "negative_status_atol"}
    stage_rows = [r for r in results if r["case_id"] in negative_pair_ids]
    def _cross_service_metrics(row):
        result = row["retrieval"]["staging"] or {}
        route = row["validated_state"]["routing_service"]
        final = {item["document_id"]: item for item in result.get("final_evidence", [])}
        target = row["forbidden_target"]
        foreign = [item for document_id, item in final.items()
                   if document_id != target and item.get("service") and route
                   and not _matches_entity(route, item.get("service"))]
        suitable_other = [item for document_id, item in final.items()
                          if document_id != target and item.get("service") and route
                          and _matches_entity(route, item.get("service"))]
        return {"forbidden_target_final": bool(target and target in final),
                "other_matching_service_final": suitable_other,
                "foreign_service_final": foreign}
    cross = [_cross_service_metrics(row) for row in stage_rows]
    summary = {
        "cases": len(results), "sprint3_frozen_cases": sum(r["case_id"] in {c[0] for c in CASES[:16]} for r in results),
        "named_service_cases": sum(bool(r["validated_state"]["routing_service"]) for r in results),
        "negative_cases": sum(c[3] == "negative" for c in CASES),
        "negative_forbidden_target_final_hits": sum(item["forbidden_target_final"] for item in cross),
        "negative_other_matching_service_final_cases": sum(bool(item["other_matching_service_final"]) for item in cross),
        "negative_real_foreign_service_final_cases": sum(bool(item["foreign_service_final"]) for item in cross),
        "llm_calls": 0, "production_qdrant_access": False, "production_kb_write": False,
        "approved_document_count": len(approved), "candidate_overlay_count": len(candidates),
    }
    payload = {"mode": "local_lexical_analyzer_in_memory_qdrant", "summary": summary, "cases": results}
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
