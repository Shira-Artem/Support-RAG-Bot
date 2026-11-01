"""Merge diagnostics from the isolated replay SQLite into its report JSON."""
from __future__ import annotations

import glob
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "bounded_live_results.json"
data = json.loads(OUT.read_text(encoding="utf-8"))
by_question = {case["question"]: case for case in data["cases"]}
found = set()
for path in glob.glob(str(ROOT / ".local/architecture-audit-*/test.sqlite3")):
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    for question, diagnostics in con.execute("""SELECT q.content, a.diagnostics_json FROM messages q
        JOIN messages a ON a.id=q.id+1 AND a.conversation_id=q.conversation_id
        WHERE q.role='user' AND a.role='assistant'"""):
        case = by_question.get(question)
        if not case or question in found or not diagnostics:
            continue
        d = json.loads(diagnostics)
        rd = d.get("retrieval_diagnostics") or {}
        case["retrieval_detail"] = {
            "sufficient": rd.get("sufficient"),
            "insufficiency_reason": rd.get("insufficiency_reason"),
            "evaluated_candidates": [{"source": x.get("source"), "reasons": x.get("reasons"),
                                      "metadata": x.get("metadata"), "retrieval": x.get("retrieval")}
                                     for x in rd.get("candidates", [])],
            "conceptual_evidence_gate": rd.get("conceptual_evidence_gate"),
            "coordinator_evidence": rd.get("coordinator_evidence"),
            "planner": rd.get("planner"),
        }
        case["validation_status"] = d.get("validation_status")
        case["validation_reason"] = d.get("validation_reason")
        found.add(question)
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"enriched": len(found), "attempted": len(by_question)}, ensure_ascii=False))
