"""Shared policy for operation compatibility and technical procedure scope."""
from __future__ import annotations

import re

from app.scope_policy import matches_scope_value


_CONTEXTUAL_OPERATIONS = {
    ("service_connection", "fiscalize"): "fiscalize_cash_register",
    ("billing", "check"): "manage_billing",
    ("peripheral_setup", "check"): "configure_peripheral",
    ("receipt_status", "status"): "inspect_fns_status",
    ("billing", "change"): "change_plan",
    ("billing", "close"): "get_closing_documents",
    ("billing", "search"): "get_renewal_invoice",
    ("billing", "return"): "request_refund",
    ("billing", "change_permissions"): "pay_debt",
    ("settings", "add"): "configure_settings",
    ("settings", "change"): "configure_settings",
    ("settings", "configure"): "configure_settings",
    ("integration", "check"): "integration_connect",
    ("integration", "configure"): "integration_connect",
    ("edo", "connect"): "exchange_edo_documents",
    ("product_catalog", "add"): "manage_product_catalog",
    ("period_close", "close"): "close_period",
    ("reconciliation", "reconcile"): "reconcile_counterparty",
    ("edo", "transmit"): "exchange_edo_documents",
    ("cash_list", "check"): "list_cash_registers",
    ("cash_list", "search"): "list_cash_registers",
    ("network_diagnostics", "check"): "diagnose_network",
    ("vat_usn", "check"): "check_vat_rules",
    ("cash_operations", "change"): "manage_shift",
    ("shift_management", "repeat_print"): "print_x_report",
    ("shift_management", "check"): "manage_shift",
    ("model_features", "check"): "check_model_features",
    ("fns_monitoring", "check"): "inspect_fns_indicators",
    ("ofd_connection", "check"): "connect_cash_register",
    ("ofd_connection", "connect"): "connect_cash_register",
    ("fiscal_format", "check"): "check_ffd",
    ("fiscal_drive", "replace"): "inspect_fiscal_drive",
    ("fiscal_drive", "check"): "inspect_fiscal_drive",
    ("sales", "return"): "issue_refund",
    ("refund", "return"): "issue_refund",
    ("cash_search", "search"): "search_cash_register",
    ("access", "assign"): "assign_role",
    ("document_discrepancy", "reconcile"): "record_discrepancy",
    ("correction_receipt", "correct"): "correct_receipt",
    ("receipt_search", "search"): "search_receipt",
    ("receipt_search", "check"): "search_receipt",
    ("receipt_search", "status"): "search_receipt",
    ("receipt_print", "repeat_print"): "repeat_print",
    ("cash_reports", "view_reports"): "view_cash_reports",
    ("fiscal_document_control", "check"): "diagnose_fiscal_document",
    ("fiscal_document_control", "diagnose"): "diagnose_fiscal_document",
    ("marking", "check"): "check_marking_code",
    ("marking", "diagnose"): "check_marking_code",
    ("tspiot", "diagnose"): "diagnose_tspiot",
    ("tspiot", "check"): "diagnose_tspiot",
    ("error_diagnosis", "diagnose"): "diagnose_error",
    ("error_diagnosis", "check"): "diagnose_error",
    ("receipt_transmission", "diagnose"): "check_transmission",
    ("receipt_transmission", "check"): "check_transmission",
    ("receipt_transmission", "status"): "check_transmission",
    ("receipt_transmission", "transmit"): "check_transmission",
    ("cash_list", "list"): "list_cash_registers",
    ("bank_statement", "list"): "list_bank_statements",
    ("integration", "connect"): "integration_connect",
}

_OPERATION_ALIASES = {
    "reconcile_document": "record_discrepancy",
    "configure_integration": "integration_connect",
    "check_integration_compatibility": "integration_connect",
    "connect": "integration_connect",
    "edit_user": "change_permissions",
    "edit_profile": "change",
    "update_profile": "change",
}

