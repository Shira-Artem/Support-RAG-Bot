"""Bounded real-Groq LIVE gate for P0.1 dialogue continuations."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from b2_2d_bounded_live_20261105 import CASES, run

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "reports/b2_2d_20261105/expanded_live_manifest_20261106.json")
                  .read_text(encoding="utf-8"))
CASES.update(manifest["cases"])
CASES.update({
    "P01_aQsi_paraphrase": [
        "На физической кассе aQsi DataMatrix сканируется плохо, обычный штрихкод читается. Что проверить сначала?",
        "Сканер не из комплекта. Имеет смысл сразу переключить USB-режим?",
    ],
    "P01_FN_paraphrase": [
        "На Эвотор выскочила ошибка ФН 234. Обязательно покупать новый накопитель?",
        "Вижу, что часы на кассе выставлены неверно. Как это связано с ошибкой и что теперь делать?",
    ],
})
args = SimpleNamespace(
    cases="N03,N04,P01_aQsi_paraphrase,P01_FN_paraphrase",
    output="reports/b2_2d_20261106/p01_live_final.json",
    pause=12,
    runtime_dir=None,
)
with patch("app.llm_client._MAX_GROQ_429_RETRIES", 0):
    asyncio.run(run(args))
