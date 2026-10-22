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


def has_named_role(text: str) -> bool:
    return bool(re.search(r'(?i:' + ROLE_WORD + r'\s+)(?:[«"“]|[А-ЯЁA-Z])', text))


_EVIDENCE_LIMIT_SECTION = re.compile(
    r"огранич|границ|важно|предупреж|безопас|когда нужен|перед выполн|"
    r"услови|применим|неподтверж|что не описано",
    re.I,
)
_NON_EVIDENCE_LINE = re.compile(r"^(?:#|источник:|https?://|\[источник:)", re.I)
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


def claim_supported(claim: str, evidence: str) -> bool:
    """Conservative local check for a paraphrased factual statement.

    Quoted interface labels and numbers must be present literally. Other claims
    need both predicate/action support and substantial overlap of their concrete
    terms; semantic similarity alone is never treated as evidence.
    """
    evidence_raw = evidence
    claim, evidence = normalize(claim), normalize(evidence)
    if not claim:
        return True
    if claim in evidence:
        return True
    labels = re.findall(r"[«\"“]([^»\"”]{2,80})[»\"”]", claim)
    if any(normalize(label) not in evidence for label in labels):
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
    source_clauses = []
    for sentence in statements(evidence_raw):
        source_clauses.extend(part.strip() for part in re.split(r"\b(?:а не|но)\b", sentence, flags=re.I)
                              if part.strip())
    compatible_raw = [item for item in source_clauses
                      if bool(re.search(r"\bне\b|\bбез\b|недоступ\w*|запре\w*", item, re.I)) == claim_negated]
    compatible = [normalize(item) for item in compatible_raw]
    evidence_text = " ".join(compatible)
    evidence_terms = _content_terms(evidence_text)
    overlap = len(claim_terms & evidence_terms) / len(claim_terms)
    action_supported = all(has_action(evidence_text, family) for family in action_families)
    # Technical identifiers such as FN are relation-sensitive: a separate
    # source mention cannot be combined with a receipt-search claim. Require
    # them in the same source paragraph, with matching polarity.
    critical_terms = claim_terms & {"fn", "fd", "fp"}
    other_claim_terms = claim_terms - critical_terms
    critical_supported = (not critical_terms or any(
        critical_terms <= _content_terms(item)
        and bool(other_claim_terms & _content_terms(item)) for item in compatible_raw))
    return action_supported and critical_supported and overlap >= 0.40


