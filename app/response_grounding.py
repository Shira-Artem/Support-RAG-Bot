"""Local repair of a response using only the evidence already sent to the model.

Validation findings apply to statements, except fiscal safety findings, which
invalidate the whole workflow. No additional generation or retrieval is done.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Callable

from app.dialogue_state import words

ROLE_WORD = r'\bрол(?:ь(?:ю)?|и|ей|ям|ями|ях)\b'

def normalize(text: str) -> str:
    text = re.sub(r"[‐‑‒–—−]", "-", text.casefold().replace("ё", "е"))
    text = re.sub(r"\be[ -]?mail\b", "email", text)
    return re.sub(r"\s+", " ", text).strip()


def statements(text: str) -> list[str]:
    parts = re.split(r"\n+|(?<=[.!?])\s+(?=[А-ЯЁA-Z0-9«])", text)
    result = []
    for part in parts:
        part = re.sub(r"^\s*(?:[-*]\s+|\d+[.)]\s*)", "", part).strip()
        if part and not re.fullmatch(r"\d+[.)]?", part):
            result.append(part)
    return result


# Action families are separate from role capabilities. Creating an account,
# editing an account, and granting a specific privilege are different claims.
ACTION_FAMILIES = {
    "create": r"созда\w*|добав\w*|приглас\w*|приглаш\w*",
    "assign": r"назнач\w*|присва\w*|присво\w*",
    "edit": r"измен\w*|редакт\w*|менять|помен\w*",
    "input": r"введ\w*|ввод\w*|введите|укаж\w*|указыв\w*|заполн\w*|зада\w*",
    "save": r"сохран\w*",
    "notification": r"получ\w*.{0,30}(?:письм\w*|уведомлен\w*)|(?:письм\w*|уведомлен\w*).{0,30}(?:прид[её]т|отправ\w*)",
    "search": r"поиск\w*|найти|найд\w*",
    "filter": r"отбира\w*|фильтр\w*|сортир\w*",
    "configure": r"настро\w*",
    "connect": r"подключ\w*|соедин\w*",
    "reset": r"сброс\w*|восстанов\w*",
    "click": r"нажм\w*|клик\w*|щелк\w*",
    "choose": r"выбер\w*|отмет\w*",
}
OPERATION_FAMILY = {
    "add_employee": "create", "add": "create", "assign_role": "assign",
    "create_role": "create",
    "assign": "assign", "change_permissions": "edit", "change": "edit",
    "search": "search", "configure": "configure", "connect": "connect",
    "reset_password": "reset",
    "click": "click",
}
PERMISSION_TERMS = {
    "view": r"просм[ао]тр\w*|смотр\w*|чтени\w*",
    "edit": r"измен\w*|менять|редактир\w*",
    "settings": r"настро\w*",
    "reports": r"отч[её]т\w*",
    "cash_registers": r"касс\w*",
    "receipts": r"чек\w*",
}


def permission_clauses(text: str):
    """Keep the polarity of each capability, rather than one 'не' per answer."""
    for clause in re.split(r"[,;]|\bно\b", text, flags=re.I):
        claims = {name for name, pattern in PERMISSION_TERMS.items() if re.search(pattern, clause, re.I)}
        if claims:
            yield claims, bool(re.search(r"\bне\b|\bбез\b|запре\w*|недоступ\w*", clause, re.I))


def has_action(text: str, family: str) -> bool:
    return bool(re.search(ACTION_FAMILIES[family], text, re.I))


_ROLE_TARGET = re.compile(
    r"\bрол\w*|\bпользовател\w*|\bсотрудник\w*|\bдоступ\w*|\bправ\w*",
    re.I,
)


def _action_supported(claim: str, evidence: str, family: str) -> bool:
    """Match ordinary paraphrases without merging unrelated procedures.

    In access workflows, Russian speakers use «выбрать роль» and «назначить
    роль» for the same documented operation.  That equivalence is deliberately
    limited to role/user/access targets; «выбрать кассу» must not become proof
    of an assignment action.
    """
    if has_action(evidence, family):
        return True
    if family not in {"choose", "assign"} or not _ROLE_TARGET.search(claim):
        return False
    alternate = "assign" if family == "choose" else "choose"
    return bool(_ROLE_TARGET.search(evidence) and has_action(evidence, alternate))


def _action_object_supported(claim: str, source: str, family: str) -> bool:
    """Do not borrow a verb from a neighbouring workflow's object."""
    if family == "save":
        objects = re.findall(r"сохран\w*\s+(?:нов\w*\s+)?([а-яёa-z]+)", claim, re.I)
        for obj in objects:
            if not re.search(r"сохран\w*\s+(?:нов\w*\s+)?" + re.escape(obj), source, re.I):
                return False
    return True


