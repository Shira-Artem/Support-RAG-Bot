import io
import json

from scripts.run_telegram_equivalent_live import CASES, terminal_record


def test_terminal_capture_survives_cp1251_with_narrow_no_break_space():
    binary = io.BytesIO()
    legacy_console = io.TextIOWrapper(binary, encoding="cp1251", errors="strict")

    terminal_record({"answer": "Проверка — 1\u202f234 ₽"}, stream=legacy_console)
    legacy_console.flush()

    line = binary.getvalue().decode("cp1251").strip()
    captured = json.loads(line)
    assert captured["answer"] == "Проверка — 1\u202f234 ₽"


def test_harness_includes_high_risk_archive_close_control():
    assert CASES["exp2_unsafe_close_fn_archive"] == ["Закройте архив ФН"]
