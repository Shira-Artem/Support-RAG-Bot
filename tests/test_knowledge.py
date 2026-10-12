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