def statements_equivalent(left: str, right: str) -> bool:
    """Detect a sourced paraphrase already present in the answer.

    Exact matching is insufficient for ordinary UI paraphrases: ``откройте
    раздел`` and ``перейдите в раздел`` are different strings but the same
    action.  The threshold is applied only when the action family or the UI
    nature also agrees, so adjacent unique steps are retained.
    """
    left_normalized, right_normalized = normalize(left), normalize(right)
    if not left_normalized or not right_normalized:
        return False
    left_actions = {family for family in ACTION_FAMILIES if has_action(left_normalized, family)}
    right_actions = {family for family in ACTION_FAMILIES if has_action(right_normalized, family)}
    if left_normalized == right_normalized:
        return True
    if left_normalized in right_normalized or right_normalized in left_normalized:
        if (left_actions or right_actions) and left_actions != right_actions:
            return False
        return True
    left_numbers = set(re.findall(r"(?<!\w)\d+(?:[.,]\d+)?(?!\w)", left_normalized))
    right_numbers = set(re.findall(r"(?<!\w)\d+(?:[.,]\d+)?(?!\w)", right_normalized))
    if left_numbers != right_numbers:
        # A release, amount, date, or fiscal identifier makes an otherwise
        # similar-looking statement materially different.
        return False
    left_terms, right_terms = _content_terms(left_normalized), _content_terms(right_normalized)
    if not left_terms or not right_terms:
        return False
    overlap = len(left_terms & right_terms) / min(len(left_terms), len(right_terms))
    shared_action = bool(left_actions & right_actions) and left_actions == right_actions
    shared_interface = bool(_INTERFACE_REFERENCE.search(left_normalized)
                             and _INTERFACE_REFERENCE.search(right_normalized))
    interface_duplicate = (shared_interface and overlap >= 0.68
                           and bool(left_actions) == bool(right_actions)
                           and left_actions == right_actions)
    return (shared_action and overlap >= 0.55) or interface_duplicate


def deduplicate_statements(items: list[str]) -> list[str]:
    """Keep the first wording while removing only semantic duplicates."""
    unique = []
    for item in items:
        if not any(statements_equivalent(item, existing) for existing in unique):
            unique.append(item)
    return unique


def _relation_supported(claim: str, source_clauses: list[str]) -> bool:
    """Require outcome and access relations, not just their shared nouns.

    A source can mention ``права`` while saying nothing about a user logging in
    or receiving those rights.  Such a noun overlap must not validate a
    postcondition added by the model.
    """
    positive = " ".join(source_clauses)
    if re.search(r"\bвойд\w*|\bзайд\w*", claim, re.I) and not re.search(
            r"\bвойд\w*|\bзайд\w*|\bвход\w*", positive, re.I):
        return False
    if re.search(r"\bполуч\w*.{0,40}\b(?:прав\w*|доступ\w*)|"
                 r"\b(?:прав\w*|доступ\w*).{0,40}\bполуч\w*", claim, re.I):
        if not re.search(r"\bполуч\w*.{0,40}\b(?:прав\w*|доступ\w*)|"
                         r"\b(?:прав\w*|доступ\w*).{0,40}\bполуч\w*", positive, re.I):
            return False
    return True


def has_named_role(text: str) -> bool:
    return bool(re.search(r'(?i:' + ROLE_WORD + r'\s+)(?:[«"“]|[А-ЯЁA-Z])', text))


