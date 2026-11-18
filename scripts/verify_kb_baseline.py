"""Verify the saved KB baseline against Git history and the current audit inventory.

Read-only: this script does not rewrite inventories, contact external services,
or access runtime/vector-store components.
"""
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/kb_review_b2_quality"


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def git_blob(commit, path):
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def fail(message):
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main():
    manifest_path = REPORTS / "baseline_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline_path = ROOT / manifest["artifact"]
    baseline_bytes = baseline_path.read_bytes()
    observed_artifact_hash = hashlib.sha256(baseline_bytes).hexdigest()
    if observed_artifact_hash != manifest["artifact_sha256"]:
        fail("saved baseline artifact hash differs from manifest")

    baseline = read_csv(baseline_path)
    if len(baseline) != manifest["baseline_row_count"]:
        fail("baseline row count differs from manifest")
    if len({row["path"] for row in baseline}) != len(baseline):
        fail("baseline contains duplicate paths")

    source_commit = manifest["source_snapshot_commit"]
    matches_source = 0
    for row in baseline:
        blob = git_blob(source_commit, row["path"])
        if hashlib.sha256(blob).hexdigest() != row["sha256"]:
            fail(f"baseline content does not match source snapshot: {row['path']}")
        matches_source += 1
    if matches_source != manifest["sha256_rows_matching_source_snapshot_commit"]:
        fail("source snapshot match count differs from manifest")

    introduced_commit = manifest["baseline_artifact_introduced_by_commit"]
    committed_artifact = git_blob(introduced_commit, manifest["artifact"])
    if hashlib.sha256(committed_artifact).hexdigest() != observed_artifact_hash:
        fail("baseline artifact differs from the artifact-introducing commit")

    current = read_csv(REPORTS / "audit_inventory.csv")
    baseline_by_path = {row["path"]: row for row in baseline}
    current_by_path = {row["path"]: row for row in current}
    added = sorted(current_by_path.keys() - baseline_by_path.keys())
    removed = sorted(baseline_by_path.keys() - current_by_path.keys())
    shared = baseline_by_path.keys() & current_by_path.keys()
    id_changes = sorted(
        path for path in shared
        if baseline_by_path[path]["document_id"] != current_by_path[path]["document_id"]
    )
    same_hash = sum(
        baseline_by_path[path]["sha256"] == current_by_path[path]["sha256"]
        for path in shared
    )
    transitions = Counter(
        f"{baseline_by_path[path]['status']}->{current_by_path[path]['status']}"
        for path in shared
        if baseline_by_path[path]["status"] != current_by_path[path]["status"]
    )
    statuses = Counter(row["status"] for row in current)

    expected = manifest
    observed = {
        "current_card_count": len(current),
        "current_paths_not_in_baseline": len(added),
        "baseline_paths_missing_current": len(removed),
        "document_id_changes": len(id_changes),
        "current_sha256_matching_baseline": same_hash,
        "current_sha256_differing_from_baseline": len(shared) - same_hash,
        "current_statuses": dict(statuses),
    }
    for key, value in observed.items():
        if expected.get(key) != value:
            fail(f"{key}: manifest={expected.get(key)!r}, observed={value!r}")

    expected_transitions = {
        "approved_to_draft": transitions["approved->draft"],
        "draft_to_approved": transitions["draft->approved"],
    }
    if expected.get("status_transitions") != expected_transitions:
        fail(
            "status_transitions: "
            f"manifest={expected.get('status_transitions')!r}, observed={expected_transitions!r}"
        )

    print(
        "PASS: baseline artifact hash verified; "
        f"{matches_source}/{len(baseline)} historical file hashes match {source_commit}; "
        f"{len(current)} current paths, {same_hash} unchanged hashes, "
        f"{len(shared) - same_hash} changed hashes, {len(id_changes)} ID changes, "
        f"status transitions={dict(transitions)}."
    )


if __name__ == "__main__":
    main()
