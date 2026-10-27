"""Evidence-bound task/operation projection shared by Understanding and retrieval.

The resolver reads the current client utterance, never a retrieved document.
It recognizes only unambiguous task/action pairs.  Unknowns remain unknown and
the existing retrieval vocabulary handles requests outside this small core.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TaskOperation:
    task_category: str | None
    operation: str
    intent: str
    mode: str  # information | diagnostic | action | unknown
    reason: str


def _has(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, re.I))


def resolve_task_operation(text: str, *, operation: str = "unknown",
                           intent: str = "unknown") -> TaskOperation:
    """Resolve explicit semantics without asserting a vendor, model or outcome.

    The patterns describe fiscal support task families already present in
    metadata and retrieval. They do not grant applicability or safety.
    """
    s = text.casefold().replace("ё", "е")
    def result(task: str | None, op: str, domain: str, mode: str, why: str):
        return TaskOperation(task, op, domain, mode, why)

    # A reported failure has priority over a generic request for instructions.
    # A code is diagnostic even when the model calls the turn an explanation.
    error = _has(s, r"\bошиб\w*|\bсбо\w*|\bфн\s*[-№#]?\s*\d{1,3}\b")
    if _has(s, r"\b(?:статус|состояни\w*|результат)\b") and _has(s, r"\bфнс\b") and _has(s, r"\bчек\w*\b"):
        return result("receipt_status", "status", "receipt", "information", "receipt_fns_status")
    if _has(s, r"\b(?:частичн\w*\s+)?возврат\w*\b|\bвернут\w*\b") and _has(s, r"\b(?:покупател\w*|чек\w*|товар\w*|сумм\w*)\b"):
        return result("refund", "return", "receipt", "action", "customer_refund")
    if _has(s, r"\bфискализац\w*\b|\bфискализир\w*\b"):
        return result("service_connection", "fiscalize", "device", "action", "fiscalization")
    if _has(s, r"\bфн\b") and _has(s, r"\bблокир\w*|\bзаблокир\w*"):
        return result("fiscal_drive", "check", "fiscal_drive", "diagnostic", "fiscal_drive_block")
    if _has(s, r"\b(?:задолж\w*|долг\w*|оплаченн\w*\s+период\w*)\b") and _has(s, r"\b(?:оплат\w*|сервис\w*|обслуживан\w*|касс\w*|счет\w*)\b"):
        return result("billing", "check", "billing", "diagnostic", "billing_status")
    if (_has(s, r"\b(?:api|апи|интеграц\w*)\b") and _has(s, r"\b(?:провер\w*|тестир\w*|запрос\w*|не\s+появ\w*|не\s+формир\w*)\b")):
        return result("integration", "check", "unknown", "diagnostic", "integration_check")
    if _has(s, r"\bподключ\w*\b") and _has(s, r"\b1[сc]\b"):
        return result("integration", "connect", "unknown", "action", "software_integration_connection")
    if _has(s, r"\b(?:сканер\w*|штрихкод\w*)\b") and _has(s, r"\b(?:подключ\w*|работ\w*|считыва\w*)\b"):
        return result("peripheral_setup", "check", "device", "diagnostic", "peripheral_check")
    if _has(s, r"\b(?:маркиров\w*|маркированн\w*)\b") and (error or _has(s, r"\bне\s+(?:получа\w*|проход\w*|прода\w*)")):
        return result("marking", "diagnose", "marking", "diagnostic", "marking_failure")
    if _has(s, r"\b(?:время|дата|часы)\b") and _has(s, r"\b(?:неправильн\w*|некорректн\w*|расхожд\w*|не\s+совпад\w*)"):
        return result("error_diagnosis", "diagnose", "unknown", "diagnostic", "clock_discrepancy")
    if error:
        return result("error_diagnosis", "diagnose", "unknown", "diagnostic", "reported_error")
    if _has(s, r"\b(?:не\s+поступ\w*|не\s+переда\w*|не\s+отправ\w*|перестал\w*\s+переда\w*)") and _has(s, r"\bчек\w*|\bдокумент\w*"):
        return result("receipt_transmission", "transmit" if operation == "transmit" else "diagnose",
                      "receipt", "diagnostic", "receipt_transmission_failure")
    if _has(s, r"\b(?:добав\w*|созда\w*)\s+(?:нов\w*\s+)?(?:сотрудник\w*|пользовател\w*)"):
        return result("access", "add_employee", "access", "action", "add_employee")
    if _has(s, r"\b(?:ффд|формат\w*\s+фискальн\w*\s+документ\w*)") and _has(s, r"\b(?:перейти|переход\w*|измен\w*|провер\w*)"):
        return result("fiscal_format", "check", "unknown", "information", "fiscal_format_check")
    if _has(s, r"\b(?:выписк\w*|директбанк|directbank)\b") and _has(s, r"\b(?:не\s+загружа\w*|перестал\w*|ошиб\w*)"):
        return result("bank_statement", "diagnose", "bank_statement", "diagnostic", "statement_failure")
    return result(None, operation, intent, "information" if operation == "explain" else
                  "diagnostic" if operation == "diagnose" else
                  "action" if operation not in {"unknown", "search", "status"} else "unknown",
                  "no_unique_explicit_task")