_EVIDENCE_LIMIT_SECTION = re.compile(
    r"^(?:ограничен(?:ия|ие)|границ|важн(?:ое|ая) огранич|предупреж|"
    r"когда нужен специалист|передать специалист|эскалац|применимост|"
    r"безопасност|граница подтверждения)$",
    re.I,
)
_EXPLICIT_LIMITATION = re.compile(
    r"не\s+(?:подтвержд|устанавлива|зада[её]т|содерж|перенос|выполня|выдава|"
    r"обеща|подменя|доказыва|описан|указан|раскрыт|следует)|"
    r"\b(?:нельзя|необходим(?:о|а)|требуется|потребуется|обратитесь|"
    r"проверить актуальност|проверить совместимост|доступ(?:а| к) нет)\b|"
    r"\b(?:только|не выполняйте|не создавайте|не удаляйте|не меняйте)\b",
    re.I,
)
_NON_EVIDENCE_LINE = re.compile(r"^(?:#|источник:|https?://|\[источник:)", re.I)
_EDITORIAL_EVIDENCE_LINE = re.compile(
    r"^(?:область применения|вопрос (?:пользователя|клиента)|"
    r"что проверено|не обещать\b|цель документа|назначение документа)",
    re.I,
)
_FACT_STOPWORDS = {
    "это", "есть", "для", "при", "после", "перед", "через", "можно", "нужно", "следует",
    "будет", "быть", "этот", "эта", "эти", "того", "который", "которая", "которые",
    "чтобы", "если", "или", "также", "сервис", "инструкция", "клиент", "клиента",
    "в", "во", "на", "по", "из", "к", "от", "до", "и", "а", "но", "не", "ни",
    "у", "за", "как", "что", "где", "какой", "какая", "какие", "ли", "же",
    "тип",
    "раздел", "дополнительн", "услови", "затем", "через", "меню",
}
_CLAIM_SYNONYMS = {
    "сумм": "amount", "стоим": "amount", "размер": "amount", "amount": "amount",
    "способ": "method", "метод": "method", "вид": "method", "тип": "method",
    "отфильтровать": "filter", "отбирать": "filter",
    "оплат": "payment", "платеж": "payment", "расчет": "payment", "расчета": "payment",
    "чек": "receipt", "чека": "receipt", "чеков": "receipt",
    "период": "period", "дата": "date", "дат": "date",
    "номер": "number", "номеру": "number", "фн": "fn", "фискальн": "fn",
    "пользовател": "user", "сотрудник": "user", "учетн": "account", "запис": "account",
    "фн": "fn", "фд": "fd", "фп": "fp", "офд": "ofd", "1с": "1c",
    "перейдите": "navigate", "перейти": "navigate", "откройте": "navigate",
    "выберите": "choose", "задайте": "input", "введите": "input",
    # Common equivalent wording for delivery checks and status questions.
    "статус": "transfer", "передач": "transfer", "передан": "transfer",
    "передано": "transfer", "передачи": "transfer", "передачу": "transfer",
    "провер": "verify", "проверьте": "verify", "проверить": "verify",
    "убедитесь": "verify",
}
_SHORT_TECHNICAL_TERMS = {"фн", "фд", "фп", "офд", "1с", "эдо"}
_PROCEDURE_VERB = re.compile(
    r"\b(?:откро(?:йте|ть)|перейд(?:ите|ти)|нажм(?:ите|ать)|выбер(?:ите|ать)|"
    r"введ(?:ите|ите|ён|енный)|укаж(?:ите|ать)|зада(?:йте|ть)|заполн(?:ите|ить)|"
    r"сохран(?:ите|ить)|созда(?:йте|ть)|добав(?:ьте|ить)|назнач(?:ьте|ить)|"
    r"уточн(?:ите|ить)|проверьте|проверить|сверьте|сверить|определите|"
    r"выясните|выяснить|отбира(?:ть|йте)|найд(?:ите|ти)|используйте|"
    r"подключ(?:ите|ить)|включ(?:ите|ить)|отмет(?:ьте|ить)|выда(?:йте|ть)|"
    r"получ(?:ите|ить)|настро(?:йте|ить)|потребуется)\b",
    re.I,
)
_INTERFACE_REFERENCE = re.compile(
    r"(?:→|\b(?:маршрут|раздел|меню|вкладк|поле|кнопк|список|форма|"
    r"интерфейс)\b|\b(?:откро\w*|перейд\w*|нажм\w*|выбер\w*)\s+[«\"“])",
    re.I,
)


def evidence_kind(sentence: str, section: str = "", metadata: dict | None = None) -> str:
    """Classify a source sentence without turning warnings into procedures.

    A warning heading is only a hint: sections such as ``Безопасная
    диагностика`` contain real read-only checks. Explicit negative or
    escalation wording always wins over action verbs, so a limitation cannot
    become a customer step merely because it contains ``проверить``.
    """
    metadata = metadata or {}
    section_name = normalize(section).strip(" .:-")
    role = str(metadata.get("chunk_role") or "").casefold()
    limitation_section = bool(re.match(
        r"^(?:ограничен(?:ия|ие)|границ|важн(?:ое|ая) огранич|предупреж|"
        r"когда нужен специалист|передать специалист|эскалац|применимост|"
        r"безопасност|граница подтверждения)(?:\s*/.*)?$",
        section_name, re.I,
    ))
    limitation_text = bool(_EXPLICIT_LIMITATION.search(sentence))
    starts_limitation = bool(re.match(
        r"^\s*(?:не\b|нельзя\b|источник\b.*\bне\b|развернут\w*|"
        r"для задачи\b.*\bспециалист\b)", sentence, re.I,
    ))
    mixed_procedure = bool(_PROCEDURE_VERB.search(sentence)) and not starts_limitation
    if (limitation_section
            or (limitation_text and not mixed_procedure)
            or (role == "warning" and section_name != "безопасная диагностика")):
        return "limitation"
    if _INTERFACE_REFERENCE.search(sentence):
        return "interface"
    if _PROCEDURE_VERB.search(sentence) or re.search(r"(?:^|\s)\d+[.)]\s*", sentence):
        return "procedure"
    return "fact"