def evidence_statements(results, context: str, *, limit: int = 12) -> list[dict]:
    """Return source statements actually included in the model context.

    Metadata can label provenance and coverage, but cannot create factual
    content: every returned statement must also occur verbatim in the context.
    """
    visible = normalize(context)
    found, seen = [], set()
    for result in results:
        metadata = result.metadata or {}
        section = str(metadata.get("section") or "")
        for sentence in statements(result.text):
            sentence = sentence.strip()
            key = normalize(sentence)
            if (not key or key in seen or key not in visible or sentence == section
                    or _NON_EVIDENCE_LINE.match(sentence) or sentence.endswith("?")
                    or len(sentence.split()) < 2):
                continue
            kind = "limitation" if (_EVIDENCE_LIMIT_SECTION.search(section)
                                    or re.search(r"\bне\b|неподтверж|не описан|не указан", sentence, re.I)) else "fact"
            if re.search(r"(?:раздел|кнопк|пункт|меню|поле)\s+[«\"“][^»\"”]+[»\"”]", sentence, re.I):
                kind = "interface"
            elif re.search(r"сумм|оплат|кассир|период|номер|поиск|фильтр", sentence, re.I):
                kind = "search"
            elif any(has_action(sentence, family) for family in ACTION_FAMILIES):
                kind = "procedure"
            found.append({"source": result.source,
                          "document_id": metadata.get("document_id"),
                          "section": section or None, "kind": kind, "text": sentence})
            seen.add(key)
            if len(found) >= limit:
                return found
    return found


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
        section = str((result.metadata or {}).get("section") or "")
        if re.search(r"вопрос клиента|когда нужен|применимость|перед выполнением", section, re.I):
            continue
        for sentence in statements(result.text):
            if (sentence == section or sentence.startswith(("#", "Источник:", "http", "[Источник:"))
                    or sentence.endswith("?") or len(sentence.split()) < 4):
                continue
            key = normalize(sentence)
            if key in seen or key not in source:
                continue
            seen.add(key)
            matches = (family is None or has_action(sentence, family)
                       or (family == 'assign' and has_named_role(sentence)))
            if not matches:
                continue
            candidates.append({"source": result.source, "text": sentence})
    return candidates[:3]


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
    return procedural and any(not claim_supported(s, context) for s in statements(answer))


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
    if state.operation == "assign_role" and role_issue:
        # Account creation does not answer which role satisfies a permission
        # requirement. Do not turn the creation procedure into role advice.
        documented_roles = [item['text'] for item in evidence if has_named_role(item['text'])]
        if documented_roles:
            text = '\n'.join(documented_roles)
        else:
            text = ("Инструкция описывает назначение роли сотруднику. " if evidence else "")
            text += limitation(service, roles=True)
        return ResponseRepair(text, "documented_scope", removed, [], evidence)

    family = OPERATION_FAMILY.get(state.operation)
    if family or state.intent in {'access', 'credentials'}:
        # A mixed procedural answer must not retain unchecked field names or
        # promises from neighbouring steps. Reconstruct its actions from the
        # source; retain only literal evidence and independent, named navigation.
        grounded = []
        evidence_text = normalize(' '.join(item['text'] for item in evidence))
        for sentence in retained:
            labels = re.findall(r'[«"]([^»"]+)[»"]', sentence)
            navigation = bool(re.match(r'(?:Перейдите|Откройте)\b', sentence, re.I))
            other_action = any(has_action(sentence, name) for name in ACTION_FAMILIES)
            named_navigation = (navigation and labels and not other_action
                                and all(normalize(label) in normalize(context) for label in labels)
                                and any(normalize(label) not in evidence_text for label in labels))
            if normalize(sentence) in normalize(context) or named_navigation:
                grounded.append(sentence)
            else:
                removed.append({'text': sentence, 'reason': 'workflow_rebuilt_from_source', 'scope': 'workflow_statement'})
        retained = grounded

    # An invalid step can contain several dependent actions. Use the source
    # statement in its place, rather than deleting a word inside that workflow.
    if evidence:
        if (family and not any(has_action(s, family) for s in retained)) or not retained:
            retained.extend(item["text"] for item in evidence)
    if retained:
        navigation = _navigation_reference(results, context, evidence) if family else None
        if navigation:
            # The source supplies the parent section when the operation says
            # only 'the menu of this record'. Avoid a duplicated model step.
            retained = [s for s in retained if normalize(navigation['label']) not in normalize(s)]
            retained.insert(0, f"Откройте раздел «{navigation['label']}».")
            evidence.append(navigation)
        text = "\n".join(dict.fromkeys(retained))
        if role_issue and state.operation in {"assign_role", "change_permissions"}:
            text += "\n\n" + limitation(service, roles=True)
        elif state.operation == "change_permissions" and not any(
                re.search(r'\bправ(?:а|ам|ами|ах)?\b|доступ\w*|рол[ьи]', item['text'], re.I) for item in evidence):
            text += "\n\nОтдельный порядок настройки прав в этой инструкции не указан."
        elif issue == 'unsupported_technical_claim':
            text += "\n\nПричина неисправности по этим сведениям не подтверждена."
        return ResponseRepair(text, "partial_answer", removed, retained, evidence)
    return ResponseRepair(limitation(service, roles=role_issue), "no_supported_statements", removed, [], evidence)
