from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.knowledge import Chunker, DocumentLoader
from app.rag import SimpleRAG


def test_legacy_threshold_does_not_return_first_weak_hit(tmp_path: Path):
    (tmp_path / "one.txt").write_text("Касса и чеки", encoding="utf-8")
    rag = SimpleRAG(tmp_path)
    assert rag.search("совсем другая тема", min_score=0.99) == []
    assert rag.search("касса", top_k=0) == []


def test_load_and_chunk_metadata(tmp_path: Path):
    (tmp_path / "guide.md").write_text("""---
document_id: guide-1
title: Проверка ККТ
category: kkt
model: АТОЛ 30Ф
status: approved
verified_at: 2026-10-12
collected_at: 2026-10-12
---
# Проверка кассы

Шаг 1. Подключите кассу.

Шаг 2. Напечатайте тестовый чек.
""", encoding="utf-8")
    (tmp_path / "plain.txt").write_text("Обычный текст", encoding="utf-8")
    (tmp_path / "page.html").write_text("<html><head><title>Инструкция</title><style>junk</style></head><body><nav>junk</nav><main><h1>ОФД</h1><p>Чеки не отправляются.</p></main></body></html>", encoding="utf-8")
    docs = DocumentLoader(tmp_path).load_all()
    guide = next(doc for doc in docs if doc.source == "guide.md")
    assert guide.status == "approved" and guide.model == "АТОЛ 30Ф"
    assert guide.collected_at == "2026-10-12"
    assert next(doc for doc in docs if doc.source == "plain.txt").status == "draft"
    html = next(doc for doc in docs if doc.source == "page.html")
    assert "junk" not in html.pages[0][1] and "Чеки" in html.pages[0][1]
    chunks = Chunker().split(guide)
    assert "Шаг 1" in chunks[0].text and "Шаг 2" in chunks[0].text
    assert chunks[0].section == "Проверка кассы"
    assert chunks[0].metadata["source"] == "guide.md"
    assert chunks[0].metadata["collected_at"] == "2026-10-12"
    assert chunks[0].id == Chunker().split(guide)[0].id


def test_duplicate_content_and_scanned_pdf(tmp_path: Path):
    (tmp_path / "a.txt").write_text("Одинаковый документ", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Одинаковый документ", encoding="utf-8")
    assert len(DocumentLoader(tmp_path).load_all()) == 1
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with (tmp_path / "scan.pdf").open("wb") as file:
        writer.write(file)
    with pytest.raises(ValueError, match="no extractable text layer"):
        DocumentLoader(tmp_path).load(tmp_path / "scan.pdf")


def test_pdf_page_number(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "text.pdf"
    pdf.write_bytes(b"%PDF-test")

    class Page:
        def extract_text(self):
            return "Инструкция на странице"

    class Reader:
        pages = [Page()]

    monkeypatch.setattr("app.knowledge.PdfReader", lambda _: Reader())
    chunk = Chunker().split(DocumentLoader(tmp_path).load(pdf))[0]
    assert chunk.page == 1 and chunk.metadata["page"] == 1


def test_status_validation(tmp_path: Path):
    path = tmp_path / "bad.md"
    path.write_text("---\nstatus: published\n---\nТекст", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid status"):
        DocumentLoader(tmp_path).load(path)
    path.write_text("---\nstatus: approved\n---\nТекст", encoding="utf-8")
    with pytest.raises(ValueError, match="requires verified_at"):
        DocumentLoader(tmp_path).load(path)


def test_normalized_metadata_survives_sidecar_and_qdrant_update(tmp_path: Path):
    from qdrant_client import QdrantClient
    from app.vector_store import QdrantStore

    class Embedding:
        dimension = 2

        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    path = tmp_path / "guide.md"
    path.write_text("---\nservice: Cloud service\ntask_category: access\n"
                    "operations: [assign_role, assign_role]\nsearch_fields: email\n"
                    "source_checked_at: 2026-10-21\n---\n# User guide\n\nChoose a role.", encoding="utf-8")
    loader = DocumentLoader(tmp_path)
    before = loader.load(path)
    store = QdrantStore(QdrantClient(":memory:"), Embedding())
    store.index([before])
    original_ids = {p.id for p in store.all_points()}
    # A metadata-only edit must refresh payload despite the unchanged body hash.
    path.with_name(path.name + ".meta.yaml").write_text(
        "operations: [change_permissions]\nsearch_fields: [email, user_name]\n", encoding="utf-8")
    after = loader.load(path)
    assert before.content_hash == after.content_hash
    assert store.index([after])["indexed"] == 1
    assert {p.id for p in store.all_points()} == original_ids
    payload = store.all_points()[0].payload
    assert payload["service"] == "Cloud service" and payload["task_category"] == "access"
    assert payload["operations"] == ["change_permissions"]
    assert payload["search_fields"] == ["email", "user_name"]
    assert payload["source_checked_at"] == "2026-10-21" and payload["status"] == "draft"
    assert store.index([after])["unchanged"] == 1


@pytest.mark.parametrize("metadata", ["operations: [1]", "search_fields: {bad: value}",
                                     "service: [bad]", "source_checked_at: yesterday"])
def test_normalized_metadata_rejects_malformed_values(tmp_path: Path, metadata):
    path = tmp_path / "bad.md"
    path.write_text(f"---\n{metadata}\n---\nUseful text", encoding="utf-8")
    with pytest.raises(ValueError):
        DocumentLoader(tmp_path).load(path)