def _content_terms(text: str) -> set[str]:
    terms = set()
    for token in re.findall(r"[a-zа-яё0-9]+", normalize(text)):
        if token in _FACT_STOPWORDS or (len(token) < 3 and token not in _SHORT_TECHNICAL_TERMS
                                        and not any(ch.isdigit() for ch in token)):
            continue
        # A small suffix fold handles ordinary Russian inflections without
        # treating broad semantic similarity as proof.
        stem = re.sub(r"(?:иями|ями|ами|ого|ему|ыми|ими|ее|ей|ам|ям|ах|ях|ов|ев|ом|ем|ой|ый|ая|ое|ые|ую|юю|и|ы|а|я|е|у|ю)$", "", token)
        stem = _CLAIM_SYNONYMS.get(stem, stem)
        if stem not in _FACT_STOPWORDS:
            terms.add(stem)
    return terms


_VERSION_RE = re.compile(r"(?<!\w)\d+\.\d+(?:\.\d+){1,2}(?!\w)")


def _version_binding_supported(claim: str, evidence_results=()) -> bool:
    """Keep a release bound to the product/configuration that owns it.

    A sentence can mention both 1С and DirectBank while the card metadata says
    that the release belongs to 1С:Бухгалтерии.  Word overlap alone would
    incorrectly allow ``версия DirectBank 3.0.148``.  The metadata check is
    deliberately conservative and only rejects an explicit competing owner;
    an unqualified ``версия 3.0.148`` remains valid.
    """
    versions = _VERSION_RE.findall(claim)
    if not versions:
        return True
    owner_match = re.search(
        r"(?:верси\w*|релиз\w*)\s+(?P<owner>[^,.;:()\d]{2,60}?)\s*"
        r"(?:v?\s*)?\d+\.\d+(?:\.\d+){1,2}"
        r"|(?P<owner_before>[^,.;:()\d]{2,60}?)\s+(?:верси\w*|релиз\w*)\s*"
        r"(?:v?\s*)?\d+\.\d+(?:\.\d+){1,2}",
        claim, re.I,
    )
    if not owner_match:
        return True
    owner = normalize(owner_match.group("owner") or owner_match.group("owner_before"))
    if not owner:
        return True
    for result in evidence_results or ():
        metadata = getattr(result, "metadata", None) or {}
        declared = str(metadata.get("version") or "")
        if not any(version in declared for version in versions):
            continue
        product = normalize(" ".join(str(metadata.get(key) or "")
                                     for key in ("software", "model", "service")))
        # DirectBank is an exchange service in this corpus, while the version
        # field is attached to the 1С configuration.  The same shape also
        # protects other service/product pairs when their metadata is explicit.
        owner_tokens = set(_content_terms(owner))
        product_tokens = set(_content_terms(product))
        if owner_tokens and not owner_tokens <= product_tokens:
            return False
    return True


def _interface_configuration_binding_supported(claim: str, evidence_raw: str) -> bool:
    """Do not equate a simple/full UI with a simple/full configuration."""
    claim_configuration = re.search(r"\b(прост\w*|полн\w*)\s+конфигурац\w*\b", claim, re.I)
    claim_interface = re.search(r"\b(прост\w*|полн\w*)\s+(?:интерфейс\w*|режим\w*)\b", claim, re.I)
    source_sentences = statements(evidence_raw)
    if claim_configuration and not any(
            re.search(r"\b" + re.escape(claim_configuration.group(1)) + r"\w*\s+конфигурац\w*\b", sentence, re.I)
            for sentence in source_sentences):
        return False
    if claim_interface and not any(
            re.search(r"\b" + re.escape(claim_interface.group(1)) + r"\w*\s+(?:интерфейс\w*|режим\w*)\b", sentence, re.I)
            for sentence in source_sentences):
        return False
    return True


def _positive_evidence_clauses(evidence_raw: str, evidence_results=(), *,
                              include_limitations: bool = False) -> list[str]:
    """Return source clauses that can support a positive customer claim.

    A limitation may repeat the requested label (for example, ``отчёты``) to
    say that the permission is *not* confirmed.  Treating the whole context as
    positive evidence would turn that warning into proof for the opposite
    instruction.  Prefer result metadata when available; the lexical fallback
    keeps callers that only provide a context string conservative as well.
    """
    clauses = []
    if evidence_results:
        visible = normalize(evidence_raw)
        for result in evidence_results:
            metadata = getattr(result, "metadata", None) or {}
            section = str(metadata.get("section") or "")
            for sentence in statements(getattr(result, "text", "")):
                if (normalize(sentence) not in visible
                        or (not include_limitations
                            and evidence_kind(sentence, section, metadata) == "limitation")):
                    continue
                clauses.extend(part.strip() for part in re.split(r"\b(?:а не|но)\b", sentence, flags=re.I)
                               if part.strip())
        if clauses:
            return clauses
    for sentence in statements(evidence_raw):
        if (sentence.startswith(("[Источник:", "Источник:", "#"))
                or (not include_limitations and evidence_kind(sentence) == "limitation")):
            continue
        clauses.extend(part.strip() for part in re.split(r"\b(?:а не|но)\b", sentence, flags=re.I)
                       if part.strip())
    return clauses


