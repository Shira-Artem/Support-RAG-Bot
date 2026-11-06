from pathlib import Path

import pytest

from app.source_first_service import _independent_information_list, _sections


ROOT = Path(__file__).resolve().parents[1] / "data" / "knowledge"


@pytest.mark.parametrize(("source", "heading"), [
    ("1c/edo/connect-1c-edo.md", "Что уточнить перед инструкцией"),
    ("1c/bank/acquiring-patent-tax.md", "Что уточнить"),
    ("1c/taxes/ens-automatic-data.md", "Уточняющие вопросы"),
])
def test_approved_information_lists_are_not_technical_sequences(source, heading):
    content = (ROOT / source).read_text(encoding="utf-8")
    assert "status: approved" in content.split("---", 2)[1]
    body = dict(_sections(content))[heading]
    assert _independent_information_list(heading, body, "Какие ещё параметры подготовить?", "information")


@pytest.mark.parametrize("body", [
    "1. Откройте настройки.\n2. Затем выберите кассу.",
    "1. Проверьте подключение.\n2. Если есть ошибка, сообщите код.",
    "1. Модель кассы.\n2. Удалите документ.",
    "1. Модель кассы.\n2. Активируйте настройку.",
    "1. Модель кассы.\n2. Сбросить настройки.",
    "1. Версия программы.\nПроведите документ.",
])
def test_actions_and_dependencies_are_not_information_lists(body):
    assert not _independent_information_list("Что уточнить", body,
                                             "Какие параметры подготовить?", "information")


def test_information_list_requires_question_and_request_type():
    body = "1. Версия программы.\n2. Модель кассы."
    assert not _independent_information_list("Что уточнить", body, "Что проверить?", "diagnosis")
