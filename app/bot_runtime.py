"""Safe startup receipt from the objects actually used by the Telegram worker."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def write_runtime_receipt(settings, rag, path: Path | None = None) -> dict:
    store = getattr(getattr(rag, 'retriever', None), 'store', None)
    collection = store.collection if store else None
    points = store.client.get_collection(collection).points_count if store else len(rag.chunks)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    sources = [ROOT/'bot.py', *sorted((ROOT/'app').glob('*.py'))]
    hashes = {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sources}
    receipt = dict(pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat(),
        backend=type(rag).__name__, collection=collection, points=points,
        demo=rag.retriever.demo if store else True,
        provider=settings.llm_provider,
        model=settings.groq_model if settings.llm_provider == 'groq' else settings.openrouter_model,
        reasoning_effort=settings.groq_reasoning_effort if settings.llm_provider == 'groq' else None,
        commit=head, source_sha256=hashes, phase='runtime_initialized_before_polling')
    target = path or ROOT/'.local/bot-runtime.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)
    return receipt