def claim_supported(claim: str, evidence: str, *, evidence_results=()) -> bool:
    """Conservative local check for a paraphrased factual statement.

    Quoted interface labels and numbers must be present literally. Other claims
    need both predicate/action support and substantial overlap of their concrete
    terms; semantic similarity alone is never treated as evidence.
    """
    evidence_raw = evidence
    claim, evidence = normalize(claim), normalize(evidence)
    if not claim:
        return True
    if not _version_binding_supported(claim, evidence_results):
        return False
    if not _interface_configuration_binding_supported(claim, evidence_raw):
        return False
    if claim in evidence:
        return True
    positive_source_clauses = _positive_evidence_clauses(evidence_raw, evidence_results)
    positive_evidence = normalize(" ".join(positive_source_clauses))
    labels = re.findall(r"[«\"“]([^»\"”]{2,80})[»\"”]", claim)
    if any(normalize(label) not in positive_evidence for label in labels):
        return False
    numbers = re.findall(r"(?<!\w)\d+(?:[.,]\d+)?(?!\w)", claim)
    if any(number not in evidence for number in numbers):
        return False
    claim_terms = _content_terms(claim)
    if not claim_terms:
        return True
    action_families = [family for family in ACTION_FAMILIES
                       if has_action(claim, family)]
    claim_negated = bool(re.search(r"\bне\b|\bбез\b|недоступ\w*|запре\w*", claim, re.I))
    source_clauses = positive_source_clauses
    if claim_negated:
        # Explicit document boundaries are valid evidence for a negative
        # claim, while remaining unavailable as proof for the opposite action.
        source_clauses = _positive_evidence_clauses(
            evidence_raw, evidence_results, include_limitations=True)
    compatible_raw = [item for item in source_clauses
                      if bool(re.search(r"\bне\b|\bбез\b|недоступ\w*|запре\w*", item, re.I)) == claim_negated]
    if not _relation_supported(claim, compatible_raw):
        return False
    compatible = [normalize(item) for item in compatible_raw]
    evidence_text = " ".join(compatible)
    evidence_terms = _content_terms(evidence_text)
    overlap = len(claim_terms & evidence_terms) / len(claim_terms)
    action_supported = all(_action_supported(claim, evidence_text, family)
                           and _action_object_supported(claim, evidence_text, family)
                           for family in action_families)
    # Technical identifiers such as FN are relation-sensitive: a separate
    # source mention cannot be combined with a receipt-search claim. Require
    # them in the same source paragraph, with matching polarity.
    critical_terms = claim_terms & {"fn", "fd", "fp"}
    other_claim_terms = claim_terms - critical_terms
    critical_supported = (not critical_terms or any(
        critical_terms <= _content_terms(item)
        and bool(other_claim_terms & _content_terms(item)) for item in compatible_raw))
    return action_supported and critical_supported and overlap >= 0.40


def evidence_statements(results, context: str, *, limit: int = 4,
                        request: str | None = None) -> list[dict]:
    """Return source statements actually included in the model context.

    Metadata can label provenance and coverage, but cannot create factual
    content: every returned statement must also occur verbatim in the context.
    """
    visible = normalize(context)
    request_terms = _content_terms(request or "")
    candidates, seen = [], set()
    order = 0
    for result in results:
        metadata = result.metadata or {}
        section = str(metadata.get("section") or "")
        for sentence in statements(result.text):
            sentence = re.sub(r"^>\s*", "", sentence.strip())
            key = normalize(sentence)
            if (not key or key in seen or key not in visible or sentence == section
                    or _NON_EVIDENCE_LINE.match(sentence)
                    or _EDITORIAL_EVIDENCE_LINE.match(sentence)
                    or sentence.endswith("?")
                    or len(sentence.split()) < 2):
                continue
            kind = evidence_kind(sentence, section, metadata)
            sentence_terms = _content_terms(sentence)
            overlap = len(request_terms & sentence_terms)
            # A partial answer must address the current question, not merely
            # occur in an article selected for the same service. Metadata is a
            # gate; concrete wording in the statement is still required.
            if request_terms and not overlap:
                continue
            priority = overlap * 10 + (4 if kind == "procedure" else 3 if kind == "interface"
                                       else 2 if kind == "fact" else 1)
            candidates.append((priority, order, {
                "source": result.source,
                "document_id": metadata.get("document_id"),
                "section": section or None,
                "kind": kind,
                "text": sentence,
            }))
            order += 1
            seen.add(key)
    # Select the most question-specific statements, then restore their source
    # order so multi-step extracts remain readable.
    chosen = sorted(candidates, key=lambda item: (-item[0], item[1]))[:limit]
    return [item[2] for item in sorted(chosen, key=lambda item: item[1])]


