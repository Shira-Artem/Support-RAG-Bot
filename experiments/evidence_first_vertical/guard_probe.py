"""Synthetic verifier probes only; these are not end-to-end customer cases."""
from __future__ import annotations

from dataclasses import asdict
import json

from experiments.evidence_first_vertical.planner import HERE, ROOT, render
from experiments.evidence_first_vertical.prototype import build_cards, index_documents


def main() -> None:
    index = index_documents()
    case = {"id": "guard_probe", "question": "Нужна инструкция", "messages": ["Нужна инструкция"]}
    safe = next(c for c in build_cards("aqsi-device-x-report", index) if "Откройте" in c.text)
    risky = next(c for c in build_cards("aqsi-device-fn18-expired", index) if c.risk_flag)
    draft_id = next(doc for doc, (_, meta, _) in index.items() if meta.get("status") == "draft")
    trials = [
        ("invented_group", [], {"mode": "answer", "group_id": "G999", "missing_slot": None}),
        ("tampered_source", [{"id": "G1", "document_id": safe.document_id,
                              "cards": [{**asdict(safe), "text": safe.text + " Выдуманное действие."}]}],
         {"mode": "answer", "group_id": "G1", "missing_slot": None}),
        ("risky_source", [{"id": "G1", "document_id": risky.document_id,
                           "cards": [asdict(risky)]}],
         {"mode": "answer", "group_id": "G1", "missing_slot": None}),
        ("draft_status", [{"id": "G1", "document_id": draft_id,
                            "cards": [asdict(safe)]}],
         {"mode": "answer", "group_id": "G1", "missing_slot": None}),
    ]
    rows = []
    for name, groups, proposal in trials:
        result = render(case, proposal, groups, index)
        rows.append({"probe": name, "mode": result["mode"], "rejected": result["rejected"],
                     "technical_units_published": len(result["source_units"])})
    assert all(row["mode"] == "escalate" and row["technical_units_published"] == 0 for row in rows)
    (HERE / "guard-probes.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
