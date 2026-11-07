"""Bounded Groq LIVE for the information-only semantic selector/Composer.

Uses exact local approved sections as frozen candidate evidence and a fresh
isolated DialogueState per synthetic question. It does not open SQLite,
Qdrant, Telegram, production worker, or frozen holdout.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import sleep

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)

from app.config import get_settings
from app.dialogue_state import DialogueState, Fact, TaskContext
from app.semantic_evidence_selector import build_evidence_units
from app.source_first_service import SourceFirstService, _sections

CASES = [
    {"id": "directbank_schedule", "question":
     "В каких условиях 1С:Бухгалтерия сможет автоматически получать выписки через DirectBank?",
     "source": "data/knowledge/1c/bank/directbank-auto-schedule.md",
     "section": "Подтверждённая возможность", "object": "автоматическое получение выписок",
     "entities": {"software": "1С:Бухгалтерия 8", "integration": "DirectBank"},
     "before": "В approved-источниках нет подходящего концептуального объяснения; не буду подменять его технической инструкцией. Запросите специалиста."},
    {"id": "usb_hub_guarantee", "question":
     "Для стороннего USB-хаба производитель подтверждает работу одновременно с зарядкой кассы?",
     "source": "data/knowledge/aqsi_devices/peripherals/scanner-hub-power.md",
     "section": "Проверенная информация и первичная диагностика", "object": "совместимость USB-хаба",
     "entities": {"manufacturer": "aQsi", "equipment": "aQsi (физическая ККТ)"},
     "before": "Какой сервис или оператор ОФД используется?"},
    {"id": "ofd_document_flow", "question":
     "Что происходит с фискальным документом после того, как касса его отправила ОФД?",
     "source": "data/knowledge/atol_online/ofd/what-is-ofd.md",
     "section": "Что проверено по инструкции производителя", "object": "передача фискального документа",
     "entities": {},
     "before": "ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает и передаёт их в ФНС в предусмотренном формате."},
]


def evidence_item(case: dict) -> dict:
    path = ROOT / case["source"]
    raw = path.read_text(encoding="utf-8")
    front = yaml.safe_load(raw.split("---", 2)[1]) or {}
    body = raw.split("---", 2)[2].strip()
    text = dict(_sections(body)).get(case["section"])
    if front.get("status") != "approved" or not text:
        raise RuntimeError(f"candidate_not_approved_or_missing:{case['id']}")
    return {"id": front["document_id"] + "::" + case["section"],
        "document_id": front["document_id"], "source": case["source"],
        "source_sha256": sha256(path.read_bytes()).hexdigest(),
        "section": case["section"], "text": text,
        # YAML front matter may parse verified_at/published_at as date objects;
        # the selector contract is JSON, so normalize metadata to JSON values.
        "scope": json.loads(json.dumps(front, ensure_ascii=False, default=str))}


async def main() -> None:
    settings = get_settings()
    if settings.llm_provider != "groq" or not settings.groq_api_key:
        raise RuntimeError("Groq is not configured; no LIVE request sent")
    settings = settings.__class__(**{**asdict(settings),
        "semantic_evidence_selector_enabled": True, "semantic_composer_enabled": True,
        "docs_dir": ROOT / "data" / "knowledge"})
    service = SourceFirstService(None, settings, ROOT)
    report = {"created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": "local approved candidate IDs -> real Groq semantic selector -> exact local SHA/scope validation -> real Groq Composer -> independent Python claim/safety validation",
        "model": settings.groq_model, "cases": []}
    output = ROOT / "reports/b2_2d_20261107/p02_selected_live.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    for index, case in enumerate(CASES):
        item = evidence_item(case)
        build_evidence_units([item], informational=True)
        facts = {slot: [Fact.span(value, 1)] for slot, value in case["entities"].items()}
        task = TaskContext(task_id="p02:" + case["id"], intent="general",
            request_type="information", operation="explain", object=case["object"], entities=facts)
        state = DialogueState(task_context=task)
        try:
            answer = await service._coordinated_information_answer(case["question"], state,
                [item], {"current_subgoal": case["question"]}, 0.0,
                {"retrieval_diagnostics": {}})
            report["cases"].append({"id": case["id"], "question": case["question"],
                "before_sourcefirst": case["before"], "after": answer.text,
                "reason": answer.scenario_reason, "validation_status": answer.validation_status,
                "composer_candidate": answer.raw_model_text,
                "diagnostics": answer.retrieval_diagnostics,
                "usage": {key: getattr(answer, key) for key in
                    ("prompt_tokens", "completion_tokens", "total_tokens")}})
        except Exception as exc:
            report["cases"].append({"id": case["id"], "question": case["question"],
                "before_sourcefirst": case["before"], "error_type": type(exc).__name__,
                "error_status": getattr(exc, "http_status", None),
                "error_stage": getattr(exc, "stage", None)})
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            break
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report["cases"][-1], ensure_ascii=False), flush=True)
        if index + 1 < len(CASES):
            sleep(15)


if __name__ == "__main__":
    asyncio.run(main())