def unsafe_operation_issue(text: str) -> str | None:
    """Recognize high-risk fiscal operations independently of retrieved text."""
    patterns = (
        ("закрыть архив ФН", r"(?:закрыть|закройте|закрывайте|закрыти\w*|заверш\w*).{0,35}архив\w*|фн.{0,25}архив\w*.{0,35}(?:закрыть|закрой|закры|заверш)\w*"),
        ("перерегистрировать ККТ", r"(?:перерегистрир\w*|перерегистрац\w*).{0,50}\b(?:ккт|касс\w*)\b|\b(?:ккт|касс\w*).{0,50}перерегистрир\w*"),
        ("заменить ФН", r"(?:заменить|замените|заменяйте|снимите|установите).{0,40}(?:\bфн\b|фискальн\w+\s+накопител\w*)|(?:\bфн\b|фискальн\w+\s+накопител\w*).{0,40}(?:заменить|замените|заменяйте|снимите|установите)"),
        ("закрыть смену", r"(?:закройте|закрыть|закрывать|нужно закрыть|необходимо закрыть).{0,30}смен\w*"),
        ("снять ККТ с учёта", r"снять.{0,40}(?:ккт|касс\w*).{0,40}(?:уч[её]т|регистрац)"),
    )
    for name, pattern in patterns:
        if re.search(pattern, text, re.I):
            return name
    return None


def instruction_issue(answer: str, context: str) -> str | None:
    """Check a concrete action, not the percentage of shared sentence words.

    Neutral mentions of an action (e.g. a question about available settings) are
    not instructions. Named UI labels and permissions have their own checks.
    """
    actionable = re.search(
        r"создайте|добавьте|пригласите|назначьте|присвойте|измените|редактируйте|"
        r"введите|укажите|заполните|сохраните|получит|получат|прид[её]т|будет отправлено",
        answer, re.I,
    )
    if not actionable:
        return None
    for family in ("create", "assign", "edit", "input", "save", "notification"):
        supported = has_action(context, family) or (family == 'assign' and has_named_role(context))
        if has_action(answer, family) and not supported:
            return "unsupported_instruction"
    return None


@dataclass
class ResponseRepair:
    text: str
    mode: str
    removed: list[dict] = field(default_factory=list)
    retained: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)


def _replacement_evidence(removed: list[dict], evidence: list[dict], state) -> list[dict]:
    """Choose source fragments for rejected statements, not for the answer.

    Each rejected model statement gets at most two nearby source candidates.
    This prevents an unrelated warning or a whole article from being appended
    merely because one button/parameter failed validation.
    """
    selected, seen = [], set()
    for rejected in removed:
        rejected_terms = _content_terms(rejected.get("text", ""))
        reason = str(rejected.get("reason") or "")
        ranked = []
        for order, item in enumerate(evidence):
            kind = item.get("kind", "fact")
            if kind == "limitation":
                continue
            item_terms = _content_terms(item.get("text", ""))
            overlap = len(rejected_terms & item_terms)
            score = overlap * 10
            if reason.startswith("unsupported_ui_label"):
                score += 4 if kind == "interface" else 0
            elif reason == "unsupported_role_or_permissions":
                score += 4 if kind in {"procedure", "interface"} else 0
            elif reason in {"unsupported_claim", "procedural_details_not_grounded"}:
                score += 3 if kind in {"procedure", "interface"} else 0
            if state.operation in {"assign_role", "change_permissions"}:
                score += 2 if kind in {"procedure", "interface"} else 0
            ranked.append((score, -order, item))
        for score, _, item in sorted(ranked, reverse=True, key=lambda value: (value[0], value[1]))[:2]:
            if score <= 0:
                continue
            key = normalize(item["text"])
            if key not in seen:
                selected.append(item)
                seen.add(key)
    return selected


def _unique_action_fragment(candidate: str, retained: list[str]) -> str | None:
    """Extract only the extra action from a source sentence sharing a route."""
    candidate_labels = {normalize(label) for label in re.findall(r"[«\"“]([^»\"”]{2,200})[»\"”]", candidate)}
    if not candidate_labels or not _INTERFACE_REFERENCE.search(candidate):
        return None
    for existing in retained:
        existing_labels = {normalize(label) for label in re.findall(r"[«\"“]([^»\"”]{2,200})[»\"”]", existing)}
        if not candidate_labels & existing_labels or not _INTERFACE_REFERENCE.search(existing):
            continue
        clauses = [part.strip() for part in re.split(r"[,;]", candidate) if part.strip()]
        extra = [part for part in clauses
                 if any(has_action(part, family) and not has_action(existing, family)
                        for family in ACTION_FAMILIES)]
        if not extra:
            continue
        prefix = re.split(r"\b(?:откройте|перейдите|нажмите|выберите)\b",
                          clauses[0], maxsplit=1, flags=re.I)[0].strip()
        text = " ".join(extra).strip()
        if prefix:
            text = prefix + ": " + text[:1].upper() + text[1:]
        return text.rstrip(" .") + "."
    return None


