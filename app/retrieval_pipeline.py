"""Task-aware candidate selection and evidence assessment for support RAG.

The pipeline is deliberately independent of Telegram and persistence. A backend
only needs to return hybrid candidates and, optionally, chunks for one article.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Protocol

from app.dialogue_state import DialogueState
from app.rag import SearchResult


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

    def diagnostics(self) -> dict:
        return {
            "rag_query": self.query,
            "candidates": [asdict(item) for item in [*self.candidates, *self.rejected]],
            "rejected": [asdict(item) for item in self.rejected],
            "selected": [asdict(item) for item in self.candidates if item.selected],
            "sufficient": self.sufficient,
            "insufficiency_reason": self.insufficiency_reason,
            "context": self.context,
        }


# Broad task families map existing, inconsistent labels and source folders to
# one runtime vocabulary. This is a derived view: it does not mutate files/index.
_TASK_TERMS = {
    "cash_list": ("список касс", "мониторинг касс", "раздел кассы"),
    "access": ("сотрудник", "пользователь", "учетная запись", "доступ", "права", "роль", "account", "user"),
    "receipt_search": ("поиск чека", "найти чек", "чек по", "receipt search", "receipts/search"),
    "receipt_transmission": ("передача чеков", "передача документов", "отправка чеков", "не отправляются", "не передаются", "ofd transmission"),
    "error_diagnosis": ("код ошибки", "ошибка фн", "ошибка ккт", "диагностика ошибки", "error code"),
    "edo": ("эдо", "электронный документооборот", "приглашени", "контрагент", "диадок"),
    "equipment_setup": ("подключение", "настройка", "конфигурация", "установка", "configure", "setup"),
}
_TASK_EVIDENCE = {
    "cash_list": ("мониторинг", "отобрать кассы", "список касс"),
    "access": ("сотрудник", "пользователь", "учетн", "доступ", "прав", "рол"),
    "receipt_search": ("чек", "найт", "поиск", "журнал", "квитанц"),
    "receipt_transmission": ("передач", "отправ", "неотправ", "очеред", "офд"),
    "error_diagnosis": ("ошиб", "код", "диагност", "фн", "ккт"),
    "edo": ("эдо", "приглашен", "контрагент", "диадок"),
    "equipment_setup": ("настрой", "подключ", "параметр", "конфигурац", "установ"),
}
_SAFETY_SECTION = re.compile(r"важно|огранич|предупреж|безопас|специалист|перед выполн|услови|применим", re.I)


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
    task_category = raw.get("task_category") or raw.get("operation")
    if not task_category:
        task_category = _derive_task_category(searchable, category, parts)
    operations = raw.get("operations") or _derive_operations(searchable, task_category)
    operation = raw.get("operation") or (operations[0] if operations else None)
    return {
        **raw,
        "service": service,
        "task_category": str(task_category) if task_category else None,
        "operation": str(operation) if operation else None,
        "operations": list(operations),
        "manufacturer": str(raw.get("manufacturer") or "").strip() or None,
        "model": str(raw.get("model") or "").strip() or None,
        "status": str(raw.get("status") or "unknown"),
    }


def _derive_task_category(searchable: str, category: str, parts: list[str]) -> str | None:
    path = set(parts)
    if "edo" in path or category == "edo":
        return "edo"
    if any(term in searchable for term in _TASK_TERMS['cash_list']):
        return 'cash_list'
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
    return {x for x in re.findall(r"[a-zа-яё0-9]+", text.casefold().replace("ё", "е")) if len(x) > 2}


def _state_task_category(state: DialogueState, query: str) -> str | None:
    if state.intent == 'device' and state.operation == 'list' and not state.error:
        return 'cash_list'
    if state.intent == 'fiscal_drive' and state.operation == 'search':
        return 'fiscal_drive_search'
    if state.intent in {"access", "credentials"}:
        return "access"
    if state.intent == "receipt":
        if state.operation == "search":
            return "receipt_search"
        if state.operation in {"diagnose", "status", "check", "transmit"}:
            return "receipt_transmission"
        query_folded = query.casefold()
        if any(x in query_folded for x in ("переда", "отправ", "не поступают")):
            return "receipt_transmission"
    if state.intent in {"device", "fiscal_drive", "network"} and (state.error or state.operation == "diagnose"):
        return "error_diagnosis"
    query_terms = _terms(query)
    matches = [(len(query_terms & _terms(" ".join(words))), family)
               for family, words in _TASK_TERMS.items()]
    matches = [item for item in matches if item[0] >= 2]
    return max(matches)[1] if matches else None


def _matches_entity(expected: str | None, actual: str | None) -> bool:
    if not expected:
        return True
    if not actual:
        return False
    return _terms(expected) <= _terms(actual) or _terms(actual) <= _terms(expected)


def _operation_matches(operation: str, metadata: dict, hit: SearchResult) -> bool:
    if operation == "explain":
        return True
    aliases = {
        "add_employee": {"add_employee"},
        "assign_role": {"assign_role"},
        "change_permissions": {"change_permissions"},
        "reset_password": {"reset_password"},
        "search": {"search_receipt"},
        "diagnose": {"diagnose_error", "check_transmission"},
        "status": {"check_transmission"},
        "check": {"check_transmission"},
        "list": {"list_cash_registers"},
        "transmit": {"check_transmission"},
    }
    supported = set(metadata.get("operations") or ())
    if supported & aliases.get(operation, {operation}):
        return True
    text = " ".join((hit.text, str(metadata.get("title") or ""), str(metadata.get("source") or ""))).casefold()
    if operation == "assign_role":
        return bool(re.search(r"\b(?:роль|роли|ролей|ролям|ролями|ролях)\b", text)) and any(x in text for x in ("назнач", "присва", "выда", "присво"))
    if operation == "add_employee":
        return any(x in text for x in ("добавить сотрудник", "добавление сотрудник", "создать пользовател", "add-user"))
    if operation == "change_permissions":
        return (any(x in text for x in ("существующ", "уже создан", "existing user"))
                and any(x in text for x in ("измен", "редакт", "меню этой записи", "change user")))
    return False


class RetrievalPipeline:
    def __init__(self, source: CandidateSource, *, candidate_k: int = 100,
                 max_documents: int = 5, max_context_chars: int = 7000,
                 expand_chunks: bool = True):
        self.source = source
        self.candidate_k = candidate_k
        self.max_documents = max_documents
        self.max_context_chars = max_context_chars
        self.expand_chunks = expand_chunks

    def search(self, state: DialogueState, query: str) -> RetrievalResult:
        raw = self.source.search(query, top_k=self.candidate_k)
        expected_task = _state_task_category(state, query)
        selected: list[tuple[SearchResult, EvaluatedDocument]] = []
        rejected: list[EvaluatedDocument] = []
        candidates: list[EvaluatedDocument] = []
        seen_docs: set[str] = set()
        for hit in raw:
            meta = normalize_metadata({**(hit.metadata or {}), "source": (hit.metadata or {}).get("source") or hit.source,
                                       "text": hit.text})
            doc_key = str(meta.get("document_id") or meta.get("source") or "")
            if doc_key and doc_key in seen_docs:
                continue
            if doc_key:
                seen_docs.add(doc_key)
            reasons: list[str] = []
            # Session facts persist across tasks. Only the cabinet bound to the
            # current task is a hard service constraint; hardware is required
            # separately for technical tasks, not for an OFD receipt filter.
            routing = state.routing_service
            routing_metadata = meta.get('service')
            if state.routing_slot == 'manufacturer':
                routing_metadata = meta.get('manufacturer')
            elif state.routing_slot == 'software':
                routing_metadata = meta.get('software') or meta.get('service')
            service_match = _matches_entity(routing, routing_metadata)
            # Keep manufacturer, equipment model and operator as independent facts.
            manufacturer_match = _matches_entity(state.entity("manufacturer"), meta.get("manufacturer"))
            model_match = _matches_entity(state.entity("equipment"), meta.get("model"))
            technical = state.intent in {'device', 'fiscal_drive', 'network'} and expected_task != 'cash_list'
            ofd = state.entity("ofd") if technical else None
            ofd_match = _matches_entity(ofd, " ".join(str(meta.get(k) or "") for k in ("ofd", "operator", "title", "source", "text")))
            actual_task = meta.get("task_category")
            task_match = expected_task is None or actual_task == expected_task
            operation_metadata = meta
            if expected_task and actual_task == expected_task and meta.get("document_id"):
                article_getter = getattr(self.source, "article", None)
                if callable(article_getter):
                    article_chunks = article_getter(meta["document_id"])
                    article_text = " ".join(chunk.text for chunk in article_chunks)
                    operation_metadata = normalize_metadata({**meta, "text": article_text, "operations": [], "operation": None})
            operation_match = _operation_matches(state.operation, operation_metadata, hit)
            if routing and not service_match:
                reasons.append("service_mismatch_or_unlabeled")
            if technical and state.entity("manufacturer") and not manufacturer_match:
                reasons.append("manufacturer_mismatch_or_unlabeled")
            if technical and state.entity("equipment") and not model_match:
                reasons.append("equipment_mismatch_or_unlabeled")
            if ofd and not ofd_match:
                reasons.append("ofd_mismatch_or_unlabeled")
            if expected_task and actual_task and actual_task != expected_task:
                reasons.append(f"task_mismatch:{actual_task}!={expected_task}")
            if expected_task and actual_task == expected_task and not operation_match:
                reasons.append(f"operation_mismatch:{state.operation}")
            if state.operation == 'unknown':
                reasons.append('operation_unconfirmed')
            # Unlabeled category is not an automatic rejection, but cannot pass
            # a task-specific evidence gate without lexical task evidence.
            query_terms = _terms(query)
            body_terms = _terms(hit.text + " " + str(meta.get("title") or ""))
            lexical_overlap = len(query_terms & body_terms) / max(1, len(query_terms))
            if expected_task and actual_task is None:
                task_match = False
                reasons.append("task_unconfirmed")
            if expected_task and actual_task == expected_task and not operation_match:
                task_match = False
            service_score = 1.0 if not state.entity("service") or service_match else 0.0
            task_score = 1.0 if task_match else (0.0 if actual_task else lexical_overlap)
            score = 0.55 * task_score + 0.3 * service_score + 0.15 * min(1.0, lexical_overlap * 2)
            relevance = Relevance("match" if service_match else "unknown_or_mismatch", "match" if task_match else "mismatch", round(score, 4), [f"task_category={actual_task or 'unknown'}", f"lexical_overlap={lexical_overlap:.3f}"])
            diagnostic_fields = {"source", "title", "category", "service", "task_category", "operation",
                                 "operations", "manufacturer", "model", "status", "source_type", "section", "page"}
            diagnostic_metadata = {k: v for k, v in meta.items() if k in diagnostic_fields and v is not None}
            evaluated = EvaluatedDocument(str(meta.get("source") or "unknown"), meta.get("document_id"), meta.get("status"), diagnostic_metadata, {"rrf": hit.score, "dense": hit.semantic_score, "bm25": hit.lexical_score}, relevance, reasons)
            if reasons:
                rejected.append(evaluated)
            else:
                evaluated.selected = True
                candidates.append(evaluated)
                selected.append((hit, evaluated))

        selected.sort(key=lambda pair: (pair[1].relevance.score, pair[0].score), reverse=True)
        # Related chunks are fetched only after article-level gates have passed;
        # their own task relevance is checked and they keep their own identity.
        docs = self._expand(selected[:self.max_documents], expected_task, state, query)
        used_sources = {doc.source for doc in docs}
        for item in candidates:
            item.selected = item.source in used_sources
        context = _format_context(docs, self.max_context_chars)
        sufficient = bool(docs) and any(item.relevance.task == "match" and item.relevance.score >= 0.62 for _, item in selected)
        reason = None if sufficient else ("no_task_matched_candidates" if raw else "no_candidates")
        return RetrievalResult(query, candidates, rejected, docs, sufficient, reason, context)

    def _expand(self, selected, expected_task, state, query) -> list[SearchResult]:
        result: list[SearchResult] = []
        seen: set[tuple[str, str]] = set()
        for hit, evaluated in selected:
            source = str((hit.metadata or {}).get("source") or hit.source)
            related = [hit]
            getter = getattr(self.source, "article", None)
            if self.expand_chunks and callable(getter) and evaluated.document_id:
                related += getter(evaluated.document_id)
            for fragment in related:
                meta = normalize_metadata({**(fragment.metadata or {}), "text": fragment.text})
                fragment_task = meta.get("task_category")
                if expected_task and fragment_task and fragment_task != expected_task:
                    continue
                if fragment is not hit and expected_task:
                    section = str(meta.get("section") or "")
                    evidence_terms = _TASK_EVIDENCE.get(expected_task, ())
                    if not _SAFETY_SECTION.search(section) and not any(term in fragment.text.casefold() for term in evidence_terms):
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
