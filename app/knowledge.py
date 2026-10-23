"""Validated knowledge documents and section-aware ingestion."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from hashlib import sha256
from pathlib import Path
import re
from uuid import UUID, uuid5

from bs4 import BeautifulSoup
from pypdf import PdfReader
import yaml


NAMESPACE = UUID("70b01bd1-c23c-4ea0-9072-94521a475623")
FORMATS = {".md", ".txt", ".html", ".htm", ".pdf"}
STATUSES = {"draft", "approved", "deprecated"}


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


@dataclass(frozen=True)
class Document:
    document_id: str
    title: str
    category: str
    manufacturer: str | None
    model: str | None
    version: str | None
    source_url: str | None
    source_type: str
    published_at: str | None
    verified_at: str | None
    collected_at: str | None
    status: str
    content_hash: str
    source: str
    pages: list[tuple[int | None, str]]
    service: str | None = None
    software: str | None = None
    task_category: str | None = None
    operations: list[str] = field(default_factory=list)
    search_fields: list[str] = field(default_factory=list)
    source_checked_at: str | None = None
    procedure_service: str | None = None
    evidence_coverage: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeChunk:
    id: str
    text: str
    section: str | None
    page: int | None
    metadata: dict


class DocumentLoader:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def load(self, path: Path) -> Document:
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Document is outside the configured source directory")
        if path.suffix.lower() not in FORMATS:
            raise ValueError(f"Unsupported document format: {path.suffix}")
        raw = path.read_bytes()
        if len(raw) > 20_000_000:
            raise ValueError(f"Document is too large (20 MB limit): {path}")
        rel = path.relative_to(self.root).as_posix()
        metadata: dict = {}
        if path.suffix.lower() == ".pdf":
            reader = PdfReader(path)
            pages = [(i, clean(page.extract_text() or "")) for i, page in enumerate(reader.pages, 1)]
            pages = [(i, body) for i, body in pages if body]
            if not pages:
                raise ValueError(f"PDF has no extractable text layer: {rel}; OCR is not enabled")
        else:
            raw_text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
            if path.suffix.lower() == ".md" and raw_text.startswith("---\n"):
                _, head, raw_text = raw_text.split("---", 2)
                metadata = yaml.safe_load(head) or {}
                if not isinstance(metadata, dict):
                    raise ValueError(f"Invalid YAML front matter: {rel}")
            if path.suffix.lower() in {".html", ".htm"}:
                soup = BeautifulSoup(raw_text, "html.parser")
                title = soup.title.get_text(" ", strip=True) if soup.title else None
                for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "form", "aside"]):
                    tag.decompose()
                main = soup.find("main") or soup.find("article") or soup.body or soup
                blocks = []
                for tag in main.find_all(["h1", "h2", "h3", "p", "li"]):
                    value = tag.get_text(" ", strip=True)
                    if value:
                        blocks.append(("#" * int(tag.name[1]) + " " if tag.name.startswith("h") else "") + value)
                raw_text = "\n\n".join(blocks) if blocks else main.get_text(" ")
                if title:
                    metadata.setdefault("title", title)
            pages = [(None, clean(raw_text))]
        sidecar = path.with_name(path.name + ".meta.yaml")
        if sidecar.exists():
            supplied = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
            if not isinstance(supplied, dict):
                raise ValueError(f"Invalid metadata sidecar: {sidecar}")
            metadata.update(supplied)
        body = "\n\n".join(text for _, text in pages)
        if not body:
            raise ValueError(f"Document has no usable text: {rel}")
        status = str(metadata.get("status", "draft"))
        if status not in STATUSES:
            raise ValueError(f"Invalid status in {rel}: {status}")
        if status == "approved" and not metadata.get("verified_at"):
            raise ValueError(f"Approved document requires verified_at: {rel}")
        for key in ("published_at", "verified_at", "collected_at", "source_checked_at"):
            if metadata.get(key):
                date.fromisoformat(str(metadata[key]))
        source_url = metadata.get("source_url")
        if source_url and not str(source_url).startswith(("https://", "http://")):
            raise ValueError(f"Invalid source_url in {rel}")
        document_id = str(metadata.get("document_id") or uuid5(NAMESPACE, rel))
        title = str(metadata.get("title") or next((line.lstrip("# ") for line in body.splitlines() if line.strip()), path.stem))
        def optional_text(key: str) -> str | None:
            value = metadata.get(key)
            return str(value).strip() if value is not None and str(value).strip() else None
        for key in ("service", "software", "task_category", "procedure_service"):
            if metadata.get(key) is not None and not isinstance(metadata[key], str):
                raise ValueError(f"{key} must be text: {rel}")
        coverage = metadata.get("evidence_coverage")
        if coverage is None:
            coverage = {}
        if not isinstance(coverage, dict) or any(
            not isinstance(key, str) or not key.strip() or value not in ("full", "partial")
            for key, value in coverage.items()
        ):
            raise ValueError(f"evidence_coverage must map operations to full/partial: {rel}")

        def text_list(key: str) -> list[str]:
            value = metadata.get(key)
            if value is None:
                return []
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValueError(f"{key} must be a list of nonempty strings: {rel}")
            return list(dict.fromkeys(item.strip() for item in value))

        return Document(
            document_id=document_id, title=title, category=str(metadata.get("category", "uncategorized")),
            manufacturer=optional_text("manufacturer"), model=optional_text("model"),
            version=optional_text("version"), source_url=optional_text("source_url"),
            source_type=str(metadata.get("source_type", "local")),
            published_at=str(metadata["published_at"]) if metadata.get("published_at") else None,
            verified_at=str(metadata["verified_at"]) if metadata.get("verified_at") else None,
            collected_at=str(metadata["collected_at"]) if metadata.get("collected_at") else None,
            status=status, content_hash=sha256(body.encode("utf-8")).hexdigest(),
            source=rel, pages=pages,
            service=optional_text("service"), software=optional_text("software"),
            task_category=optional_text("task_category"),
            operations=text_list("operations"), search_fields=text_list("search_fields"),
            source_checked_at=str(metadata["source_checked_at"]) if metadata.get("source_checked_at") else None,
            procedure_service=optional_text("procedure_service"), evidence_coverage=coverage,
        )

    def load_all(self) -> list[Document]:
        by_hash: dict[str, Document] = {}
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in FORMATS:
                continue
            document = self.load(path)
            previous = by_hash.get(document.content_hash)
            if previous is None or (document.status == "approved" and previous.status != "approved"):
                by_hash[document.content_hash] = document
        return list(by_hash.values())


class Chunker:
    def __init__(self, max_chars: int = 1200):
        if max_chars < 100:
            raise ValueError("max_chars must be at least 100")
        self.max_chars = max_chars

    def split(self, document: Document) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        section_index = 0
        for page, body in document.pages:
            sections: list[tuple[str | None, list[str]]] = []
            heading: str | None = None
            paragraphs: list[str] = []
            for part in re.split(r"\n\s*\n", body):
                part = part.strip()
                if not part:
                    continue
                if re.match(r"^#{1,6}\s+", part):
                    if paragraphs:
                        sections.append((heading, paragraphs))
                    heading, paragraphs = part.splitlines()[0].lstrip("# ").strip(), []
                    rest = "\n".join(part.splitlines()[1:]).strip()
                    if rest:
                        paragraphs.append(rest)
                else:
                    paragraphs.append(part)
            if paragraphs:
                sections.append((heading, paragraphs))
            for section, parts in sections:
                current_section_index = section_index
                section_index += 1
                section_chunk_index = 0
                current = ""
                prefix = (f"{section}\n" if section else "")[: self.max_chars // 3]
                for part in parts:
                    if re.match(r"^(?:Ошибка|Код)\s+(?:(?:ФН|ККТ)\s+)?\d", part, re.IGNORECASE) and current:
                        chunks.append(self._make(
                            document, section, page, current, len(chunks),
                            current_section_index, section_chunk_index,
                        ))
                        section_chunk_index += 1
                        current = ""
                    # Keep short instruction steps together; split only oversized paragraphs.
                    pieces = [part[i:i + self.max_chars - len(prefix)] for i in range(0, len(part), self.max_chars - len(prefix))]
                    for piece in pieces:
                        candidate = (current + "\n\n" + piece).strip() if current else prefix + piece
                        if len(candidate) > self.max_chars and current:
                            chunks.append(self._make(
                                document, section, page, current, len(chunks),
                                current_section_index, section_chunk_index,
                            ))
                            section_chunk_index += 1
                            current = prefix + piece
                        else:
                            current = candidate
                if current:
                    chunks.append(self._make(
                        document, section, page, current, len(chunks),
                        current_section_index, section_chunk_index,
                    ))
        for index, chunk in enumerate(chunks):
            previous = chunks[index - 1] if index else None
            following = chunks[index + 1] if index + 1 < len(chunks) else None
            chunk.metadata.update({
                "previous_chunk_id": previous.id if previous else None,
                "next_chunk_id": following.id if following else None,
                "relation_to_previous": self._relation(
                    previous.metadata.get("chunk_role") if previous else None,
                    chunk.metadata.get("chunk_role"),
                ),
            })
        return chunks

    @staticmethod
    def _make(document: Document, section: str | None, page: int | None, text: str,
              ordinal: int, section_index: int, section_chunk_index: int) -> KnowledgeChunk:
        chunk_id = str(uuid5(NAMESPACE, f"{document.document_id}:{ordinal}"))
        metadata = {k: v for k, v in asdict(document).items() if k != "pages"}
        metadata.update({
            "section": section,
            "page": page,
            "chunk_id": chunk_id,
            "chunk_index": ordinal,
            "section_index": section_index,
            "section_chunk_index": section_chunk_index,
            "chunk_role": Chunker._role(section, text),
        })
        return KnowledgeChunk(chunk_id, text, section, page, metadata)

    @staticmethod
    def _role(section: str | None, text: str) -> str:
        label = (section or "").casefold().replace("ё", "е")
        if re.search(r"\bвопрос\b|симптом", label):
            return "question"
        if re.search(r"важн|огранич|предупреж|безопас|передать специалист", label):
            return "warning"
        if re.search(r"услови|перед началом|когда примен", label):
            return "condition"
        if (re.search(r"инструкц|порядок|процедур|диагност|что проверено|действ", label)
                or re.search(r"(?:^|\n)\s*(?:\d+[.)]|шаг\s+\d+)", text, re.I)):
            return "procedure"
        return "detail"

    @staticmethod
    def _relation(previous_role: str | None, current_role: str) -> str | None:
        if previous_role is None:
            return None
        if previous_role == "question":
            return "answers_question"
        if previous_role == "condition" and current_role == "procedure":
            return "procedure_for_condition"
        if previous_role == "procedure" and current_role == "warning":
            return "warning_for_procedure"
        if previous_role == "procedure":
            return "clarifies_procedure"
        return "follows"