def _evidence(results, context: str, operation: str) -> list[dict]:
    """Pick substantive statements from the exact context, with provenance.

    Matching retrieval metadata is not sufficient: a statement cut off by the
    context budget must never be used to reconstruct a customer answer.
    """
    source = normalize(context)
    family = OPERATION_FAMILY.get(operation)
    candidates = []
    seen = set()
    for result in results:
        metadata = result.metadata or {}
        section = str((result.metadata or {}).get("section") or "")
        operations = set(metadata.get("operations") or ())
        if operations:
            allowed = {
                "add_employee": {"add_employee"},
                "assign_role": {"assign_role", "create_role", "configure_role"},
                "change_permissions": {"change_permissions", "edit_user", "assign_role",
                                         "create_role", "configure_role"},
            }.get(operation)
            if allowed is not None and not (operations & allowed):
                continue
            if (operation == "change_permissions" and "add_employee" in operations
                    and not operations & {"change_permissions", "edit_user"}):
                # The add-user article also mentions assigning a pre-created
                # role, but it is not evidence for editing an existing user.
                continue
        for sentence in statements(result.text):
            if (sentence == section or sentence.startswith(("#", "Источник:", "http", "[Источник:"))
                    or sentence.endswith("?") or len(sentence.split()) < 4):
                continue
            kind = evidence_kind(sentence, section, metadata)
            if kind == "limitation":
                # Coverage limits are rendered separately in customer-safe
                # wording.  Never use the document's warning prose as a step.
                continue
            key = normalize(sentence)
            if key in seen or key not in source:
                continue
            seen.add(key)
            # A replacement may be an interface route or a documented check,
            # not only a verb from the normalized operation family.  This is
            # what keeps a confirmed period/filter step when the model added
            # one unsupported button in the same workflow.
            matches = (kind in {"interface", "procedure"}
                       or (family is None and kind == "fact")
                       or (family is not None and has_action(sentence, family))
                       or (family == 'assign' and has_named_role(sentence)))
            if not matches:
                continue
            candidates.append({"source": result.source, "document_id": metadata.get("document_id"),
                               "section": section or None, "kind": kind, "text": sentence})
    return candidates[:8 if operation in {"search", "assign_role", "change_permissions"} else 6]


def needs_procedure_grounding(answer: str, context: str, state, results) -> bool:
    """A supported verb does not prove its parameters or promised outcomes.

    For concrete documented workflows, use source actions when the model adds
    procedural wording we cannot establish locally. This is an extractive
    rendering policy, not a claim that every paraphrase is a hallucination.
    Role recommendations use the separate role/capability checks instead.
    """
    if state.operation not in OPERATION_FAMILY or state.operation == 'assign_role':
        return False
    if not _evidence(results, context, state.operation):
        return False
    procedural = any(has_action(answer, family) for family in ACTION_FAMILIES)
    return procedural and any(not claim_supported(s, context, evidence_results=results)
                              for s in statements(answer))


def unconfirmed_search_parameters(state, context: str) -> list[str]:
    """Detect absent field evidence, never infer that a feature is impossible.

    Only parameter spans bound by the dialogue analyser are inspected. Periods
    ('за ...') are values, not requested filter fields. A mention is not positive
    proof of support; it merely prevents a local absence claim. The model must
    still ground any positive instruction in the document.
    """
    if state.operation != 'search':
        return []
    context_words = set(words(context))
    missing = []
    for parameter in state.parameters:
        tokens = words(parameter.value)
        if tokens[:1] != ['по']:
            continue
        field_words = [token for token in tokens[1:] if token not in {'номер', 'номеру', 'номера'}]
        if field_words and not any(token in context_words for token in field_words):
            missing.append(parameter.value)
    return missing


def search_scope_response(state, context: str, results) -> ResponseRepair | None:
    missing = unconfirmed_search_parameters(state, context)
    if not missing:
        return None
    evidence = _evidence(results, context, 'search')
    limitations = ('В найденной инструкции не подтверждён поиск ' + '; '.join(missing)
                   + '. Это не означает, что такой поиск в сервисе недоступен.')
    text = limitations + ('\n' + '\n'.join(item['text'] for item in evidence) if evidence else '')
    return ResponseRepair(text, 'documented_search_scope', evidence=evidence)


