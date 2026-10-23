"""Task-aware candidate selection and evidence assessment for support RAG.

The pipeline is deliberately independent of Telegram and persistence. A backend
only needs to return hybrid candidates and, optionally, chunks for one article.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Protocol

from app.dialogue_state import DialogueState
from app.procedure_policy import (document_applicability, normalize_operation,
                                  operation_compatibility, query_operation_hints)
from app.rag import SearchResult
from app.response_grounding import (claim_supported, evidence_statements, has_action,
                                    has_named_role, normalize, permission_clauses, statements,
                                    unsafe_operation_issue)


class CandidateSource(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]: ...


@dataclass
class Relevance:
    service: str
    task: str
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class EvaluatedDocument:
    source: str
    document_id: str | None
    status: str | None
    metadata: dict
    retrieval: dict
    relevance: Relevance
    reasons: list[str] = field(default_factory=list)
    selected: bool = False


@dataclass
class RetrievalResult:
    query: str
    candidates: list[EvaluatedDocument]
    rejected: list[EvaluatedDocument]
    documents: list[SearchResult]
    sufficient: bool
    insufficiency_reason: str | None
    context: str
    evidence_status: str = "none"
    missing_evidence: list[str] = field(default_factory=list)
    supported_steps: list[dict] = field(default_factory=list)

    @property
    def evidence_level(self) -> str:
        """Stable four-state evidence contract; legacy fields remain readable."""
        if self.evidence_status == "unsafe":
            return "unsafe"
        if self.evidence_status in {"full", "source_confirmed"} and self.sufficient:
            return "full"
        if self.evidence_status == "partial" and self.supported_steps:
            return "partial"
        # Compatibility for callers constructing the pre-v2 RetrievalResult:
        # a relevant legacy result without a coverage declaration is useful,
        # but remains partial rather than being promoted to full evidence.
        if self.evidence_status == "none" and self.sufficient and self.documents:
            if evidence_statements(self.documents, self.context):
                return "partial"
        return "none"

    def diagnostics(self) -> dict:
        return {
            "rag_query": self.query,
            "candidates": [asdict(item) for item in [*self.candidates, *self.rejected]],
            "rejected": [asdict(item) for item in self.rejected],
            "selected": [asdict(item) for item in self.candidates if item.selected],
            "sufficient": self.sufficient,
            "insufficiency_reason": self.insufficiency_reason,
            "context": self.context,
            "evidence_status": self.evidence_status,
            "evidence_level": self.evidence_level,
            "missing_evidence": self.missing_evidence,
            "supported_steps": self.supported_steps,
            "relevant": bool(self.documents),
        }


# Broad task families map existing, inconsistent labels and source folders to
# one runtime vocabulary. This is a derived view: it does not mutate files/index.
_TASK_TERMS = {
    "bank_statement": ("директбанк", "банковская выписка", "банковских выписок", "список выписок", "другого банка", "банк-посредник", "через посредника"),
    "integration": ("интеграция с 1с", "подключить к 1с", "1с:унф", "1с:розница", "1с:бухгалтерия", "совместим", "поддерживается", "версия 1с", "cms"),
    "settings": ("интернет-магазин", "интернет магазин", "облачная касса", "облачную кассу", "облачной касс", "дополнительный адрес", "адрес магазина", "тестовом режиме"),
    "product_catalog": ("каталог товаров", "карточка товара", "добавить товар", "загрузить товары", "товары в excel"),
    "period_close": ("закрыть месяц", "закрытие месяца", "закрытии месяца", "месяц в 1с", "завершить месяц"),
    "reconciliation": ("акт сверки", "сверить контрагента", "сверка с контрагентом", "взаиморасчет"),
    "goods_receipt": ("не доставили", "получить товар", "приемка товара", "фактически получил", "фактическое количество", "товар пришел", "товар пришёл", "на два склада"),
    "vat_usn": ("усн", "ндс", "налогообложение", "освобождение от ндс", "лимит доходов"),
    "refund": ("вернуть деньги", "возврат денег", "возврат покупателю"),
    "sales": ("проданный товар", "продажу товара", "отложенный заказ"),
    "cash_operations": ("открыть смену", "закрыть смену", "смена на кассе", "управление сменой"),
    "shift_management": ("x-отчет", "x отчет", "отчёт без гашения", "отчет без гашения", "кассовые операции"),
    "fiscal_format": ("формат фискальных документов", "формат фд", "ффд"),
    "model_features": ("характеристики модели", "возможности модели", "функции модели", "функци", "модель поддерживает", "особенности модели", "особенности", "что умеет"),
    "receipt_print": ("копия чека", "копию чека", "печать документа по номеру", "повторная печать"),
    "cash_list": ("список касс", "мониторинг касс", "мониторинг", "раздел кассы", "какие кассы", "все мои кассы", "все кассы", "кассах", "не вижу кассу", "ресурсом фн", "остаток ресурса", "ресурса фн", "заканчивающимся ресурсом"),
    "cash_search": ("заводскому номеру", "номер фн"),
    "access": ("сотрудник", "пользователь", "учетная запись", "доступ", "права", "роль", "account", "user"),
    "receipt_search": ("поиск чека", "найти чек", "чек по", "receipt search", "receipts/search"),
    "correction_receipt": ("исправить чек", "исправление чека", "чек коррекции", "коррекция чека"),
    "receipt_transmission": ("передача чеков", "передача документов", "отправка чеков", "не отправляются", "не передаются", "не может передать", "не передает", "передается", "передаётся", "не поступает", "связаться с офд", "ofd transmission"),
    "fiscal_document_control": ("код флк", "флк", "контроль фискального документа"),
    "marking": ("маркиров", "код маркировки", "честный знак", "разрешительный режим", "gtin", "марка не была проверена"),
    "billing": ("сменить тариф", "изменение тарифа", "тариф", "лицензия", "продление", "баланс", "задолж", "долг", "оплат", "закрывающие документы", "акт сверки", "приостановить обслуживание", "заморозить", "без платежей"),
    "network_diagnostics": ("мобильный интернет", "мобильному интернету", "связь кассы", "проверить соединение", "нет связи"),
    "document_discrepancy": ("упд", "накладная", "расхождение", "недостача", "фактическое количество"),
    "error_diagnosis": ("код ошибки", "ошибка фн", "ошибка ккт", "диагностика ошибки", "error code", "не печатает", "не записан в фн", "не совпадает время", "расхождение времени", "исчезли с кассы"),
    "edo": ("эдо", "электронный документооборот", "электронные документы", "приглашени", "диадок"),
    "equipment_setup": ("подключение", "настройка", "конфигурация", "установка", "активация", "configure", "setup"),
    "ofd_connection": ("подключить кассу", "подключение кассы", "добавить кассу в офд", "сервер офд", "порт офд", "архивир", "архив кассы"),
    "fns_monitoring": ("запрет от фнс", "индикатор фнс", "индикаторы фнс", "детализация нарушений"),
}
_TASK_EVIDENCE = {
    "bank_statement": ("выписк", "директбанк", "банковск"),
    "integration": ("интеграци", "драйвер", "1с", "совместим"),
    "receipt_print": ("копия", "печать", "фискальн", "фд"),
    "cash_list": ("мониторинг", "отобрать кассы", "список касс"),
    "access": ("сотрудник", "пользователь", "учетн", "доступ", "прав", "рол"),
    "cash_reports": ("отчет", "отчёт"),
    "receipt_search": ("чек", "найт", "поиск", "журнал", "квитанц"),
    "correction_receipt": ("чек", "исправ", "коррекц", "ошиб"),
    "receipt_transmission": ("передач", "отправ", "неотправ", "очеред", "офд"),
    "fiscal_document_control": ("флк", "итог чек", "сумм оплат", "фискальн документ"),
    "marking": ("маркиров", "честн знак", "gtin", "разрешительн", "код товар"),
    "billing": ("тариф", "лиценз", "прайс", "переход", "продлен"),
    "document_discrepancy": ("упд", "накладн", "расхожд", "недостач", "количеств"),
    "error_diagnosis": ("ошиб", "код", "диагност", "фн", "ккт"),
    "edo": ("эдо", "приглашен", "контрагент", "диадок"),
    "equipment_setup": ("настрой", "подключ", "параметр", "конфигурац", "установ"),
    "shift_management": ("x-отчет", "кассовые операц", "смен"),
    "ofd_connection": ("подключ", "сервер", "порт", "архив"),
    "fns_monitoring": ("фнс", "индикатор", "запрет", "нарушен"),
    "model_features": ("модел", "возможност", "функц", "поддерж"),
}
_SAFETY_SECTION = re.compile(r"важно|огранич|предупреж|безопас|специалист|перед выполн|услови|применим", re.I)

# DialogueState uses client-facing verbs while reviewed documents use precise
# operation names.  Both sides are projected into one operation vocabulary
# before comparison; task context prevents a generic verb such as ``change``
# from matching unrelated changes in the same service.
def _query_operation_hints(query: str | None) -> set[str]:
    return query_operation_hints(query)
_TASK_BY_OPERATION = {
    "change_plan": "billing",
    "record_discrepancy": "document_discrepancy",
    "correct_receipt": "correction_receipt",
    "search_receipt": "receipt_search",
    "repeat_print": "receipt_print",
}
_TASK_ALIASES = {
    # Do not collapse every OFD procedure into transmission.  The old global
    # alias made connection/archive candidates look interchangeable with a
    # transmission check.  The compatibility alias is retained only for the
    # explicitly named transmission operation below.
}


def normalize_task_category(task_category: str | None, operations=()) -> str | None:
    normalized_operations = {normalize_operation(str(operation), task_category)
                             for operation in operations}
    implied = {_TASK_BY_OPERATION[operation] for operation in normalized_operations
               if operation in _TASK_BY_OPERATION}
    if len(implied) == 1:
        return implied.pop()
    if not task_category:
        return None
    # ``ofd_connection`` is a real family containing several procedures. Only
    # the old metadata label paired with an explicit transmission operation is
    # projected to the transmission family; connection and archive stay apart.
    if task_category == "ofd_connection" and "check_transmission" in normalized_operations:
        return "receipt_transmission"
    return _TASK_ALIASES.get(str(task_category), task_category)


def normalize_metadata(metadata: dict) -> dict:
    """Project existing Qdrant/front-matter fields into a stable read model."""
    raw = dict(metadata or {})
    source = str(raw.get("source") or "").replace("\\", "/").removeprefix("data/knowledge/").casefold()
    category = str(raw.get("category") or "").casefold()
    title = str(raw.get("title") or "")
    text = str(raw.get("text") or "")
    searchable = f"{source} {category} {title} {text}".casefold().replace("ё", "е")
    parts = source.split("/")
    service = raw.get("service")
    service = str(service).strip() if service else None
    if not service:
        service = {
            "aqsi_online": "aQsi Online", "atol_online": "АТОЛ Онлайн",
            "evotor": "Эвотор", "tspiot": "ТС ПиОТ",
        }.get(parts[0] if parts else "")
        if parts and parts[0] == "platformaofd":
            service = "Платформа ОФД"
    software = raw.get("software")
    if not software and parts and parts[0] == "1c":
        software = "1С"
    raw_task_category = raw.get("task_category") or raw.get("operation")
    if not raw_task_category:
        raw_task_category = _derive_task_category(searchable, category, parts, title)
    explicit_operations = raw.get("_operations_explicit", bool(raw.get("operations")))
    operations = raw.get("operations") or _derive_operations(searchable, raw_task_category)
    task_category = normalize_task_category(
        str(raw_task_category) if raw_task_category else None, operations,
    )
    operation = raw.get("operation") or (operations[0] if operations else None)
    return {
        **raw,
        "service": service,
        "software": str(software).strip() if software else None,
        "task_category": str(task_category) if task_category else None,
        "_raw_task_category": str(raw_task_category) if raw_task_category else None,
        "operation": str(operation) if operation else None,
        "operations": list(operations),
        "_operations_explicit": explicit_operations,
        "manufacturer": str(raw.get("manufacturer") or "").strip() or None,
        "model": str(raw.get("model") or "").strip() or None,
        "status": str(raw.get("status") or "unknown"),
    }


def _derive_task_category(searchable: str, category: str, parts: list[str], title: str = "") -> str | None:
    path = set(parts)
    if "edo" in path or category == "edo":
        return "edo"
    if "bank" in path and any(term in searchable for term in ("директбанк", "банковск", "выписк")):
        return "bank_statement"
    if "integration" in path and "1с" in searchable:
        return "integration"
    # An identified error article retains its subject when its diagnostic
    # explanation mentions transmission. Generic OFD guides do not inherit it.
    identity = title.casefold().replace("ё", "е")
    if category in {"fn", "kkt"} and any(term in identity for term in _TASK_TERMS["error_diagnosis"]):
        return "error_diagnosis"
    if any(term in identity for term in _TASK_TERMS["equipment_setup"]):
        return "equipment_setup"
    if any(term in searchable for term in _TASK_TERMS['cash_list']):
        return 'cash_list'
    if "billing" in path and any(term in searchable for term in _TASK_TERMS["billing"]):
        return "billing"
    if any(term in searchable for term in _TASK_TERMS["correction_receipt"]):
        return "correction_receipt"
    if any(term in searchable for term in _TASK_TERMS["document_discrepancy"]):
        return "document_discrepancy"
    if "account" in path or "users" in path or "access" in path or category in {"account", "users", "access"}:
        return "access"
    if "receipts" in path or category == "receipts":
        return "receipt_search"
    # Content-only normalization requires a pair of access-specific concepts;
    # an incidental "employee" or "settings" mention is not enough.
    access_subject = any(x in searchable for x in ("сотрудник", "пользователь", "учетная запись", "личный кабинет"))
    access_control = (any(x in searchable for x in ("доступ", "права", "полномоч", "account"))
                      or bool(re.search(r"\b(?:роль|роли|ролей|ролям|ролями|ролях)\b", searchable)))
    if access_subject and access_control:
        return "access"
    if any(x in searchable for x in _TASK_TERMS["edo"]):
        return "edo"
    if any(x in searchable for x in _TASK_TERMS["receipt_search"]):
        return "receipt_search"
    if any(x in searchable for x in _TASK_TERMS["receipt_transmission"]):
        return "receipt_transmission"
    if (any(x in searchable for x in ("переда", "отправ", "не поступа"))
            and any(x in searchable for x in ("чек", "документ")) and "офд" in searchable):
        return "receipt_transmission"
    if category in {"fn", "kkt"} and any(x in searchable for x in _TASK_TERMS["error_diagnosis"]):
        return "error_diagnosis"
    if any(x in searchable for x in _TASK_TERMS["error_diagnosis"]):
        return "error_diagnosis"
    if any(x in searchable for x in _TASK_TERMS["equipment_setup"]):
        return "equipment_setup"
    return None


def _derive_operations(searchable: str, task_category: str | None) -> list[str]:
    operations = []
    if task_category == 'cash_list':
        operations.append('list_cash_registers')
    if task_category == "access":
        if any(x in searchable for x in ("добавить сотрудник", "добавление сотрудник", "создать пользовател", "нового пользовател", "add-user")):
            operations.append("add_employee")
        if re.search(r"\b(?:роль|роли|ролей|ролям|ролями|ролях)\b", searchable) and any(x in searchable for x in ("назнач", "присва", "выда", "присво")):
            operations.append("assign_role")
        if any(x in searchable for x in ("существующ", "уже создан", "existing user")) and any(x in searchable for x in ("измен", "редакт", "меню этой записи", "change user")):
            operations.append("change_permissions")
        if any(x in searchable for x in ("сброс парол", "восстановление парол", "reset password")):
            operations.append("reset_password")
    if task_category == "receipt_search":
        operations.append("search_receipt")
    if task_category == "correction_receipt":
        operations.append("correct_receipt")
    if task_category == "billing" and any(x in searchable for x in ("сменить тариф", "изменение тарифа", "change-plan")):
        operations.append("change_plan")
    if task_category == "document_discrepancy":
        operations.append("record_discrepancy")
    if task_category == "receipt_transmission":
        if any(x in searchable for x in (
            "проверить статус передачи", "проверьте статус передачи", "очередь передачи",
            "журнал передачи", "передача прервалась", "не передает документы",
            "не передает чеки", "не передаются чеки", "не отправляются чеки",
            "register error ofd", "check transmission",
        )):
            operations.append("check_transmission")
    if task_category == "error_diagnosis":
        operations.append("diagnose_error")
    return list(dict.fromkeys(operations))


def _terms(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-zа-яё0-9]+", text.casefold().replace("ё", "е"))
            if len(x) > 2 or any(char.isdigit() for char in x)}


def _state_task_category(state: DialogueState, query: str) -> str | None:
    query_folded = query.casefold().replace("ё", "е")
    task_facts = [*([state.task] if state.task else []), *state.goals,
                  *state.constraints, *state.details, *state.parameters]
    task_folded = " ".join(f.value for f in task_facts).casefold().replace("ё", "е")
    # Resolve the task family from positive subject/context evidence before
    # falling back to the coarse DialogueState intent.  These are semantic
    # families, not expected-document lookups.
    if (state.intent == "network"
            and re.search(r"\b(?:офд|оператор\w*)\b", task_folded)
            and re.search(r"подключ\w*|соедин\w*|определ\w*|узна\w*", task_folded)):
        return "ofd_connection"
    if state.intent == "bank_statement" or any(term in query_folded for term in _TASK_TERMS["bank_statement"]):
        return "bank_statement"
    if any(term in task_folded for term in _TASK_TERMS["shift_management"]):
        return "shift_management"
    if (state.task_entity("ofd")
            and ((any(term in task_folded for term in _TASK_TERMS["ofd_connection"])
                  or ("подключ" in task_folded and "офд" in task_folded)))
            and not state.task_entity("manufacturer")):
        return "ofd_connection"
    # Looking up the configured address/port on physical equipment is a
    # parameter check, not the cabinet's connect/archive procedure. Keep the
    # task unresolved so candidate evidence and the hardware boundary decide.
    if (state.task_entity("manufacturer") and "адрес" in task_folded
            and "порт" in task_folded
            and any(term in task_folded for term in ("где", "посмотр", "провер"))):
        return None
    if (state.task_entity("ofd")
            and any(term in task_folded for term in _TASK_TERMS["fns_monitoring"])):
        return "fns_monitoring"
    if (state.task_entity("equipment")
            and (any(term in task_folded for term in _TASK_TERMS["model_features"])
                 or "индикатор" in task_folded or "быстро выключ" in task_folded)):
        return "model_features"
    # Receipt wording has several intentionally strict subfamilies. Resolve
    # these before broad words such as «ФФД», «возврат» or «передача» can
    # pull the request into an unrelated technical family.
    if state.intent == "receipt":
        if (state.symptom and any(term in task_folded for term in
                                  ("не печат", "не записан", "ошибк", "бумаг"))):
            return "error_diagnosis"
        if (state.operation == "return"
                or any(term in task_folded for term in _TASK_TERMS["refund"])
                or "оплаченных товаров" in task_folded):
            return "refund"
        if (state.operation == "correct"
                or any(term in task_folded for term in ("коррекц", "неверная цена", "ффд"))):
            return "correction_receipt"
        if "флк" in task_folded:
            return "fiscal_document_control"
        if (state.operation == "repeat_print"):
            return "receipt_print"
        if any(term in task_folded for term in _TASK_TERMS["receipt_print"]):
            return "receipt_print"
        if (state.operation == "diagnose"
                and any(term in task_folded for term in ("не печат", "не записан", "ошибк", "бумаг"))):
            return "error_diagnosis"
        if ("api" in task_folded or "тестовой отправ" in task_folded) and "ошиб" in task_folded:
            return "integration"
        search_request = (state.operation == "search"
                          or any(term in task_folded for term in (
                              "журнал чек", "выгруз", "экспорт", "конкретн", "найти чек", "поиск чек",
                          ))
                          or bool(re.search(r"журнал.{0,50}чек|чек.{0,50}журнал", task_folded))
                          or (state.operation == "status"
                              and not any(term in task_folded for term in (
                                  "не отправ", "не переда", "очеред", "нет связи",
                              ))))
        if search_request:
            return "receipt_search"
        if state.operation in {"diagnose", "status", "check", "transmit"}:
            return "receipt_transmission"
        if any(term in task_folded for term in _TASK_TERMS["receipt_transmission"]):
            return "receipt_transmission"
        return None
    explicit_error_code = bool(re.search(r"\b(?:фн|код)\s*-?\d{2,}", task_folded))
    if ((explicit_error_code or ("ошибк" in task_folded and re.search(r"\b\d{2,}\b", task_folded)))
            and state.intent != "receipt"):
        return "error_diagnosis"
    if (state.intent == "fiscal_drive" and state.symptom
            and any(term in task_folded for term in ("ошибк", "неисправ", "сбой"))):
        return "error_diagnosis"
    fn_status_request = any(term in task_folded for term in (
        "остаток ресурса", "состояние фн", "срок", "прослуж", "заполн", "ресурс",
    ))
    if (state.intent == "fiscal_drive" and re.search(r"\bфн\b", task_folded)
            and (("кабинет" in task_folded and state.operation in {"check", "search"})
                 or (state.operation in {"check", "search"} and fn_status_request))):
        return "cash_list"
    if (state.intent == "fiscal_drive" and state.operation in {"replace", "check"}
            and re.search(r"\bфн\b", task_folded)):
        return "fiscal_drive"
    if "неоплачен" in task_folded and "счете" in task_folded and "касса" in task_folded:
        # The reviewed metadata calls this OFD-connection family; the runtime
        # projection intentionally uses its canonical transmission alias.
        return "receipt_transmission"
    if (state.operation == "search" and "касс" in task_folded
            and any(term in task_folded for term in _TASK_TERMS["cash_search"])):
        return "cash_search"
    if ("тестовом режиме" in task_folded and "облач" in task_folded):
        return "integration"
    if (any(term in task_folded for term in _TASK_TERMS["reconciliation"])
            and ("контрагент" in task_folded or state.task_entities.get("software")
                 or "1с" in task_folded)):
        return "reconciliation"
    if any(term in task_folded for term in _TASK_TERMS["edo"]):
        return "edo"
    if any(term in task_folded for term in _TASK_TERMS["period_close"]):
        return "period_close"
    if state.operation == "close" and "месяц" in task_folded:
        return "period_close"
    if any(term in task_folded for term in _TASK_TERMS["vat_usn"]):
        return "vat_usn"
    if any(term in task_folded for term in _TASK_TERMS["cash_operations"]):
        return "cash_operations"
    if (state.operation == "search" and "касс" in task_folded
            and any(term in task_folded for term in ("заводскому номеру", "номер фн"))):
        return "cash_search"
    if any(term in task_folded for term in _TASK_TERMS["fiscal_format"]):
        return "fiscal_format"
    if any(term in task_folded for term in _TASK_TERMS["model_features"]):
        return "model_features"
    if any(term in task_folded for term in _TASK_TERMS["product_catalog"]):
        return "product_catalog"
    if ("замороз" in task_folded or "без платеж" in task_folded):
        return "billing"
    if any(term in task_folded for term in _TASK_TERMS["settings"]):
        return "settings"
    if any(term in task_folded for term in _TASK_TERMS["goods_receipt"]):
        return "goods_receipt"
    if (state.task_entities.get("software") and "эквайр" in task_folded
            and "банк" in task_folded):
        # Keep the known metadata ambiguity unresolved; do not turn an
        # acquiring-return accounting question into a receipt refund route.
        return None
    if any(term in task_folded for term in _TASK_TERMS["sales"]):
        return "sales"
    if (any(term in task_folded for term in _TASK_TERMS["refund"])
            and not ("эквайр" in task_folded and "банк" in task_folded
                     and state.task_entities.get("software"))):
        return "refund"
    if any(term in task_folded for term in _TASK_TERMS["billing"]):
        return "billing"
    if any(term in task_folded for term in _TASK_TERMS["cash_list"]):
        return "cash_list"
    if any(term in task_folded for term in _TASK_TERMS["network_diagnostics"]):
        return "network_diagnostics"
    if any(term in task_folded for term in _TASK_TERMS["error_diagnosis"]):
        return "error_diagnosis"
    if any(term in task_folded for term in _TASK_TERMS["marking"]):
        return "marking"
    if any(term in task_folded for term in _TASK_TERMS["receipt_transmission"]):
        return "receipt_transmission"
    if ((state.routing_service or state.task_entities.get("software"))
            and (any(term in task_folded for term in _TASK_TERMS["integration"])
                 or "интеграц" in task_folded)):
        return "integration"
    if (state.operation in {"add", "assign", "add_employee", "assign_role"}
            and any(term in task_folded for term in ("роль", "сотрудник", "бухгалтер"))):
        return "access"
    if state.intent == "receipt" and state.operation == "repeat_print":
        return "receipt_print"
    if state.intent == "receipt" and state.operation == "correct":
        return "correction_receipt"
    if state.intent == "receipt" and any(term in query_folded for term in _TASK_TERMS["receipt_print"]):
        return "receipt_print"
    if state.intent == 'report' and state.operation == 'view_reports':
        return 'cash_reports'
    if state.intent == 'device' and state.operation == 'list' and not state.error:
        return 'cash_list'
    if state.intent == 'fiscal_drive' and state.operation == 'search':
        return 'fiscal_drive_search'
    if state.intent in {"access", "credentials"}:
        return "access"
    if state.intent == "billing":
        return "billing"
    if state.intent == "delivery_document":
        return "document_discrepancy"
    if state.error and state.task_entity("manufacturer"):
        return "error_diagnosis"
    if state.intent == "marking":
        return "marking"
    if "флк" in task_folded:
        return "fiscal_document_control"
    if (state.operation == "diagnose" and state.task_entity("manufacturer")
            and any(term in task_folded for term in ("не печат", "печать", "индикатор", "ошибка"))):
        return "error_diagnosis"
    if state.intent in {"device", "fiscal_drive", "network"} and (
            state.error or state.operation == "diagnose"
            or (state.symptom and any(term in task_folded for term in ("ошибк", "неисправ", "сбой")))):
        return "error_diagnosis"
    query_terms = _terms(query)
    matches = [(len(query_terms & _terms(" ".join(words))), family)
               for family, words in _TASK_TERMS.items()]
    matches = [item for item in matches if item[0] >= 2]
    return max(matches)[1] if matches else None


def _related_search_task(state: DialogueState, expected: str | None, actual: str | None) -> bool:
    """Allow neighboring search scopes to contribute field limits, not steps.

    A receipt-search article can answer whether a fiscal-drive field is
    documented, while its operation metadata and source text still decide what
    it can affirm. Service and approved-status gates remain unchanged.
    """
    return (state.operation == "search" and state.intent in {"receipt", "fiscal_drive"}
            and {expected, actual} == {"receipt_search", "fiscal_drive_search"})


def _related_task_for_query(state: DialogueState, expected: str | None,
                            actual: str | None, query: str) -> bool:
    if _related_search_task(state, expected, actual):
        return True
    # Some approved OFD materials describe the account state that explains an
    # unpaid/disabled cash register. This is a semantic relation for that
    # explicit condition, not a global alias between connection procedures.
    folded = query.casefold().replace("ё", "е")
    return (expected == "receipt_transmission" and actual == "ofd_connection"
            and "неоплачен" in folded and "касс" in folded)


def _unconfirmed_search_parameters(state: DialogueState, context: str) -> list[str]:
    """Find requested search fields not positively tied to this search object."""
    if state.operation != "search":
        return []
    missing = []
    for fact in state.parameters:
        value = fact.value.strip()
        if not re.search(r"\bпо\b", value, re.I):
            continue
        # The parameter extractor may retain the service suffix ("в ОФД")
        # with the requested field. Use a neutral search claim so this check
        # tests field/object evidence rather than requiring the source to use
        # one specific verb such as "фильтровать".
        claim = f"Поиск {state.object or 'результатов'} {value}"
        # A source's explicit negative boundary must override a positive match
        # assembled from neighboring, unrelated statements (for example a
        # separate search by the same technical identifier).
        limitation = f"{value} не подтверждён как фильтр {state.object or 'результатов'}"
        if claim_supported(limitation, context) or not claim_supported(claim, context):
            missing.append(value)
    return missing


def _matches_entity(expected: str | None, actual: str | None) -> bool:
    if not expected:
        return True
    if not actual:
        return False
    expected_terms, actual_terms = _terms(expected), _terms(actual)
    # Product families with and without an Online cabinet are independent
    # routes.  Token-subset matching must not turn aQsi into aQsi Online (or
    # АТОЛ into АТОЛ Онлайн) merely because they share the vendor name.
    online = {"online", "онлайн"}
    vendor_roots = {"aqsi", "акси", "атол"}
    if ((expected_terms | actual_terms) & vendor_roots
            and bool(expected_terms & online) != bool(actual_terms & online)):
        return False
    if expected_terms <= actual_terms or actual_terms <= expected_terms:
        return True
    # Russian case endings around a model name (for example «на Эвоторе
    # 7.3») must not be treated as a different device, while different
    # numeric releases remain incompatible.
    expected_numbers = re.findall(r"\d+(?:[.,]\d+)*", expected.casefold())
    actual_numbers = re.findall(r"\d+(?:[.,]\d+)*", actual.casefold())
    if expected_numbers and expected_numbers == actual_numbers:
        expected_roots = {term[:5] for term in expected_terms if not term[0].isdigit()}
        actual_roots = {term[:5] for term in actual_terms if not term[0].isdigit()}
        return bool(expected_roots & actual_roots)
    return False


def _procedure_matches(state: DialogueState, metadata: dict) -> bool:
    scope = metadata.get("procedure_service")
    if not scope or not state.routing_service:
        return True
    # A publisher's integration article may legitimately apply to another
    # cabinet only when that cabinet is established in the active client task.
    return any(_matches_entity(value.value, scope)
               for slot, values in state.task_entities.items() if slot in {"service", "ofd", "software"}
               for value in values)


def _operation_matches(operation: str, metadata: dict, hit: SearchResult,
                        query: str | None = None) -> bool:
    compatibility = operation_compatibility(operation, metadata, query)
    if compatibility != "mismatch":
        return True
    supported = {normalize_operation(item, metadata.get("task_category"))
                 for item in metadata.get("operations") or ()}
    if metadata.get("_operations_explicit"):
        # Opening an existing record / configuring a role is useful partial
        # evidence for changing permissions, not proof of a complete workflow.
        if operation == "change_permissions" and bool(supported & {"edit_user", "configure_role"}):
            return True
        if (operation == "change_permissions" and bool(supported & {"add_employee", "assign_role"})
                and query and any(term in query.casefold() for term in ("уже завед", "уже создан", "отредакт"))):
            return True
        return False
    text = " ".join((hit.text, str(metadata.get("title") or ""), str(metadata.get("source") or ""))).casefold()
    if operation == "assign_role":
        return bool(re.search(r"\b(?:роль|роли|ролей|ролям|ролями|ролях)\b", text)) and any(x in text for x in ("назнач", "присва", "выда", "присво"))
    if operation == "add_employee":
        return any(x in text for x in ("добавить сотрудник", "добавление сотрудник", "создать пользовател", "add-user"))
    if operation == "change_permissions":
        return (any(x in text for x in ("существующ", "уже создан", "existing user"))
                and any(x in text for x in ("измен", "редакт", "меню этой записи", "change user")))
    return False


def _unresolved_task_fallback(state: DialogueState, query: str, hit: SearchResult,
                              metadata: dict, *, service_match: bool,
                              manufacturer_match: bool, model_match: bool,
                              software_match: bool, operation_status: str) -> bool:
    """Allow a well-supported approved article when task classification is absent.

    This is deliberately narrower than ordinary task matching.  It requires a
    confirmed service, compatible explicit entities, a generic (not
    operation-specific) client verb, and two independent retrieval signals.
    A high raw rank alone is never enough.  The fallback does not apply to an
    unsafe request or to a specific operation mismatch.
    """
    if metadata.get("status") != "approved" or not service_match:
        return False
    if unsafe_operation_issue(query):
        return False
    manufacturer = state.entity("manufacturer") or state.task_entity("manufacturer")
    equipment = state.entity("equipment") or state.task_entity("equipment")
    software = state.entity("software") or state.task_entity("software")
    if any((manufacturer and not manufacturer_match,
            equipment and not model_match,
            software and not software_match)):
        return False
    if operation_status == "mismatch":
        return False

    request = state.task.value if state.task else query
    # Compare stems and remove the confirmed service itself.  Otherwise a
    # high-ranked article from the right cabinet could pass merely by
    # repeating "aQsi Online" without supporting the requested object.
    stem = lambda value: {item[:5] if item.isalpha() and len(item) > 5 else item
                          for item in _terms(value)}
    routing_terms = stem(state.routing_service or "")
    request_terms = stem(request) - routing_terms
    searchable = " ".join((
        hit.text,
        str(metadata.get("title") or ""),
        str(metadata.get("source") or ""),
        str(metadata.get("task_category") or ""),
        " ".join(str(item) for item in metadata.get("operations") or ()),
    ))
    document_terms = stem(searchable) - routing_terms
    overlap = len(request_terms & document_terms) / max(1, len(request_terms))
    shared_terms = len(request_terms & document_terms)
    semantic = hit.semantic_score
    if semantic is None:
        # Test doubles and legacy stores may not expose a dense score.  In
        # that case require a stronger lexical signal instead of guessing.
        return overlap >= 0.45 and shared_terms >= 3
    combined = 0.55 * max(0.0, float(semantic)) + 0.45 * overlap
    return (shared_terms >= 2 and overlap >= 0.15 and float(semantic) >= 0.33
            and combined >= 0.28)


def _access_evidence(state, documents, context):
    """Coverage is reviewed source metadata, never a relevance-score claim.

    Full coverage of a generic operation does not establish a named role or
    client-specific privileges. Those remain partial until independently checked.
    Only complete statements actually sent in context can become useful steps.
    """
    steps, seen = [], set()
    families = {"change_permissions": ("edit", "search", "configure", "choose"),
                "assign_role": ("assign", "input", "configure", "choose"),
                "create_role": ("create", "input", "configure", "edit"),
                "add_employee": ("create", "input", "assign", "save"),
                "reset_password": ("reset",)}.get(state.operation, ())
    full = False
    for doc in documents:
        meta = doc.metadata or {}
        if not families:
            continue
        if (state.operation == "change_permissions" and meta.get("_operations_explicit")
                and not set(meta.get("operations") or ()) & {"change_permissions", "edit_user"}):
            continue
        section = str(meta.get("section") or "")
        coverage = meta.get("evidence_coverage") or {}
        # A declaration counts only if that article contributes an actual step.
        contributes = False
        for sentence in statements(doc.text):
            key = normalize(sentence)
            action_evidence = any(has_action(sentence, family) for family in families)
            permission_evidence = (state.operation in {"assign_role", "create_role", "change_permissions"}
                                   and (any(permission_clauses(sentence))
                                        or bool(re.search(
                                            r"\b(?:рол[ьи]|прав[ао]?|доступ\w*|разреш\w*|полномоч\w*)\b",
                                            sentence, re.I))))
            if (sentence == section or sentence.startswith(("#", "Источник:", "http"))
                    or sentence.endswith("?") or len(sentence.split()) < 4
                    or key not in normalize(context)
                    or not (action_evidence or permission_evidence)):
                continue
            contributes = contributes or action_evidence
            if key not in seen:
                steps.append(dict(source=doc.source, document_id=meta.get("document_id"),
                                  section=section, text=sentence))
                seen.add(key)
        if (contributes and coverage.get(state.operation) == "full"
                and meta.get("source_url") and meta.get("source_checked_at")):
            full = True
    missing = []
    if not full:
        missing.append({"change_permissions": "permission_change_workflow_unverified",
                        "create_role": "role_creation_workflow_unverified"}.get(state.operation, "access_workflow_unverified"))
    request = " ".join(f.value for f in [*state.goals, *state.constraints, *state.details,
                                        *([state.task] if state.task else [])])
    if (state.goals or state.constraints or has_named_role(request)
            or state.operation == "change_permissions"):
        missing.append("requested_role_or_permissions_unverified")
    status = "full" if steps and not missing else "partial" if steps else "none"
    return status, missing, steps[:12]


def _scoped_evidence_documents(documents: list[SearchResult], expected_task: str | None,
                               state: DialogueState, query: str = "") -> list[SearchResult]:
    """Keep evidence from one coherent article for the current operation.

    Retrieval may legitimately return neighboring articles for recall, but a
    partial answer cannot splice their independent procedures together. The
    first article that passes task and operation gates becomes the sole source
    of extractive partial evidence; its sibling chunks remain available.
    """
    matching: list[SearchResult] = []
    primary_key: str | None = None
    for document in documents:
        meta = normalize_metadata({**(document.metadata or {}), "text": document.text})
        if meta.get("status") != "approved":
            continue
        if (expected_task and meta.get("task_category") != expected_task
                and not _related_task_for_query(state, expected_task, meta.get("task_category"), query)):
            continue
        if (state.operation != "explain"
                and operation_compatibility(state.operation, meta, query,
                                            task_category=expected_task) == "mismatch"):
            continue
        key = str(meta.get("document_id") or meta.get("source") or document.source)
        if primary_key is None:
            primary_key = key
        if key == primary_key:
            matching.append(document)
    return matching


class RetrievalPipeline:
    def __init__(self, source: CandidateSource, *, candidate_k: int = 100,
                 max_documents: int = 4, max_context_chars: int = 7000,
                 expand_chunks: bool = True):
        self.source = source
        self.candidate_k = candidate_k
        self.max_documents = max_documents
        self.max_context_chars = max_context_chars
        self.expand_chunks = expand_chunks

    def search(self, state: DialogueState, query: str) -> RetrievalResult:
        unsafe = unsafe_operation_issue(query)
        raw = self.source.search(query, top_k=self.candidate_k)
        expected_task = _state_task_category(state, query)
        evaluated_hits: list[tuple[str, SearchResult, EvaluatedDocument, bool]] = []
        for hit in raw:
            meta = normalize_metadata({**(hit.metadata or {}), "source": (hit.metadata or {}).get("source") or hit.source,
                                       "text": hit.text})
            doc_key = str(meta.get("document_id") or meta.get("source")
                          or meta.get("chunk_id") or id(hit))
            reasons: list[str] = []
            # The pipeline is a second safety boundary: drafts and unlabeled
            # snapshots never become answer context, even if a source adapter
            # accidentally returns them.
            if meta.get("status") != "approved":
                reasons.append("status_unapproved")
            # Session facts persist across tasks. Only the cabinet bound to the
            # current task is a hard service constraint; hardware is required
            # separately for technical tasks, not for an OFD receipt filter.
            # An OFD is a current routing fact even when the reducer keeps it
            # outside the active service slot for fiscal-drive questions.
            routing = state.routing_service or state.task_entity("ofd")
            routing_metadata = meta.get('service')
            if state.routing_slot == 'manufacturer':
                routing_metadata = meta.get('manufacturer')
            elif state.routing_slot == 'software':
                routing_metadata = meta.get('software') or meta.get('service')
            service_match = _matches_entity(routing, routing_metadata)
            software = state.task_entity("software")
            software_match = _matches_entity(software, meta.get("software"))
            if expected_task == "integration" and software and not software_match:
                reasons.append("software_mismatch_or_unlabeled")
            if meta.get("procedure_service") and state.routing_slot not in {"manufacturer", "software"}:
                service_match = _procedure_matches(state, meta)
            # Keep manufacturer, equipment model and operator as independent facts.
            manufacturer_fact = state.entity("manufacturer") or state.task_entity("manufacturer")
            equipment_fact = state.entity("equipment") or state.task_entity("equipment")
            manufacturer_match = _matches_entity(manufacturer_fact, meta.get("manufacturer"))
            model_match = _matches_entity(equipment_fact, meta.get("model"))
            technical = (state.intent in {'device', 'fiscal_drive', 'network'}
                        and expected_task in {
                            'device', 'fiscal_drive', 'network_diagnostics', 'ofd_connection',
                            'error_diagnosis', 'receipt_transmission',
                            'fiscal_document_control', 'fiscal_format', 'marking',
                        })
            ofd = state.entity("ofd") if technical else None
            ofd_match = _matches_entity(ofd, " ".join(str(meta.get(k) or "") for k in ("ofd", "operator", "title", "source", "text")))
            actual_task = meta.get("task_category")
            query_terms = _terms(query)
            body_terms = _terms(hit.text + " " + str(meta.get("title") or ""))
            lexical_overlap = len(query_terms & body_terms) / max(1, len(query_terms))
            related_search_task = _related_task_for_query(state, expected_task, actual_task, query)
            operation_metadata = meta
            if expected_task and actual_task == expected_task and meta.get("document_id"):
                article_getter = getattr(self.source, "article", None)
                if callable(article_getter):
                    article_chunks = article_getter(meta["document_id"])
                    article_text = " ".join(chunk.text for chunk in article_chunks)
                    operation_metadata = normalize_metadata({**meta, "text": article_text})
                    if not meta.get("_operations_explicit"):
                        operation_metadata["operations"] = _derive_operations(article_text.casefold(), actual_task)
            operation_status = operation_compatibility(
                state.operation, operation_metadata, query, task_category=expected_task)
            operation_match = operation_status == "match"
            unscoped_match = (expected_task is None and state.intent != "unknown"
                              and lexical_overlap >= 0.50)
            unresolved_fallback = False
            if expected_task is None:
                unresolved_fallback = _unresolved_task_fallback(
                    state, query, hit, meta,
                    service_match=service_match,
                    manufacturer_match=manufacturer_match,
                    model_match=model_match,
                    software_match=software_match,
                    operation_status=operation_status,
                )
                unscoped_match = unscoped_match or unresolved_fallback
            task_match = (actual_task == expected_task if expected_task else unscoped_match) or related_search_task
            if routing and not service_match:
                reasons.append("service_mismatch_or_unlabeled")
            procedure_service = meta.get("procedure_service")
            if not _procedure_matches(state, meta):
                reasons.append(f"procedure_service_mismatch:{procedure_service}")
            model_bound = technical or expected_task in {"model_features", "integration"}
            if model_bound and manufacturer_fact and not manufacturer_match:
                reasons.append("manufacturer_mismatch_or_unlabeled")
            if model_bound and equipment_fact and not model_match:
                reasons.append("equipment_mismatch_or_unlabeled")
            if ofd and not ofd_match:
                reasons.append("ofd_mismatch_or_unlabeled")
            missing_scope = document_applicability(state, meta, technical=technical)
            if missing_scope:
                reasons.extend(f"applicability_{slot}_unconfirmed" for slot in missing_scope)
            if expected_task and actual_task and actual_task != expected_task and not related_search_task:
                reasons.append(f"task_mismatch:{actual_task}!={expected_task}")
            strong_unlabeled_match = (expected_task and actual_task is None
                                      and service_match and lexical_overlap >= 0.60)
            if (expected_task and actual_task == expected_task and operation_status == "mismatch"
                    and meta.get("_operations_explicit") and meta.get("operations")
                    and state.operation in {"unknown", "explain"}):
                reasons.append("operation_mismatch:query_action")
            elif (expected_task and actual_task == expected_task and operation_status == "mismatch"
                  and meta.get("_operations_explicit") and meta.get("operations")):
                reasons.append(f"operation_mismatch:{state.operation}")
            elif (expected_task and actual_task == expected_task and state.operation != "unknown"
                  and not meta.get("_operations_explicit") and not operation_match
                  and lexical_overlap < 0.30):
                reasons.append("operation_evidence_missing")
            # Missing task/operation labels are not contradictions. A strong
            # lexical match can pass the relevance gate when service and
            # approved-status constraints agree; explicit conflicting labels
            # remain hard rejects.
            if expected_task and actual_task is None and not strong_unlabeled_match:
                reasons.append("task_unconfirmed")
            if expected_task is None and not unscoped_match:
                reasons.append("task_unresolved")
            task_match = (expected_task is None or actual_task == expected_task
                          or related_search_task or bool(strong_unlabeled_match))
            if expected_task is None:
                task_match = unscoped_match
            service_score = 1.0 if not state.entity("service") or service_match else 0.0
            task_score = 1.0 if task_match else (0.0 if actual_task else lexical_overlap)
            score = 0.55 * task_score + 0.3 * service_score + 0.15 * min(1.0, lexical_overlap * 2)
            relevance_reasons = [f"task_category={actual_task or 'unknown'}",
                                 f"lexical_overlap={lexical_overlap:.3f}",
                                 f"operation_match={operation_match}",
                                 f"operation_compatibility={operation_status}",
                                 f"related_search_task={related_search_task}",
                                 f"procedure_service={procedure_service or 'unreviewed'}"]
            if unresolved_fallback:
                relevance_reasons.append("unresolved_task_fallback")
            relevance = Relevance("match" if service_match else "unknown_or_mismatch",
                                  "match" if task_match else "mismatch", round(score, 4),
                                  relevance_reasons)
            diagnostic_fields = {"source", "title", "category", "service", "task_category", "operation",
                                 "operations", "manufacturer", "model", "status", "source_type", "section", "page",
                                 "procedure_service", "evidence_coverage"}
            diagnostic_metadata = {k: v for k, v in meta.items() if k in diagnostic_fields and v is not None}
            evaluated = EvaluatedDocument(str(meta.get("source") or "unknown"), meta.get("document_id"), meta.get("status"), diagnostic_metadata, {"rrf": hit.score, "dense": hit.semantic_score, "bm25": hit.lexical_score}, relevance, reasons)
            evaluated_hits.append((doc_key, hit, evaluated, not reasons))

        # Evaluate every retrieved chunk before collapsing by document.  The
        # former early ``seen_docs`` check made the first lexical hit decide the
        # fate of the entire article, even when a later chunk matched the task
        # and operation better.
        accepted_by_document: dict[str, tuple[SearchResult, EvaluatedDocument]] = {}
        rejected_by_document: dict[str, tuple[SearchResult, EvaluatedDocument]] = {}
        for doc_key, hit, evaluated, accepted in evaluated_hits:
            target = accepted_by_document if accepted else rejected_by_document
            current = target.get(doc_key)
            rank = (evaluated.relevance.score, hit.score, -len(evaluated.reasons))
            current_rank = ((current[1].relevance.score, current[0].score,
                             -len(current[1].reasons)) if current else None)
            if current is None or rank > current_rank:
                target[doc_key] = (hit, evaluated)
        selected = list(accepted_by_document.values())
        candidates = [evaluated for _, evaluated in selected]
        rejected = [evaluated for key, (_, evaluated) in rejected_by_document.items()
                    if key not in accepted_by_document]
        for evaluated in candidates:
            evaluated.selected = True

        def selection_rank(pair):
            hit, evaluated = pair
            if expected_task is None and "unresolved_task_fallback" in evaluated.relevance.reasons:
                # For unresolved routing, lexical evidence identifies the
                # requested object/action more precisely than a dense tie.
                # Dense relevance already passed as a separate hard gate.
                return (hit.lexical_score or 0.0, hit.semantic_score or 0.0, hit.score)
            return (evaluated.relevance.score, hit.score, 0.0)

        selected.sort(key=selection_rank, reverse=True)
        unresolved_ambiguity = False
        if expected_task is None and len(selected) > 1:
            top_hit, top_evaluated = selected[0]
            second_hit, second_evaluated = selected[1]
            if ("unresolved_task_fallback" in top_evaluated.relevance.reasons
                    and "unresolved_task_fallback" in second_evaluated.relevance.reasons):
                top_lexical = top_hit.lexical_score or 0.0
                second_lexical = second_hit.lexical_score or 0.0
                lexical_margin = ((top_lexical - second_lexical) / max(1.0, abs(second_lexical))
                                  if top_lexical else 0.0)
                semantic_margin = ((top_hit.semantic_score or 0.0)
                                   - (second_hit.semantic_score or 0.0))
                if lexical_margin < 0.03 and semantic_margin < 0.08:
                    unresolved_ambiguity = True
                    for _, evaluated in selected:
                        if "unresolved_task_ambiguous" not in evaluated.reasons:
                            evaluated.reasons.append("unresolved_task_ambiguous")
                    selected = []
        # Related chunks are fetched only after article-level gates have passed;
        # their own task relevance is checked and they keep their own identity.
        # An unresolved task cannot safely justify mixing several procedures
        # from one service.  Keep the strongest coherent article only; its
        # sibling chunks are expanded below and preserve the needed steps.
        # An unresolved operation must not splice several procedures from the
        # same task family. Pick one best candidate and clarify if its margin
        # is not safe; explicit operations may still use the normal limit.
        selection_limit = 1 if selected and (
            expected_task is None
            or (state.operation in {"unknown", "explain"} and _query_operation_hints(query))
        ) else self.max_documents
        docs = self._expand(selected[:selection_limit], expected_task, state, query)
        used_sources = {doc.source for doc in docs}
        for item in candidates:
            item.selected = item.source in used_sources
        context = _format_context(docs, self.max_context_chars)
        sufficient = bool(docs) and any(item.relevance.task == "match" and item.relevance.score >= 0.62 for _, item in selected)
        applicability_missing = any(
            reason.startswith("applicability_") and reason.endswith("_unconfirmed")
            for item in rejected for reason in item.reasons)
        reason = ("unresolved_task_ambiguous" if unresolved_ambiguity
                  else "applicability_context_missing" if applicability_missing
                  else None if sufficient
                  else "no_task_matched_candidates" if raw else "no_candidates")
        # The new source-coverage contract is scoped to access workflows.
        # Other task families retain their existing gate, without claiming a
        # reviewed proof of every search parameter or business requirement.
        evidence_status, missing, steps = ("relevance_only" if sufficient else "none"), [], []
        if expected_task == "access" and docs:
            evidence_status, missing, steps = _access_evidence(state, docs, context)
            if evidence_status == "none":
                steps = evidence_statements(docs, context)
                if steps:
                    evidence_status = "partial"
                    missing = (["permission_change_workflow_unverified",
                                "requested_role_or_permissions_unverified"]
                               if state.operation == "change_permissions"
                               else ["access_workflow_unverified"])
                    reason = "access_evidence_incomplete"
            sufficient = sufficient and evidence_status == "full"
            reason = None if sufficient else "access_evidence_incomplete"
        elif docs:
            evidence_docs = _scoped_evidence_documents(docs, expected_task, state, query)
            steps = evidence_statements(evidence_docs, context, limit=4, request=query)
            # The candidate gates already established one approved, coherent
            # article and an operation-compatible source.  Some valid answers
            # use different vocabulary (for example «импорт» vs «загрузка»),
            # so a strict lexical overlap must not turn that source into
            # no-context. This only supplies evidence for the model; it never
            # mechanically assembles a customer response.
            if not steps and len({(doc.metadata or {}).get("document_id") for doc in evidence_docs}) == 1:
                steps = evidence_statements(evidence_docs, context, limit=4)
            unconfirmed_fields = _unconfirmed_search_parameters(state, context)
            coverage_keys = {
                "search": ("search", "search_receipt"),
                "view_reports": ("view_reports", "view_cash_reports"),
                "list": ("list", "list_cash_registers", "list_bank_statements"),
                "connect": ("connect", "configure_integration", "check_integration_compatibility"),
            }.get(state.operation, (state.operation,))
            full_coverage = False
            for doc in evidence_docs:
                meta = doc.metadata or {}
                coverage = meta.get("evidence_coverage") or {}
                if (any(coverage.get(key) == "full" for key in coverage_keys) and meta.get("source_url")
                        and meta.get("source_checked_at") and steps):
                    full_coverage = True
                    break
            if full_coverage and sufficient and not unconfirmed_fields:
                evidence_status, missing = "full", []
            elif steps:
                evidence_status = "partial"
                missing = ([f"search_parameter_unconfirmed:{field}" for field in unconfirmed_fields]
                           or ["procedure_completeness_unverified"])
                reason = "evidence_coverage_incomplete"
            else:
                evidence_status, missing = "none", ["no_source_statements_in_context"]
                sufficient = False
                reason = "no_source_statements_in_context"
        if unsafe:
            evidence_status, missing, sufficient = "unsafe", ["high_risk_operation_requires_specialist"], False
            reason = "unsafe_operation:" + unsafe
        return RetrievalResult(query, candidates, rejected, docs, sufficient, reason, context,
                               evidence_status, missing, steps)

    def _expand(self, selected, expected_task, state, query) -> list[SearchResult]:
        result: list[SearchResult] = []
        seen: set[tuple[str, str]] = set()
        for hit, evaluated in selected:
            source = str((hit.metadata or {}).get("source") or hit.source)
            related = [hit]
            getter = getattr(self.source, "article", None)
            if self.expand_chunks and callable(getter) and evaluated.document_id:
                article = getter(evaluated.document_id)
                if article:
                    hit_id = (hit.metadata or {}).get("chunk_id")
                    replaced = False
                    related = []
                    for fragment in article:
                        fragment_id = (fragment.metadata or {}).get("chunk_id")
                        if ((hit_id and fragment_id == hit_id)
                                or (not hit_id and fragment.text == hit.text)):
                            related.append(hit)
                            replaced = True
                        else:
                            related.append(fragment)
                    if not replaced:
                        related.append(hit)
                        if all(isinstance((item.metadata or {}).get("chunk_index"), int)
                               for item in related):
                            related.sort(key=lambda item: (item.metadata or {})["chunk_index"])
            for fragment in related:
                meta = normalize_metadata({**(fragment.metadata or {}), "text": fragment.text})
                if not _procedure_matches(state, meta):
                    continue
                fragment_task = meta.get("task_category")
                if (expected_task and fragment_task and fragment_task != expected_task
                        and not _related_task_for_query(state, expected_task, fragment_task, query)):
                    continue
                if fragment is not hit and expected_task:
                    section = str(meta.get("section") or "")
                    evidence_terms = _TASK_EVIDENCE.get(expected_task, ())
                    reviewed_operation = (meta.get("_operations_explicit")
                                          and _operation_matches(state.operation, meta, fragment))
                    if (not _SAFETY_SECTION.search(section) and not reviewed_operation
                            and not any(term in fragment.text.casefold() for term in evidence_terms)):
                        continue
                key = (str(meta.get("source") or source), fragment.text)
                if key in seen:
                    continue
                seen.add(key)
                fragment_meta = {k: v for k, v in meta.items() if k != "text"}
                score = fragment.score if fragment is hit else 0.0
                # Preserve best fragment's retrieval scores only for that fragment.
                result.append(SearchResult(str(meta.get("source") or source), fragment.text, score,
                    fragment.semantic_score if fragment is hit else None,
                    fragment.lexical_score if fragment is hit else None, fragment_meta))
        return result


def _format_context(results: list[SearchResult], limit: int) -> str:
    blocks = []
    used = 0
    for item in results:
        meta = normalize_metadata(item.metadata or {})
        label = (f"[Источник: {item.source}; документ={meta.get('document_id') or 'не указан'}; "
                 f"статус={meta.get('status')}; раздел={meta.get('section') or 'не указан'}; "
                 f"оценка фрагмента={item.score:.5f}]\n")
        block = label + item.text
        remaining = limit - used
        if remaining <= len(label):
            break
        if len(block) > remaining:
            body_budget = remaining - len(label)
            block = label + item.text[:body_budget]
        blocks.append(block)
        used += len(block) + 6
        if used >= limit:
            break
    return "\n\n---\n\n".join(blocks)
