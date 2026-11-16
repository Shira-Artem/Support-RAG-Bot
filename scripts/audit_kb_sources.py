"""Probe HTTP availability only; this does not verify source content or claims.

The probe is deliberately opt-in and writes to a separate artifact so it cannot
replace the curated source-review evidence ledger.
"""

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml


ROOT = Path.cwd()
DEFAULT_OUTPUT = Path("reports/kb_review_b2_quality/source_access_probe.csv")


def read_sources():
    urls = {}
    for path in (ROOT / "data/knowledge").rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
            if not text.startswith("---\n"):
                continue
            metadata = yaml.safe_load(text.split("---\n", 2)[1]) or {}
            url = metadata.get("source_url")
            if url:
                urls.setdefault(str(url), []).append(str(path.relative_to(ROOT)))
        except (OSError, UnicodeError, IndexError, yaml.YAMLError):
            continue
    return sorted(urls.items())


def probe(item, timeout):
    url, paths = item
    checked_at = datetime.now(timezone.utc).date().isoformat()
    request = Request(url, headers={"User-Agent": "Support-RAG-Bot KB source availability probe"})
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read(1024)
            access = "http_reachable_content_unverified"
            evidence = f"HTTP {response.status}; first 1024 bytes only, page content/claims not reviewed"
    except HTTPError as error:
        access = "http_error_content_unverified"
        evidence = f"HTTP {error.code}; page content/claims not reviewed"
    except (URLError, TimeoutError, OSError) as error:
        access = "request_failed_unverified"
        evidence = f"{type(error).__name__}: {str(error)[:160]}"
    return {
        "url": url,
        "paths_count": len(paths),
        "access": access,
        "checked_at": checked_at,
        "access_evidence": evidence,
        "claims_verified": "unverified: transport probe only",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="perform HTTP availability requests")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="new probe CSV path (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=5.0, help="per-URL timeout in seconds")
    parser.add_argument("--workers", type=int, default=8, help="maximum concurrent requests")
    args = parser.parse_args()

    if not args.run:
        parser.print_help()
        return 0
    output = args.output
    if output.resolve() == (ROOT / "reports/kb_review_b2_quality/source_review.csv").resolve():
        parser.error("refusing to overwrite curated source_review.csv; choose a separate output file")
    if output.exists():
        parser.error(f"output already exists; choose a new path: {output}")
    if args.timeout <= 0 or args.workers <= 0:
        parser.error("--timeout and --workers must be positive")

    sources = read_sources()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda item: probe(item, args.timeout), sources))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"probed={len(rows)} output={output}; HTTP reachability only, claims remain unverified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
