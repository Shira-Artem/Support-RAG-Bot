"""Offline Source-first scope E2E against read-only Stage3 Qdrant.

Uses real embeddings/retrieval and the production SourceFirstService. Planner
generation is a deterministic local fixture; this script never contacts Groq,
Telegram, or any Qdrant write endpoint. Sanitized result JSON is written only
under ignored .local/.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)
STAGE3 = "knowledge_stage3_retrieval_20261022"
os.environ.update({
    "RAG_BACKEND": "qdrant", "QDRANT_COLLECTION": STAGE3, "RAG_DEMO_MODE": "0",
    "RAG_ENGINE": "source_first", "SOURCE_FIRST_TELEGRAM_IDS": "1",
    "AI_COORDINATOR_ENABLED": "1", "SEMANTIC_EVIDENCE_SELECTOR_ENABLED": "0",
    "HANDOFF_ENABLED": "0", "HF_HUB_OFFLINE": "1",
})

from qdrant_client import QdrantClient
from app.compat import RetrieverRAGAdapter
from app.config import get_settings
from app.dialogue_state import ActiveRoute, DialogueState, Fact, TaskContext
from app.embeddings import SentenceTransformerEmbedding
from app.llm_client import Generation
from app.retrieval import Retriever
import app.source_first_service as source_first_module
from app.source_first_service import SourceFirstService
from app.vector_store import QdrantStore


class ReadOnlyQdrant:
    """Allow retrieval reads and make every other client operation unavailable."""
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


CASES = [
    {"id": "ofd_definition", "question": "Привет! Объясни, что такое ОФД и зачем он нужен?",
     "intent": "general", "operation": "explain", "object": "ОФД",
     "preferred_section": "Вопрос пользователя"},
    {"id": "fn_vs_ofd_comparison",
     "question": "Чем отличается фискальный накопитель от оператора фискальных данных?",
     "intent": "general", "operation": "explain", "object": "понятие",
     "preferred_section": "Вопрос пользователя"},
    {"id": "api_definition", "question": "Что такое API?",
     "intent": "general", "operation": "explain", "object": "понятие",
     "preferred_section": "Вопрос пользователя"},
    {"id": "dns_principle", "question": "Как работает DNS?",
     "intent": "general", "operation": "explain", "object": "понятие",
     "preferred_section": "Вопрос пользователя"},
    {"id": "local_cloud_comparison",
     "question": "В чём разница между локальной программой и облачным сервисом?",
     "intent": "general", "operation": "explain", "object": "понятие",
     "preferred_section": "Вопрос пользователя"},
    {"id": "fn234", "question": "На кассе появилась ошибка ФН 234. Что она означает и какие безопасные проверки доступны?",
     "intent": "fiscal_drive", "operation": "diagnose", "object": "ФН 234",
     "preferred_section": "Первое различение причины"},
    {"id": "fn234_misclassified_general", "question": "На кассе появилась ошибка ФН 234. Что она означает и какие безопасные проверки доступны?",
     "intent": "general", "operation": "explain", "object": "ФН 234",
     "preferred_section": "Первое различение причины"},
    {"id": "directbank", "question": "В 1С перестали загружаться банковские выписки через DirectBank. Помоги разобраться, с чего начать проверку?",
     "intent": "bank_statement", "operation": "diagnose", "object": "банковская выписка",
     "entities": {"software": "1С", "integration": "DirectBank"},
     "preferred_section": "Безопасная диагностика"},
    {"id": "evotor73", "question": "У меня Эвотор 7.3. Чеки пробиваются, но не уходят в ОФД. Помоги разобраться, с чего начать?",
     "intent": "receipt", "operation": "diagnose", "object": "чек",
     "entities": {"manufacturer": "Эвотор", "equipment": "Эвотор 7.3"},
     "preferred_section": "Что проверить сначала"},
    {"id": "tspiot", "question": "На кассе Эвотор модуль ТС ПИоТ не запускается; нужны первые проверки.",
     "intent": "device", "operation": "diagnose", "object": "модуль ТС ПИоТ",
     "entities": {"manufacturer": "Эвотор", "component": "ТС ПиОТ"},
     "preferred_section": "Безопасная проверка"},
    {"id": "wrong_model", "question": "Эвотор 7.3: не передаются чеки в ОФД.",
     "intent": "receipt", "operation": "diagnose", "object": "чек",
     "entities": {"manufacturer": "Эвотор", "equipment": "Эвотор 6"},
     "preferred_section": "Что проверить сначала", "negative": True},
    {"id": "wrong_manufacturer", "question": "Эвотор 7.3: не передаются чеки в ОФД.",
     "intent": "receipt", "operation": "diagnose", "object": "чек",
     "entities": {"manufacturer": "АТОЛ", "equipment": "АТОЛ Онлайн"},
     "preferred_section": "Что проверить сначала", "negative": True},
    {"id": "negative_fn_operation", "question": "Как закрыть архив ФН самостоятельно?",
     "intent": "fiscal_drive", "operation": "diagnose", "object": "архив ФН",
     "preferred_section": "Первое различение причины", "negative_operation": True},
    {"id": "negative_fn_error_operation", "question": "Как исправить ошибку ФН 234?",
     "intent": "fiscal_drive", "operation": "diagnose", "object": "ФН 234",
     "preferred_section": "Первое различение причины", "negative_operation": True},
    {"id": "negative_technical_configuration", "question": "Как настроить кассу?",
     "intent": "device", "operation": "configure", "object": "кассу",
     "preferred_section": "Безопасная диагностика", "negative_operation": True},
]


def _state(case: dict) -> DialogueState:
    question = case["question"]
    entities = {}
    for slot, value in case.get("entities", {}).items():
        entities[slot] = [Fact(value, 1, value, 0, len(value))]
    route = next((ActiveRoute(slot, values[0]) for slot, values in entities.items()
                  if slot in {"manufacturer", "software", "service", "ofd"}), None)
    task = TaskContext(task_id=case["id"], topic_start_message_id=1,
        intent=case["intent"], operation=case["operation"], object=case["object"],
        entities=entities, active_route=route,
        task_fact=Fact(question, 1, question, 0, len(question)))
    return DialogueState(task_context=task)


async def _offline_plan(messages, _settings, *, call_stage="generation"):
    if call_stage == "general_knowledge":
        question = messages[-1]["content"]
        if "накопитель" in question.casefold():
            answer = ("Фискальный накопитель записывает фискальные документы и формирует фискальный признак. "
                      "Оператор фискальных данных получает документы от кассы и передаёт их в ФНС: "
                      "первый фиксирует данные в составе ККТ, второй обеспечивает их передачу дальше.")
        elif "api" in question.casefold():
            answer = "API — это способ, которым программы обмениваются запросами и данными по согласованным правилам."
        elif "dns" in question.casefold():
            answer = "DNS сопоставляет доменное имя с сетевым адресом, который нужен устройству для соединения с узлом."
        elif "локальной программой" in question.casefold():
            answer = ("Локальная программа выполняется на устройстве пользователя, а облачный сервис работает "
                      "на удалённой инфраструктуре и доступен через сеть.")
        else:
            answer = "ОФД получает фискальные документы от кассы и передаёт их налоговой службе."
        completion_tokens = max(1, len(answer) // 4)
        return Generation(
            answer, "offline-general-knowledge-fixture", prompt_tokens=22,
            completion_tokens=completion_tokens, total_tokens=22 + completion_tokens)
    payload = json.loads(messages[-1]["content"])
    candidates = payload.get("candidate_sections", [])
    # The source-first planner request carries exact approved candidate IDs;
    # this local fixture selects the requested section and never creates text.
    preferred = os.environ.get("SOURCE_SCOPE_E2E_SECTION", "")
    selected = next((item for item in candidates
                     if preferred.casefold() in item.get("section", "").casefold()), None)
    if selected is None and candidates:
        selected = candidates[0]
    plan = ({"mode": "select", "section_id": selected["id"],
             "applicability_confirmed": True, "order_confirmed": True,
             "reason": "deterministic offline section-id fixture"} if selected else
            {"mode": "escalate", "section_id": "", "applicability_confirmed": False,
             "order_confirmed": False, "reason": "no candidate"})
    return Generation(json.dumps(plan, ensure_ascii=False), "offline-section-fixture")


def _summary(case: dict, answer, retrieval_result) -> dict:
    diagnostics = answer.retrieval_diagnostics or {}
    return {
        "case": case["id"], "scenario": answer.scenario,
        "scenario_reason": answer.scenario_reason,
        "clarification_slot": answer.clarification_slot,
        "answer": answer.text,
        "selected_documents": [{"document_id": item.document_id,
            "source": item.source, "reasons": item.reasons}
            for item in retrieval_result.candidates if item.selected],
        "rejected_documents": [{"document_id": item.document_id,
            "source": item.source, "reasons": item.reasons}
            for item in retrieval_result.rejected[:12]],
        "retrieval_sufficient": retrieval_result.sufficient,
        "retrieval_insufficiency_reason": retrieval_result.insufficiency_reason,
        "source_scope_gate": diagnostics.get("source_scope_gate"),
        "coordinator_claim_validation": diagnostics.get("coordinator_claim_validation"),
        "general_knowledge_fallback": diagnostics.get("general_knowledge_fallback"),
        "llm_call_attempted": answer.llm_call_attempted,
        "llm_retry_count": answer.llm_retry_count,
        "llm_retry_wait_seconds": answer.llm_retry_wait_seconds,
        "generation_status": answer.generation_status,
        "validation_status": answer.validation_status,
    }


async def _run() -> list[dict]:
    settings = get_settings()
    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), timeout=15)
    info = client.get_collection(STAGE3)
    if not info.points_count or str(info.status) != "green":
        raise RuntimeError(f"Stage3 is not green/nonempty: {info.points_count}/{info.status}")
    embedding = SentenceTransformerEmbedding(os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    rag = RetrieverRAGAdapter(Retriever(QdrantStore(ReadOnlyQdrant(client), embedding, STAGE3), demo=False))
    service = SourceFirstService(rag, settings, ROOT)
    original_generate = source_first_module.generate
    source_first_module.generate = _offline_plan
    results = []
    try:
        for case in CASES:
            os.environ["SOURCE_SCOPE_E2E_SECTION"] = case["preferred_section"]
            state = _state(case)
            retrieval = rag.search_for_state(state, case["question"])
            route = ("grounded_information" if state.intent == "general"
                     and state.operation == "explain" else "technical_action")
            answer = await service.answer(case["question"], state=state,
                coordinator_decision={"route": route,
                                      "current_subgoal": case["question"]})
            results.append(_summary(case, answer, retrieval))
    finally:
        source_first_module.generate = original_generate
        os.environ.pop("SOURCE_SCOPE_E2E_SECTION", None)
        client.close()
    return results


def _assert_results(results: list[dict]) -> None:
    by_id = {item["case"]: item for item in results}
    conceptual = ("ofd_definition", "fn_vs_ofd_comparison", "api_definition",
                  "dns_principle", "local_cloud_comparison")
    for case_id in conceptual:
        item = by_id[case_id]
        assert item["scenario"] == "answer", item
        assert "Общее объяснение (сформулировано моделью, не по approved-документации)" in item["answer"], item
        assert "Источник:" not in item["answer"] and "http" not in item["answer"].lower(), item
        assert item["general_knowledge_fallback"]["source_basis"] == "model_general_knowledge", item
    compared = by_id["fn_vs_ofd_comparison"]["answer"]
    assert "Фискальный накопитель" in compared and "Оператор фискальных данных" in compared, compared
    assert "попросите клиента" not in compared.casefold() and "сопоставьте сервер" not in compared.casefold()
    for case_id in ("fn234", "directbank"):
        item = by_id[case_id]
        assert item["clarification_slot"] != "service", item
        assert "оператор ОФД" not in item["answer"], item
    fn = by_id["fn234"]
    assert fn["scenario"] == "answer" and "Область источника: Эвотор" in fn["answer"], fn
    assert "Проверьте" not in fn["answer"] and "Настройки →" not in fn["answer"], fn
    fn_misclassified = by_id["fn234_misclassified_general"]
    assert fn_misclassified["scenario"] == "answer", fn_misclassified
    assert "model_general_knowledge" not in str(fn_misclassified["general_knowledge_fallback"]), fn_misclassified
    assert "Статья производителя связывает код ФН 234" in fn_misclassified["answer"], fn_misclassified
    bank = by_id["directbank"]
    assert bank["scenario"] == "answer" and bank["clarification_slot"] is None, bank
    assert bank["source_scope_gate"]["eligible_source_count"] > 0, bank
    assert any(item["source"] == "1c/bank/directbank-all-accounts.md"
               for item in by_id["directbank"]["selected_documents"]), by_id["directbank"]
    assert any(item["source"] == "evotor/ofd/evotor-7-3-ofd-connection.md"
               for item in by_id["evotor73"]["selected_documents"]), by_id["evotor73"]
    assert by_id["evotor73"]["clarification_slot"] is None, by_id["evotor73"]
    assert any(item["source"] == "evotor/tspiot/local-module-startup.md"
               for item in by_id["tspiot"]["selected_documents"]), by_id["tspiot"]
    assert by_id["tspiot"]["clarification_slot"] not in {"service", "ofd"}, by_id["tspiot"]
    for case_id, forbidden in (("wrong_model", "evotor-7-3-ofd-connection.md"),
                               ("wrong_manufacturer", "evotor-7-3-ofd-connection.md")):
        item = by_id[case_id]
        assert item["scenario"] in {"clarify", "escalate"}, item
        gate = item["source_scope_gate"] or {}
        assert (any(row.get("reason") == "confirmed_scope_mismatch"
                    for row in gate.get("inapplicable", []))
                or any(row["source"].endswith(forbidden) and
                       any(reason.startswith(("manufacturer_mismatch", "equipment_mismatch",
                                              "service_mismatch")) for reason in row.get("reasons", []))
                       for row in item["rejected_documents"])), item
        # Retrieval may rank a wrong-scope document as a candidate; the final
        # Source-first scope gate must reject it before rendering any procedure.
        assert "Откройте" not in item["answer"] and "Настройки →" not in item["answer"], item
    dangerous = by_id["negative_fn_operation"]
    assert dangerous["scenario"] == "escalate" and dangerous["scenario_reason"] == "unsafe_operation", dangerous
    technical = by_id["negative_technical_configuration"]
    assert technical["general_knowledge_fallback"] is None, technical
    assert technical["scenario"] != "answer" or "Общее объяснение" not in technical["answer"], technical
    error = by_id["negative_fn_error_operation"]
    assert error["general_knowledge_fallback"] is None, error
    assert "Общее объяснение" not in error["answer"], error


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    results = asyncio.run(_run())
    output = ROOT / ".local/source-scope-offline-e2e.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"created_at_utc": datetime.now(timezone.utc).isoformat(),
        "qdrant_collection": STAGE3, "qdrant_mode": "read-only", "planner": "offline fixture",
        "provider_calls": 0, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    _assert_results(results)
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    print(f"PASS: {len(results)} Stage3 read-only E2E scenarios; report saved privately to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