_QUERY_OPERATION_HINTS = {
    "archive_cash_register": ("архивир", "архив кас"),
    "connect_cash_register": ("подключ", "добавить касс"),
    "activate_tariff": ("активир", "ключ для касс", "тариф"),
    "print_x_report": ("x-отчет", "x отчет", "без гашения"),
    "check_model_features": ("что умеет", "характеристик", "возможност"),
    "inspect_fns_indicators": ("индикатор фнс", "запрет от фнс"),
    "import_bank_statements_via_intermediary": ("посредник", "другого банка"),
}


def query_operation_hints(query: str | None) -> set[str]:
    context = (query or "").casefold().replace("ё", "е")
    hints = set()
    for operation, terms in _QUERY_OPERATION_HINTS.items():
        for term in terms:
            if operation == "connect_cash_register" and term == "подключ":
                # A connected device is a state description, not a request to
                # connect it. Only imperative/infinitive action forms qualify.
                matched = bool(re.search(r"\bподключ(?:ить|ать|ите|айте|аем|ают|ает)\b", context))
            else:
                matched = term in context
            if matched:
                hints.add(operation)
                break
    return hints


def normalize_operation(operation: str, task_category: str | None = None,
                        context: str | None = None) -> str:
    context_folded = (context or "").casefold().replace("ё", "е")
    if task_category == "integration" and operation == "check" and any(
            term in context_folded for term in ("тестовом режиме", "облачную кассу", "облачной касс")):
        return "integration_connect"
    if task_category == "error_diagnosis" and operation == "reconcile" and any(
            term in context_folded for term in ("расхождени", "времени", "диагностик")):
        return "diagnose_error"
    if task_category == "bank_statement" and operation == "list":
        if any(term in context_folded for term in ("через посредника", "посредник", "банк-посредник", "другого банка", "не подключен к прямому обмену")):
            return "import_bank_statements_via_intermediary"
        if "расписан" in context_folded:
            return "schedule_bank_statement_import"
        if "файл" in context_folded:
            return "import_bank_statement_file"
    if task_category == "billing" and context_folded:
        if operation == "close" and "закрывающ" in context_folded:
            return "get_closing_documents"
        if operation == "check" and "акт свер" in context_folded:
            return "get_reconciliation_act"
        if operation == "check" and any(term in context_folded for term in ("договор", "срок действия", "окончан")):
            return "check_contract_status"
        if operation == "search" and any(term in context_folded for term in ("счет на продлен", "счёт на продлен", "продлен")):
            return "get_renewal_invoice"
        if operation == "change_permissions" and any(term in context_folded for term in ("задолж", "долг", "оплат")):
            return "pay_debt"
    contextual = _CONTEXTUAL_OPERATIONS.get((task_category, operation))
    return contextual or _OPERATION_ALIASES.get(operation, operation)


_COARSE_OPERATIONS = {"change", "check", "connect", "configure", "list", "search", "status"}
_BANK_STATEMENT_OPERATIONS = {
    "load_bank_statements", "list_bank_statements", "import_bank_statement_file",
    "import_bank_statements_via_intermediary", "schedule_bank_statement_import",
}


def reviewed_safe_diagnostic_section(metadata: dict,
                                     task_category: str | None = None) -> bool:
    """Recognize an approved, explicitly reviewed bank diagnostic fragment.

    This grants evidence from this section only; it does not turn diagnose
    into the article's loading/import operation.
    """
    operations = metadata.get("operations") or ()
    supported = {normalize_operation(str(item), "bank_statement") for item in operations}
    section = re.sub(r"\s+", " ", str(metadata.get("section") or "").casefold().replace("ё", "е")).strip()
    return (metadata.get("status") == "approved"
            and (task_category or metadata.get("task_category")) == "bank_statement"
            and metadata.get("task_category") == "bank_statement"
            and section == "безопасная диагностика"
            and bool(metadata.get("_operations_explicit", bool(operations)))
            and bool(supported) and supported <= _BANK_STATEMENT_OPERATIONS)


