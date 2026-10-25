"""Local Source-first contract smoke; never calls Telegram, Qdrant, or an LLM."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config import Settings, should_use_source_first  # noqa: E402
from app.source_first_service import _approved_sources, _sections, _source_sections  # noqa: E402
from experiments.telegram_source_first_integration.export_anonymized import mask_text  # noqa: E402


def main() -> int:
    enabled = Settings("", "", "", "Support", "", True, ROOT / "data/docs",
                       rag_engine="source_first", source_first_telegram_ids=frozenset({111, 222}))
    legacy = Settings("", "", "", "Support", "", True, ROOT / "data/docs")
    assert should_use_source_first(enabled, 111)
    assert not should_use_source_first(enabled, 333)
    assert not should_use_source_first(legacy, 111)

    sources = _approved_sources(ROOT)
    assert sources, "No local approved source documents found"
    doc_id, (path, metadata, body) = next(iter(sources.items()))
    heading, section = _sections(body)[0]
    fake_hit = SimpleNamespace(metadata={"document_id": doc_id, "section": heading})
    fake_retrieval = SimpleNamespace(
        documents=[fake_hit],
        diagnostics=lambda: {"selected": [{"document_id": doc_id,
                                               "metadata": {"section": heading}}]},
    )
    candidates = _source_sections(None, fake_retrieval, ROOT)
    assert len(candidates) == 1
    assert candidates[0]["text"] == section
    assert candidates[0]["source_sha256"] == sha256(path.read_bytes()).hexdigest()
    assert metadata["status"] == "approved"
    sample = "\u041c\u0435\u043d\u044f \u0437\u043e\u0432\u0443\u0442 \u0418\u0432\u0430\u043d \u0418\u0432\u0430\u043d\u043e\u0432, email: ivan@example.com, \u0442\u0435\u043b\u0435\u0444\u043e\u043d: +7 999 123-45-67"
    masked = mask_text(sample)
    assert "[NAME]" in masked and "[REDACTED]" in masked and "ivan@example.com" not in masked
    print("PASS: allowlist exact; legacy unchanged; approved exact section/SHA verified; common PII masks; external calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
