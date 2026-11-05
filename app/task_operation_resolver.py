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
                           intent: str = "unknown", subject: str | None = None) -> TaskOperation:
    """Resolve explicit semantics without asserting a vendor, model or outcome.

    The patterns describe fiscal support task families already present in
    metadata and retrieval. They do not grant applicability or safety.
    """
    s = text.casefold().replace("ё", "е")
    def result(task: str | None, op: str, domain: str, mode: str, why: str):
        return TaskOperation(task, op, domain, mode, why)

    # A typed control-code namespace is more specific than the surrounding
    # receipt/OFD vocabulary. Preserve an explanatory speech act when present.
    if _has(s, r"\bфлк\s*[-№#:]?\s*\d{2,5}\b"):
        op = operation if operation in {"explain", "check", "status", "diagnose"} else "diagnose"
        return result("fiscal_document_control", op, "receipt",
                      "information" if op == "explain" else "diagnostic", "typed_fiscal_control_code")

    # Identify the technical subject before generic error/connect labels.
    # These projections never assert client equipment or source applicability.
    if (_has(s, r'\b(?:интернет\w*|связ\w*|сеть|сети)\b')
            and _has(s, r'\bsim\b|сим[ -]?карт|мобильн\w*|wi[ -]?fi')
            and not _has(s, r'\b(?:офд|фнс|оисм)\b')
            and operation in {'unknown','explain','check','diagnose'}):
        return result('network_diagnostics', 'check', 'network', 'diagnostic', 'network_transport_subject')
    if (_has(s, r'\b(?:выписк\w*)\b') and _has(s, r'\bфайл\w*\b')
            and _has(s, r'\b1[сc]\b|директбанк|directbank|\bбанк\w*\b')
            and _has(s, r'загруз\w*|импорт\w*')
            and operation in {'unknown','explain','connect','list','search','diagnose'}
            and not _has(s, r'ошиб\w*|не\s+загружа\w*|перестал\w*')):
        return result('bank_statement', 'list', 'bank_statement', 'action', 'bank_file_import_subject')
    if (_has(s, r'акт\w*\s+сверк\w*|свер\w*\s+с\s+контрагент\w*')
            and _has(s, r'с\s+чего\s+начать|начать|подготов\w*|провер\w*')
            and operation in {'unknown','explain','reconcile','check'}):
        return result('reconciliation', 'reconcile', 'general', 'diagnostic', 'reconciliation_preparation')
    if (_has(s, r'\bрол\w*\b') and _has(s, r'прав\w*|просмотр\w*|редактир\w*')
            and operation == 'configure'):
        return result('access', 'create_role', 'access', 'action', 'role_configuration_subject')

    # Recording a bank entry in accounting software is not issuing a customer
    # refund. Domain evidence must precede the generic word 'return'.
    accounting = _has(s, r"\b1[сc]\b|\bбухгалтер\w*")
    bank_entry = (_has(s, r"\bбанк\w*|\bэквайринг\w*")
                  and _has(s, r"\bсписа\w*|\bпоступлен\w*|\bвыписк\w*|расчетн\w*\s+счет"))
    if accounting and bank_entry and _has(s, r"\bвозврат\w*"):
        return result("bank_statement", operation, "bank_statement",
                      "information" if operation in {"unknown", "explain"} else "diagnostic",
                      "accounting_bank_entry_domain")

    # A qualified business document is not a fiscal receipt. Keep the user's
    # read-only action separate from document signing/sending, for every EDO.
    edo_subject = _has(s, r"\b(?:эдо|упд|накладн\w*)\b|\b(?:электронн\w*|входящ\w*|исходящ\w*|отправленн\w*)\s+документ\w*")
    if edo_subject and not _has(s, r"\b(?:чек\w*|офд|фискальн\w*)\b"):
        if operation == "connect":
            return result("edo", "connect", "delivery_document", "action", "edo_connection_domain")
        if _has(s, r"\b(?:статус\w*|состояни\w*)\b") and operation in {"unknown", "status", "check", "search", "explain"}:
            return result("edo", "status", "delivery_document", "information", "electronic_document_status")
        if operation in {"search", "check", "status", "diagnose"}:
            return result("edo", operation, "delivery_document", "diagnostic", "electronic_document_lookup")

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
    account_subject = _has(s, r"\b(?:банковск\w*|расчетн\w*)\s+сч[её]т\w*\b")
    statement_subject = _has(s, r"\bвыписк\w*\b")
    bank_context = (_has(s, r"\b(?:директбанк|directbank|банк\w*\s+обмен\w*)\b")
                    or (statement_subject and _has(s, r"\bбанк\w*\b")))
    bank_failure = _has(s, r"\b(?:не\s+\w{0,16}(?:отображ\w*|вид\w*|появ\w*|доступ\w*|загружа\w*|приход\w*)|"
                           r"отсутств\w*|пропал\w*|исчез\w*|сбо\w*|ошиб\w*|перестал\w*)\b")
    if bank_context and (account_subject or statement_subject):
        if bank_failure:
            return result("bank_statement", "diagnose", "bank_statement", "diagnostic",
                          "bank_account_or_statement_failure")
        if _has(s, r"\b(?:подключ\w*|настро\w*)\b") and not statement_subject:
            return result("integration", "connect", "unknown", "action",
                          "bank_exchange_setup")
    if (_has(s, r"\b(?:api|апи|интеграц\w*)\b") and _has(s, r"\b(?:провер\w*|тестир\w*|запрос\w*|не\s+появ\w*|не\s+формир\w*)\b")):
        return result("integration", "check", "unknown", "diagnostic", "integration_check")
    if _has(s, r"\bподключ\w*\b") and _has(s, r"\b1[сc]\b"):
        return result("integration", "connect", "unknown", "action", "software_integration_connection")
    if _has(s, r"\b(?:сканер\w*|штрихкод\w*)\b") and _has(s, r"\b(?:подключ\w*|работ\w*|считыва\w*)\b"):
        return result("peripheral_setup", "check", "device", "diagnostic", "peripheral_check")
    if _has(s, r"\b(?:маркиров\w*|маркированн\w*|марка|марку|марки)\b") and (error or _has(s, r"\bне\s+(?:получа\w*|проход\w*|прода\w*)|\bне\s+(?:был\w*\s+)?провер\w*")):
        return result("marking", "diagnose", "marking", "diagnostic", "marking_failure")
    if _has(s, r"\b(?:время|дата|часы)\b") and _has(s, r"\b(?:неправильн\w*|некорректн\w*|расхожд\w*|не\s+совпад\w*)"):
        return result("error_diagnosis", "diagnose", "unknown", "diagnostic", "clock_discrepancy")
    if error:
        return result("error_diagnosis", "diagnose", "unknown", "diagnostic", "reported_error")
    # A receipt problem at the OFD boundary is a transmission diagnostic even
    # when the provider labels the intent as a fiscal drive or device. Use the
    # subject, destination, and diagnostic context; never infer a vendor/model.
    receipt_at_ofd = (_has(s, r"\b(?:чек\w*|фискальн\w*\s+документ\w*)\b")
                      and _has(s, r"\b(?:офд|оператор\w*\s+фискальн\w*\s+данн\w*)\b"))
    receipt_to_operator_failed = (
        _has(s, r"\b(?:чек\w*|фискальн\w*\s+документ\w*)\b")
        and _has(s, r"\bоператор\w*\b")
        and _has(s, r"\b(?:не\s+(?:доход|поступ)\w*|перестал\w*\s+(?:доход|поступ)\w*)\b")
    )
    if receipt_to_operator_failed and not _has(s, r"\b(?:печат\w*|распечат\w*|возврат\w*)\b"):
        return result("receipt_transmission", "diagnose", "receipt", "diagnostic",
                      "receipt_delivery_to_operator_failed")
    # The grounded subject can name the OFD while the symptom describes sales
    # at the till rather than spelling out "receipt". This is still a
    # transmission diagnostic, provided no distinct print/refund operation is
    # requested. The subject is client-grounded by Understanding upstream.
    reported_problem = _has(s, r"\b(?:не|нет|ничего|сбой\w*|пропал\w*|очеред\w*)\b")
    if (subject == "ОФД" and operation in {"diagnose", "check", "status"}
            and (operation == "diagnose" or reported_problem)
            and _has(s, r"\b(?:касс\w*|ккт|продаж\w*|выручк\w*)\b")
            and not _has(s, r"\b(?:печат\w*|распечат\w*|возврат\w*|вернут\w*)\b")):
        return result("receipt_transmission", "diagnose", "receipt", "diagnostic",
                      "ofd_subject_with_till_diagnostic")
    printing_failure = _has(s, r"\bне\s+печат\w*|\bпроблем\w*\s+с\s+печать\w*")
    if (receipt_at_ofd and not printing_failure
            and (operation == "diagnose" or
                 (operation in {"check", "status", "unknown"} and reported_problem))):
        return result("receipt_transmission", "transmit" if operation == "transmit" else "diagnose",
                      "receipt", "diagnostic", "receipt_at_ofd_diagnostic")
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
