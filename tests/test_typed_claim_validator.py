from experiments.typed_claim_validator.validator import (
    Claim, ClaimKind, Decision, Evidence, Risk, Scope, Verdict, coverage,
    validate_claim, validate_ledger,
)


def claim(text, **kwargs):
    return Claim("c", text, 0, len(text), kwargs.pop("kind", ClaimKind.FACT), **kwargs)


def evidence(clause, **kwargs):
    return Evidence("doc-1", "approved", clause, clause, **kwargs)


def test_exact_clause_and_provenance():
    text = "Сервис хранит журнал событий."
    assert validate_claim(claim(text), text, evidence(text)).verdict == Verdict.SUPPORTED
    assert validate_claim(claim(text), text, None).reason == "approved_clause_missing"
    assert validate_claim(claim(text), text, Evidence("doc-1", "draft", text, text)).reason == "source_not_approved"
    assert validate_claim(claim(text), text, Evidence("doc-1", "approved", text, "other")).reason == "clause_not_in_approved_source"


def test_scope_numbers_and_ui():
    text = "Версия 2.4 поддерживает режим."
    assert validate_claim(claim(text, scope=Scope(service="Alpha")), text,
                          evidence(text, scope=Scope(service="Beta"))).verdict == Verdict.CONTRADICTED
    assert validate_claim(claim(text, scope=Scope(service="Alpha")), text,
                          evidence(text)).reason == "service_scope_unknown"
    assert validate_claim(claim("Версия 2.5",), "Версия 2.5", evidence(text)).reason == "number_not_in_clause:2.5"
    assert validate_claim(claim("Откройте «Панель»", kind=ClaimKind.UI,
                                ui_labels=("Панель",), action="Откройте", object="Панель"),
                          "Откройте «Панель»", evidence("Откройте «Журнал»")).reason.startswith("ui_label_not_in_clause")


def test_action_relation_and_risk_constraints():
    text = "Измените настройки подключения."
    c = claim(text, kind=ClaimKind.ACTION, action="Измените", object="настройки подключения",
              risk=Risk.SETTINGS, changes_state=True)
    assert validate_claim(c, text, evidence(text)).reason == "risk_constraints_not_declared"
    c = claim(text, kind=ClaimKind.ACTION, action="Измените", object="настройки подключения",
              risk=Risk.SETTINGS, changes_state=True, prerequisites=("доступ администратора",))
    assert validate_claim(c, text, evidence(text)).reason == "condition_not_established:доступ администратора"
    ev = evidence(text, satisfied_prerequisites=("доступ администратора",))
    assert validate_claim(c, text, ev).verdict == Verdict.SUPPORTED
    assert validate_claim(claim("Откройте журнал", kind=ClaimKind.ACTION,
                                action="Откройте", object="журнал"), "Откройте журнал",
                          evidence("Откройте настройки; журнал доступен отдельно.")).verdict != Verdict.SUPPORTED


def test_polarity_dependency_and_coverage():
    text = "Функция недоступна."
    assert validate_claim(claim(text, negated=True), text, evidence("Функция доступна.")).reason == "polarity_requires_semantic_review"
    c = claim("Откройте журнал", kind=ClaimKind.ACTION, depends_on=("first",))
    assert validate_claim(c, c.quote, None).reason == "dependency_missing:first"
    failed = Decision("first", Verdict.UNSUPPORTED, "test")
    assert validate_claim(c, c.quote, None, {"first": failed}).reason == "dependency_not_supported:first"
    basic = claim("Факт")
    assert coverage("Факт и другой факт", [basic], [(0, 4), (7, 12)])["certified"] is False
    assert coverage("Факт", [basic], [(0, 4)])["certified"] is True
    assert coverage("Факт", [basic], None)["certified"] is False


def test_incomplete_relation_cannot_use_word_overlap():
    text = "Назначьте роль пользователю."
    c = claim(text, kind=ClaimKind.ACCESS, action="Назначьте", object="роль", risk=Risk.ACCESS)
    ev = evidence("Назначьте права администратору. Роль пользователя создаётся отдельно.")
    assert validate_claim(c, text, ev).verdict != Verdict.SUPPORTED
    assert validate_claim(c, text, evidence(text)).reason == "action_risk_or_state_change_unknown"


def test_ledger_requires_certified_coverage():
    text = "Сервис хранит журнал событий."
    c = claim(text)
    unverified = validate_ledger(text, [c], {"c": evidence(text)}, None)
    assert unverified["decisions"]["c"].verdict == Verdict.SUPPORTED
    assert unverified["safe_to_publish"] is False
    verified = validate_ledger(text, [c], {"c": evidence(text)}, [(0, len(text))])
    assert verified["safe_to_publish"] is True
