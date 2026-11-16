"""Read-only offline validation of KB review candidates against the current KB."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.knowledge import Chunker, DocumentLoader  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "reports/kb_review_b2_quality/candidate_validation.csv",
        help="CSV registry containing a path column (default: candidate_validation.csv)",
    )
    args = parser.parse_args()
    registry = args.registry if args.registry.is_absolute() else ROOT / args.registry

    with registry.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or "path" not in rows[0]:
        print(f"ERROR: empty registry or missing path column: {registry}", file=sys.stderr)
        return 2

    kb_docs = DocumentLoader(ROOT / "data/knowledge").load_all()
    candidate_docs = []
    errors: list[str] = []
    warnings: list[str] = []
    chunk_counts: Counter[str] = Counter()

    for row in rows:
        relative = Path(row["path"])
        path = relative if relative.is_absolute() else ROOT / relative
        display_path = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
        try:
            raw = path.read_text(encoding="utf-8")
            if not raw.startswith("---\n"):
                raise ValueError("missing YAML front matter")
            metadata = yaml.safe_load(raw.split("---", 2)[1])
            if not isinstance(metadata, dict):
                raise ValueError("front matter is not a mapping")

            doc = DocumentLoader(path.parent).load(path)
            chunks = Chunker().split(doc)
            candidate_docs.append((display_path, doc, chunks, metadata))
            chunk_counts[display_path] = len(chunks)

            if doc.status != "draft":
                errors.append(f"{display_path}: status={doc.status!r}, expected 'draft'")
            if doc.verified_at is not None:
                errors.append(f"{display_path}: verified_at must be null for an unapproved candidate")
            if not doc.source_url or not doc.source_url.startswith(("https://", "http://")):
                errors.append(f"{display_path}: source_url is missing or not HTTP(S)")
            if not chunks or any(not chunk.text.strip() for chunk in chunks):
                errors.append(f"{display_path}: no chunks or an empty chunk")
            if set(doc.evidence_coverage) - set(doc.operations):
                errors.append(f"{display_path}: evidence_coverage contains an operation absent from operations")
            if metadata.get("requires_sme_review") is not True:
                warnings.append(f"{display_path}: requires_sme_review is not explicitly true in front matter")
        except Exception as exc:  # Continue auditing the remaining candidates.
            errors.append(f"{display_path}: {type(exc).__name__}: {exc}")

    all_docs = kb_docs + [doc for _, doc, _, _ in candidate_docs]
    id_counts = Counter(doc.document_id for doc in all_docs)
    hash_counts = Counter(doc.content_hash for doc in all_docs)
    for path, doc, _, _ in candidate_docs:
        if id_counts[doc.document_id] > 1:
            errors.append(f"{path}: duplicate document_id {doc.document_id!r} across KB/candidates")
        if hash_counts[doc.content_hash] > 1:
            errors.append(f"{path}: duplicate content_hash across KB/candidates")

    total_chunks = sum(len(chunks) for _, _, chunks, _ in candidate_docs)
    print(
        f"registry={len(rows)} candidates_loaded={len(candidate_docs)} "
        f"main_kb_loaded={len(kb_docs)} chunks={total_chunks} "
        f"unique_ids={len(id_counts) == len(all_docs)} "
        f"unique_content_hashes={len(hash_counts) == len(all_docs)} "
        f"errors={len(errors)} warnings={len(warnings)}"
    )
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