def diagnostic_version_compatible(query: str | None, metadata: dict) -> bool:
    """A stated client release must meet the reviewed feature's first release."""
    source = re.fullmatch(r"\d+(?:\.\d+){2,}", str(metadata.get("version") or ""))
    if not source:
        return True
    mentioned = re.findall(r"(?<!\d)\d+(?:\.\d+){2,}(?!\d)", query or "")
    minimum = tuple(int(part) for part in source.group().split("."))
    return all(tuple(int(part) for part in release.split(".")) >= minimum
               for release in mentioned)


def operation_compatibility(operation: str, metadata: dict,
                            query: str | None = None,
                            task_category: str | None = None) -> str:
    """Return match, unknown, or mismatch against reviewed operation metadata.

    Only explicit, reviewed operation declarations can establish a confirmed
    mismatch. Missing/derived operation labels remain unknown, while a client
    action that conflicts with an explicit procedure is never treated as a
    fallback opportunity.
    """
    raw_operations = metadata.get("operations") or ()
    explicit = bool(metadata.get("_operations_explicit", bool(raw_operations)) and raw_operations)
    if not raw_operations:
        return "unknown"
    category = metadata.get("task_category")
    supported = {normalize_operation(str(item), category) for item in raw_operations}
    if operation in {"unknown", "explain"}:
        hints = {normalize_operation(item, category, query)
                 for item in query_operation_hints(query)}
        if not hints:
            return "unknown"
        return "match" if supported & hints else "mismatch" if explicit else "unknown"
    if operation in _COARSE_OPERATIONS and not task_category:
        # A verb such as "search" in an unresolved task may describe what to
        # search for rather than an operation that conflicts with the source.
        # Query-level, specific action hints still take precedence.
        hints = {normalize_operation(item, category, query)
                 for item in query_operation_hints(query)}
        if hints:
            return "match" if supported & hints else "mismatch" if explicit else "unknown"
        return "unknown"
    expected = normalize_operation(operation, task_category or category, query)
    if expected in supported:
        return "match"
    if (operation == "diagnose"
            and reviewed_safe_diagnostic_section(metadata, task_category)):
        return "match" if diagnostic_version_compatible(query, metadata) else "mismatch"
    if (operation == "change_permissions" and query
            and re.search(r"уже\s+(?:за|созд|добавл)|существующ|отредактир", query, re.I)
            and supported & {"add_employee", "assign_role", "create_role", "configure_role"}):
        # These articles can establish a partial navigation route to an
        # existing user/role. They are not treated as complete permission
        # evidence by the separate coverage and grounding checks.
        return "match"
    return "mismatch" if explicit else "unknown"


def document_applicability(state, metadata: dict, *, technical: bool = False) -> list[str]:
    """Return missing/mismatched scope facts for a client-specific procedure.

    Topic relevance is decided elsewhere. This checks whether the current
    client has actually established the service/equipment described by a
    technically scoped source.
    """
    if not technical:
        return []
    missing: list[str] = []
    manufacturer = state.entity("manufacturer") or state.task_entity("manufacturer")
    equipment = state.entity("equipment") or state.task_entity("equipment")
    route = state.routing_service or state.task_entity("ofd")
    model = str(metadata.get("model") or "")
    # Numeric model designations are product-specific; a manufacturer-wide
    # article can apply when the manufacturer is confirmed without a model.
    model_is_specific = bool(re.search(r"\d", model))
    service = str(metadata.get("service") or metadata.get("procedure_service") or "")
    confirmed_service = str(route or state.entity("service") or "")
    service_matches = bool(service and confirmed_service and
                           matches_scope_value(service, confirmed_service))
    hardware_families = {"device", "fiscal_drive", "network", "network_diagnostics",
                         "ofd_connection", "error_diagnosis", "receipt_transmission",
                         "fiscal_document_control", "fiscal_format", "marking"}
    hardware_scoped = (str(metadata.get("task_category") or "") in hardware_families
                       or model_is_specific)
    if metadata.get("manufacturer") and hardware_scoped and not manufacturer and not service_matches:
        missing.append("equipment")
    if model_is_specific and not equipment and manufacturer:
        missing.append("model")
    if (metadata.get("service") or metadata.get("procedure_service")) and hardware_scoped and not route and not manufacturer:
        missing.append("service")
    return list(dict.fromkeys(missing))
