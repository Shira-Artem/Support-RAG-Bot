import sys

import pytest

from scripts.index_documents import main


def test_draft_index_requires_separate_collection(tmp_path, monkeypatch):
    (tmp_path / "draft.md").write_text("# Черновая инструкция\n\nПроверка связи с ОФД.", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["index_documents", "--docs-dir", str(tmp_path)])
    with pytest.raises(SystemExit, match="2"):
        main()
