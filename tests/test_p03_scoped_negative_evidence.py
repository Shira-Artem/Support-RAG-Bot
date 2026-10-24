"""P0.3: an evidence gap is not proof of a negative capability claim."""

from pathlib import Path

import pytest

from app.dialogue_state import DialogueManager, DialogueState
from app.response_grounding import claim_supported
from app.retrieval_pipeline import _unconfirmed_search_parameters


RECEIPTS = Path("data/knowledge/platformaofd/ofd/lkk-receipt-search.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("question", [
    "Как найти чек по номеру ФД в Платформе ОФД?",
    "Платформа ОФД: где найти чек по ФД?",
    "Можно отыскать чек по ФП в Платформе ОФД?",
])
def test_documented_receipt_identifiers_do_not_acquire_false_gap(question):
    state = DialogueManager().advance(DialogueState(), question, 1)
    assert state.operation == "search"
    assert _unconfirmed_search_parameters(state, RECEIPTS) == []


def test_unconfirmed_identifier_stays_unconfirmed():
    state = DialogueManager().advance(
        DialogueState(), "Можно найти чек по номеру ФН в Платформе ОФД?", 1)
    assert _unconfirmed_search_parameters(state, RECEIPTS)
    assert not claim_supported("ФН можно использовать как фильтр чеков.", RECEIPTS)


@pytest.mark.parametrize("source,unsupported,supported", [
    (
        "Поиск выписок. Доступен фильтр по номеру счёта. "
        "ИНН не подтверждён как фильтр выписок. Не подменяйте ИНН номером счёта.",
        "Номер счёта не подтверждён как фильтр выписок.",
        "ИНН не подтверждён как фильтр выписок.",
    ),
    (
        "Поиск документов. Можно отбирать документы по статусу. "
        "Дата отправки не подтверждена как фильтр документов. "
        "Не подменяйте дату отправки статусом.",
        "Статус не подтверждён как фильтр документов.",
        "Дата отправки не подтверждена как фильтр документов.",
    ),
])
def test_negative_boundary_is_scoped_to_field_and_operation(source, unsupported, supported):
    assert not claim_supported(unsupported, source)
    assert claim_supported(supported, source)


def test_no_source_field_does_not_prove_absence_of_feature():
    source = "Выписки можно искать по номеру счёта."
    assert not claim_supported("Фильтр по ИНН недоступен для выписок.", source)
    assert not claim_supported("Поиск выписок по ИНН поддерживается.", source)
