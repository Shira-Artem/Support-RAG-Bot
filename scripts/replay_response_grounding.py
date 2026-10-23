"""Replay saved 23.10.2026 model outputs through grounding without an LLM call."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.answer_service import _parse_scenario, _safe_alternative, _validation_issue
from app.dialogue_state import DialogueManager, DialogueState
from app.rag import SearchResult
from app.response_grounding import claim_supported, needs_procedure_grounding, statements


def replay(case: dict) -> dict:
    results = [SearchResult(item["source"], item["text"], .9, metadata=item["metadata"])
               for item in case["results"]]
    context = "\n\n".join(result.text for result in results)
    state = DialogueManager().advance(
        DialogueState(), f"{case['service']}. {case['question']}", case["id"])
    state.operation = case["operation"]
    if case["operation"] in {"add_employee", "change_permissions", "assign_role"}:
        state.intent = "access"
    _, _, raw = _parse_scenario(case["raw"])
    request = f"{case['service']}: {case['question']}"
    issue = ("procedural_details_not_grounded"
             if needs_procedure_grounding(raw, context, state, results)
             else _validation_issue(raw, context, request, case["service"], results=results))
    diagnostics = {}
    new_final = (_safe_alternative(raw, issue, request, context=context,
                                   state=state, results=results, diagnostics=diagnostics)
                 if issue else raw)
    confirmed = sum(claim_supported(line, context, evidence_results=results)
                    for line in statements(new_final))
    unsafe = _validation_issue(new_final, context, request, case["service"], results=results)
    return {
        "id": case["id"],
        "service": case["service"],
        "raw": raw,
        "old_final": case["old_final"],
        "new_final": new_final,
        "old_validation_reason": case["old_validation_reason"],
        "new_validation_issue": unsafe,
        "removed": diagnostics.get("removed", []),
        "confirmed_lines": confirmed,
        "evidence_kinds": [item.get("kind") for item in diagnostics.get("evidence", [])],
    }


def main() -> None:
    payload = json.loads((ROOT / "tests/fixtures/response_grounding_incidents_2026-10-23.json").read_text(encoding="utf-8"))
    print("offline replay: saved raw -> old baseline -> new validator; llm_calls=0")
    results = [replay(case) for case in payload["cases"]]
    for result in results:
        print(f"\n## {result['id']} / {result['service']}")
        print("RAW:", result["raw"])
        print("OLD FINAL:", result["old_final"])
        print("NEW FINAL:", result["new_final"])
        print("confirmed_lines:", result["confirmed_lines"],
              "removed:", len(result["removed"]),
              "new_validation_issue:", result["new_validation_issue"])
    print("\nunsafe_new_answers:", sum(bool(result["new_validation_issue"])
                                for result in results))


if __name__ == "__main__":
    main()