def _navigation_reference(results, context: str, evidence: list[dict]) -> dict | None:
    """Recover a unique section from the same article, never from another hit."""
    sources = {item['source'] for item in evidence}
    labels = {}
    for result in results:
        if result.source not in sources:
            continue
        for match in re.finditer(r'\bв разделе [«"]([^»"]+)[»"]', result.text, re.I):
            if normalize(match.group()) in normalize(context):
                labels[normalize(match[1])] = {'source': result.source, 'text': match.group(),
                                             'label': match[1], 'kind': 'navigation'}
    if len(labels) == 1:
        item = next(iter(labels.values()))
        if normalize(item['label']) not in normalize(' '.join(e['text'] for e in evidence)):
            return item
    return None


def repair_response(answer: str, issue: str, *, context: str, request: str,
                    service: str | None, state, results, check: Callable,
                    limitation: Callable) -> ResponseRepair:
    """Keep independent valid statements and reconstruct mixed steps from RAG.

    This is intentionally extractive, not a second model asked to judge itself.
    It can recover documented actions but cannot invent a missing UI or matrix.
    """
    if issue.startswith("unsupported_dangerous_operation:"):
        return ResponseRepair(
            "Это ответственная фискальная операция. Не выполняйте её самостоятельно; передайте вопрос специалисту по ККТ.",
            "fiscal_escalation", removed=[{"text": answer, "reason": issue, "scope": "workflow"}],
        )
    removed, retained = [], []
    for sentence in statements(answer):
        reason = check(sentence, context, request, service)
        if reason:
            removed.append({"text": sentence, "reason": reason, "scope": "statement"})
        else:
            retained.append(sentence)
    evidence = [item for item in _evidence(results, context, state.operation)
                if not check(item["text"], context, request, service)]

    role_issue = any(item["reason"] == "unsupported_role_or_permissions" for item in removed)
    if state.operation == "assign_role" and role_issue and not evidence:
        # Without source statements there is nothing safe to reconstruct.
        return ResponseRepair(limitation(service, roles=True), "documented_scope", removed, [], evidence)

    family = OPERATION_FAMILY.get(state.operation)
    # Replace only rejected statements. Previously every non-literal sentence
    # in an otherwise useful workflow was discarded, which turned one unknown
    # button into a generic navigation answer. Source statements are local
    # replacements, never a mechanical rewrite of the whole answer.
    if evidence:
        removed_families = {
            candidate for item in removed
            for candidate in ACTION_FAMILIES
            if has_action(item["text"], candidate)
        }
        replacement_evidence = _replacement_evidence(removed, evidence, state)
        for item in replacement_evidence:
            item_kind = item.get("kind", "fact")
            if item_kind not in {"interface", "procedure", "fact"}:
                continue
            if (removed_families and family and item_kind == "fact"
                    and not any(has_action(item["text"], candidate)
                                for candidate in removed_families)):
                continue
            replacement_text = _unique_action_fragment(item["text"], retained) or item["text"]
            if not any(statements_equivalent(replacement_text, existing) for existing in retained):
                retained.append(replacement_text)
    if retained:
        navigation = _navigation_reference(results, context, evidence) if family else None
        if navigation:
            # The source supplies the parent section when the operation says
            # only 'the menu of this record'. Avoid a duplicated model step.
            navigation_text = f"Откройте раздел «{navigation['label']}»."
            if not any(statements_equivalent(navigation_text, existing) for existing in retained):
                retained.insert(0, navigation_text)
                evidence.append(navigation)
        retained = deduplicate_statements(retained)
        text = "\n".join(retained)
        if role_issue and state.operation in {"assign_role", "change_permissions"}:
            has_capability_matrix = any(
                has_named_role(item["text"]) and list(permission_clauses(item["text"]))
                for item in evidence
            )
            if not has_capability_matrix:
                service_name = service or "этого сервиса"
                text += ("\n\nДля " + service_name +
                         ": Конкретная роль и её полномочия для ваших требований "
                         "в источнике не подтверждены.")
        if state.operation == "change_permissions" and not any(
                re.search(r'\bправ(?:а|ам|ами|ах)?\b|доступ\w*|рол[ьи]', item['text'], re.I) for item in evidence):
            text += "\n\nОтдельный порядок настройки прав в этой инструкции не указан."
        elif (issue == 'unsupported_technical_claim'
              and re.search(r"ошибк\w*|неисправ\w*|не работает|не переда\w*|код\s*\d+",
                            request, re.I)):
            text += "\n\nПричина неисправности по этим сведениям не подтверждена."
        return ResponseRepair(text, "partial_answer", removed, retained, evidence)
    return ResponseRepair(limitation(service, roles=role_issue), "no_supported_statements", removed, [], evidence)
