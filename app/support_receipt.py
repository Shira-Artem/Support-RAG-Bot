"""Nonsecret startup identity for the internal API process."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess


def write_receipt():
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    files = [*sorted((root / 'app').glob('*.py')), root / 'scripts/run_support_api.py']
    receipt = {'pid': os.getpid(), 'started_at': datetime.now(timezone.utc).isoformat(), 'commit': commit,
               'provider': os.getenv('LLM_PROVIDER'), 'collection': os.getenv('QDRANT_COLLECTION'),
               'source_sha256': {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest() for p in files}}
    output = root / '.local/api-runtime.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
