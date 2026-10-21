"""Local repair of a response using only the evidence already sent to the model.

Validation findings apply to statements, except fiscal safety findings, which
invalidate the whole workflow. No additional generation or retrieval is done.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Callable

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
    "input": r"введ\w*|ввод\w*|введите|укаж\w*|указыв\w*|заполн\w*",
    "save": r"сохран\w*",
    "notification": r"получ\w*.{0,30}(?:письм\w*|уведомлен\w*)|(?:письм\w*|уведомлен\w*).{0,30}(?:прид[её]т|отправ\w*)",
    "search": r"поиск\w*|найти|найд\w*|фильтр\w*",
    "configure": r"настро\w*",
    "connect": r"подключ\w*|соедин\w*",
    "reset": r"сброс\w*|восстанов\w*",
}
OPERATION_FAMILY = {
    "add_employee": "create", "add": "create", "assign_role": "assign",
    "assign": "assign", "change_permissions": "edit", "change": "edit",
    "search": "search", "configure": "configure", "connect": "connect",
    "reset_password": "reset",
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
    return procedural and any(normalize(s) not in normalize(context) for s in statements(answer))


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
    if family:
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
        if role_issue:
            text += "\n\n" + limitation(service, roles=True)
        elif state.operation == "change_permissions" and not any(
                re.search(r'\bправ(?:а|ам|ами|ах)?\b|доступ\w*|рол[ьи]', item['text'], re.I) for item in evidence):
            text += "\n\nОтдельный порядок настройки прав в этой инструкции не указан."
        elif issue == 'unsupported_technical_claim':
            text += "\n\nПричина неисправности по этим сведениям не подтверждена."
        return ResponseRepair(text, "partial_answer", removed, retained, evidence)
    return ResponseRepair(limitation(service, roles=role_issue), "no_supported_statements", removed, [], evidence)
