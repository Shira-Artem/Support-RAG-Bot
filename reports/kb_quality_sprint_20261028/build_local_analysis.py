"""Generate privacy-filtered KB sprint artifacts from local source files.

This script never copies or logs source messages. Raw text exists only in memory.
Run with --messages pointing to the private TXT supplied by the workspace.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import unicodedata

import yaml


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
KNOWN_TERMS = {
    "эвотор", "evotor", "aqsi", "акси", "атол", "atol", "атолонлайн",
    "1с", "егаис", "бифит", "bifit", "нева", "меркурий", "штрих", "штрихм",
    "платформаофд", "офд", "фн", "ффд", "ккт", "фнс", "честныйзнак",
    "тспиот", "пиот", "директбанк", "маркировка", "эквайринг", "эдо", "упд",
    "сбис", "диадок", "астрал", "гисмт", "гис", "мт", "усн", "ндс", "енс",
    "ттн", "qr", "api", "xml", "фд", "фп", "фпд", "цто", "бухгалтерия",
}
COMMON_START = {
    "здравствуйте", "добрый", "доброе", "привет", "мне", "у", "как", "нужно",
    "не", "касса", "кассу", "офд", "атол", "эвотор", "aQsi", "1с", "помогите",
    "подскажите", "вопрос", "про", "в", "на", "что", "можно", "когда", "сколько",
    "хочу", "сделайте", "почему", "есть", "ищу", "нужна", "нам", "уточните",
    "проверьте", "подскажите", "здравствуйте!", "добрый день", "добрый вечер",
}
COMMON_NAMES = {
    "арина", "татьяна", "женя", "жени", "евгений", "александр", "александра",
    "алексей", "анна", "мария", "марина", "ольга", "иван", "сергей", "елена",
    "наталья", "екатерина", "андрей", "дмитрий", "михаил", "юлия", "ирина",
    "светлана", "виктория", "анастасия", "павел", "николай", "роман", "денис",
    "алёна", "алена", "алина", "борис", "валентина", "владимир", "галия",
    "юрий", "вадим", "любовь", "вероника", "ксения", "дарья", "максим",
    "вера", "петр", "пётр", "маргарита", "игорь", "артем", "артём", "степан",
    "леонид", "лидия", "лариса", "галина", "виталий", "алекс", "элина",
}
SAFE_SENTENCE_STARTS = {
    "здравствуйте", "добрый", "доброе", "привет", "мне", "у", "как", "нужно",
    "не", "касса", "кассу", "офд", "атол", "эвотор", "aqsi", "1с", "помогите",
    "подскажите", "вопрос", "про", "в", "на", "что", "можно", "когда", "сколько",
    "хочу", "сделайте", "почему", "есть", "ищу", "нужна", "нам", "уточните",
    "проверьте", "скиньте", "пришлите", "надо", "а", "и", "по", "для", "вчера",
    "сегодня", "оплатить", "оформить", "открыть", "закрыть", "сдать", "проверить",
    "работает", "пока", "нужен", "нужны", "требуется", "при", "если", "после",
    "ккт", "кассовая", "сколько", "какой", "какая", "какие", "чем", "куда", "зачем",
    "пожалуйста", "с", "мой", "моя", "оплата", "фн", "эдо", "бифит", "чек", "банк",
    "сделать", "сформировать", "включить", "необходимо", "отправьте", "обновить",
    "подключить", "ищем", "восстановить", "закончился", "купил", "установить",
}

TOPICS = [
    ("edo_upd", r"эдо|упд|сбис|диадок|астрал"),
    ("cash_register", r"касс|ккт|чек|смен"),
    ("marking_chestny_znak", r"маркир|честн.{0,8}знак|гис.?мт|datamatrix|мрц"),
    ("bank_acquiring", r"банк|эквайр|карт.{0,8}оплат|оплат.{0,8}карт|альфа|псб|сбер|тиньк"),
    ("evotor", r"эвотор|эвот"), ("ofd", r"офд"), ("fn", r"фн\b|фискальн.{0,15}накоп"),
    ("tax_reporting", r"декларац|патент|страхов|ндс|усн|енс|налог"),
    ("account_access_renewal", r"продл|доступ|логин|парол|покупк|срок действия|личн.{0,8}кабинет"),
    ("ts_piot", r"пиот|пи от"), ("bifit", r"бифит|bifit"), ("atol", r"атол|atol"),
    ("egais", r"егаис|егас"), ("1c", r"1с|1c|бухгалтерия"),
    ("shtrih_m", r"штрих"), ("neva", r"нева"), ("mercury", r"меркур"),
    ("aqsi", r"aqsi|акси"), ("qr_payments", r"qr|куар|кьюар"),
    ("support_contact_complaint", r"не отвечает|не связал|обещал|специалист|инженер|поддержк|жалоб"),
    ("consumer_goods_operations", r"сканер|товар|продаж|возврат|склад|номенклатур"),
]
INTENTS = [
    ("urgent_complaint", r"срочно|жалоб|не отвечает|не связал|обещал|не могу ждать|претенз"),
    ("technical_diagnostics", r"не работ|ошиб|не печат|не перед|не подключ|не закры|не проходит|не отправ|не видит|не груз|не пробив|не считыв|нет связи|сбой|проблем|завис|истек|закончился|не принимает|не открывает|не отображ"),
    ("setup_connection", r"настро|подключ|установ|интеграц|эквайринг"),
    ("registration_renewal", r"регистрац|продл|оформ|открыть ип|снять с регистрац|закрыть ип|активац"),
    ("accounting_document_process", r"декларац|ндс|усн|патент|страхов|выписк|упд|эдо|отчет|бухгалтер|налог|платеж|накладн|егаис|ттн"),
    ("personal_status_or_action", r"провер|статус|срок действия|покупк|доступ|закрой|пришл|отправ|подпиш|сформир|свяж|проверь"),
    ("information_faq", r"\?|сколько|когда|какой|какая|какие|как|что|почему|можно ли|нужно ли|чем"),
    ("information_faq", r"\?|сколько|когда|какой|какая|какие|как|что|почему|можно ли|нужно ли|чем"),
    ("personal_status_check", r"провер|статус|срок действия|покупк|доступ|отобраз|список|мой |моя "),
    ("employee_action", r"закрой|пришл|отправ|подпиш|сформир|свяж|сделай|передай|позвони|оформите"),
]


def scrub(value: str) -> str:
    text = unicodedata.normalize("NFKC", value)
    text = re.sub(r"(?i)\S*@\S+", " [EMAIL] ", text)
    text = re.sub(r"(?i)https?://\S+|www\.\S+", " [URL] ", text)
    text = re.sub(r"(?i)(парол\w*|токен\w*|секрет\w*|код\s+подтверждения)\s*[:=]?\s*[^,;\\]+", r" \1 [SECRET] ", text)
    text = re.sub(r"(?i)\b(?:инн|снилс|паспорт|телефон|тел\.?|номер телефона|р/с|сч[её]т\s*№|карта\s*№|email|адрес)\s*[:№=-]?\s*[^,;\\]*", " [SENSITIVE] ", text)
    text = re.sub(r"(?i)\b(?:ип|ооо|зао|пао|ао)\s+[^,;\\]+", " [ORG] ", text)
    text = re.sub(r"(?i)\b(?:эцп|электронн\w* подпись)\b[^,;\\]*", " [EDS] ", text)
    text = re.sub(r"(?<!\w)\+?\d[\d\s()/-]{2,}\d(?!\w)", " [ID] ", text)
    text = re.sub(r"\d+", " [NUMBER] ", text)
    text = re.sub(r"(?i)\b(?:ул\.?|улица|проспект|пр-т|дом|кв\.?|адрес|пропиской)\b[^,;\\]*", " [ADDRESS] ", text)
    text = re.sub(r"(?i)(?:меня зовут|фио\s*[:=]?|имя\s*[:=]?|сотрудник\s*[:=]?)\s*[А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+){0,5}", " [PERSON] ", text)
    text = re.sub(r"(?i)\b(?:фамилия|имя клиента|контактное лицо)\b[^,;\\]*", " [PERSON] ", text)
    # Mask known names and non-whitelisted proper nouns. Unrecognized sentence-
    # initial proper nouns cause the example row to be excluded below.
    tokens = re.findall(r"\S+", text)
    cleaned = []
    at_sentence_start = True
    unverified_entity = False
    for token in tokens:
        bare = re.sub(r"[^\wА-Яа-яЁё-]", "", token).lower()
        if bare in COMMON_NAMES:
            cleaned.append("[PERSON]")
        elif re.search(r"(?:овна|евна|ович|евич|ична)$", bare):
            cleaned.append("[PERSON]")
        else:
            first = re.sub(r"^[^А-ЯЁ]+", "", token)
            title_case = bool(re.match(r"^[А-ЯЁ][а-яё-]{2,}$", first))
            if title_case and bare not in KNOWN_TERMS and bare not in SAFE_SENTENCE_STARTS:
                if at_sentence_start:
                    cleaned.append("[UNVERIFIED_ENTITY]")
                    unverified_entity = True
                else:
                    cleaned.append("[ENTITY]")
            else:
                cleaned.append(token.lower())
        at_sentence_start = token.endswith((".", "!", "?"))
    text = " ".join(cleaned)
    text = re.sub(r"(?:\s*\[(?:PERSON|ENTITY)\]\s*){2,}", " [ENTITY] ", text)
    text = re.sub(r"\s+", " ", text).strip(" \\")
    # Some records contain personal/contact payloads that are safer to exclude
    # from the example dataset altogether; their topic still contributes to counts.
    if unverified_entity or re.search(r"(?i)паспорт|снилс|инн|номер телефона|\bтелефон\b|почт\w*|пропис|реквизит|закрыт\w* ключ", value):
        return ""
    return text[:500]


def classify(text: str, rules: list[tuple[str, str]]) -> str:
    for label, pattern in rules:
        if re.search(pattern, text, re.I):
            return label
    return rules[-1][0]


def normalize(text: str) -> str:
    return re.sub(r"[^а-яёa-z0-9]+", " ", text.lower()).strip()


def write_catalog() -> dict:
    old_path = ROOT / "reports/knowledge_base_audit_20261028/document_catalog.csv"
    old = {}
    if old_path.exists():
        with old_path.open(encoding="utf-8-sig", newline="") as stream:
            old = {row.get("path", ""): row for row in csv.DictReader(stream)}
    fields = ["path", "document_id", "title", "status", "service", "category", "task_category",
              "manufacturer", "model", "model_yaml_state", "version", "version_yaml_state",
              "published_at", "published_at_yaml_state", "verified_at", "source_url", "source_type",
              "body_chars", "has_numbered_steps", "mentions_result", "quality_class", "old_catalog_misaligned"]
    overrides = {
        "data/knowledge/atol_online/ofd/what-is-ofd.md": "faq_needs_scope_refresh",
        "data/knowledge/platformaofd/ofd/lkk-receipt-search.md": "sufficient_faq_and_lookup_procedure",
        "data/knowledge/platformaofd/ofd/lkk-receipt-fns-status.md": "sufficient_faq_needs_error_code_for_action",
        "data/knowledge/atol_online/integration/api-test.md": "sufficient_api_test_faq_not_incident_procedure",
        "data/knowledge/atol_online/receipts/receipt-journal-export.md": "procedure_source_refresh_time_limits",
        "data/knowledge/evotor/fn/fn-231.md": "source_update_required",
        "data/knowledge/evotor/fn/fn-234.md": "partial_instruction_source_update_required",
        "data/knowledge/evotor/fn/fn-235.md": "partial_instruction_source_update_required",
        "data/knowledge/aqsi_devices/peripherals/scanner.md": "partial_instruction",
        "data/knowledge/aqsi_online/receipts/partial-refund.md": "source_update_required_complete_path_now_verified",
        "data/knowledge/aqsi_online/receipts/full-refund.md": "procedure_needs_path_and_financial_boundary_review",
        "data/knowledge/1c/bank/directbank-all-accounts.md": "partial_scoped_procedure",
        "data/knowledge/atol_online/integration/api-test.md": "sufficient_api_test_faq_not_incident_procedure",
    }
    rows = []
    misaligned = 0
    for path in sorted((ROOT / "data/knowledge").rglob("*.md")):
        content = path.read_text(encoding="utf-8-sig")
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        meta = yaml.safe_load(parts[1]) or {}
        rel = path.relative_to(ROOT).as_posix()
        previous = old.get(rel, {})
        compare = ["model", "version", "status", "source_url", "source_type", "published_at", "collected_at", "verified_at", "source_checked_at"]
        mismatch = any((None if previous.get(key, "").strip().lower() in {"", "null", "none"} else previous.get(key, "").strip()) !=
                       (None if meta.get(key) in (None, "") else str(meta.get(key)).strip()) for key in compare)
        misaligned += mismatch
        body = parts[2]
        rows.append({
            "path": rel, "document_id": meta.get("document_id"), "title": meta.get("title"),
            "status": meta.get("status"), "service": meta.get("service"), "category": meta.get("category"),
            "task_category": meta.get("task_category"), "manufacturer": meta.get("manufacturer"),
            "model": meta.get("model"), "model_yaml_state": field_state(meta, "model"),
            "version": meta.get("version"), "version_yaml_state": field_state(meta, "version"),
            "published_at": meta.get("published_at"), "published_at_yaml_state": field_state(meta, "published_at"),
            "verified_at": meta.get("verified_at"), "source_url": meta.get("source_url"),
            "source_type": meta.get("source_type"), "body_chars": len(body),
            "has_numbered_steps": bool(re.search(r"(?m)^\s*\d+[.)]\s", body)),
            "mentions_result": bool(re.search(r"(?i)результат|ожидаем|если .*то|при этом", body)),
            "quality_class": overrides.get(rel, "not_individually_reassessed"),
            "old_catalog_misaligned": mismatch,
        })
    with (OUT / "corrected_document_catalog.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    return {"documents": len(rows), "old_catalog_misaligned_rows": misaligned}


def field_state(meta: dict, field: str) -> str:
    if field not in meta: return "absent"
    if meta[field] is None: return "yaml_null_or_empty"
    if meta[field] == "": return "quoted_empty_string"
    return "populated"


def write_messages(message_path: Path) -> dict:
    raw = message_path.read_text(encoding="utf-8-sig")
    source = [line.strip() for line in raw.splitlines() if line.strip()]
    normalized_raw = [normalize(re.sub(r"[^а-яёa-z0-9]+", " ", line.lower())) for line in source]
    counts = Counter(normalized_raw)
    exact_unique = list(counts)
    fuzzy_parent = list(range(len(exact_unique)))

    def find(i: int) -> int:
        while fuzzy_parent[i] != i:
            fuzzy_parent[i] = fuzzy_parent[fuzzy_parent[i]]
            i = fuzzy_parent[i]
        return i

    def union(a: int, b: int) -> None:
        a, b = find(a), find(b)
        if a != b: fuzzy_parent[b] = a

    for i, left in enumerate(exact_unique):
        if len(left) < 24 or len(set(left.split())) < 4: continue
        for j in range(i + 1, len(exact_unique)):
            right = exact_unique[j]
            if len(right) < 24 or abs(len(left)-len(right))/max(len(left), len(right)) > .27: continue
            lset, rset = set(left.split()), set(right.split())
            if len(rset) < 4 or len(lset & rset)/len(lset | rset) < .54: continue
            if SequenceMatcher(None, left, right, autojunk=False).ratio() >= .86: union(i, j)
    fuzzy_groups = len({find(i) for i in range(len(exact_unique))})

    safe_rows = {}
    topic_counts = Counter(); topic_unique = defaultdict(set)
    intent_counts = Counter()
    for line, key in zip(source, normalized_raw):
        matched_topics = [name for name, pattern in TOPICS if re.search(pattern, line, re.I)]
        for topic in matched_topics:
            topic_counts[topic] += 1; topic_unique[topic].add(key)
        intent_tags = [name for name, pattern in INTENTS if re.search(pattern, line, re.I)]
        if not intent_tags: intent_tags = ["unclassified_by_rules"]
        intent = intent_tags[0]
        for tag in intent_tags: intent_counts[tag] += 1
        safe = scrub(line)
        if not safe: continue
        fingerprint = normalize(safe)
        if not fingerprint: continue
        entry = safe_rows.setdefault(fingerprint, {"text": safe, "source_occurrences": 0,
                                                   "topics": matched_topics, "intents": intent_tags,
                                                   "intent": intent,
                                                   "expected_behavior": expected_behavior(intent)})
        entry["source_occurrences"] += 1
    with (OUT / "anonymized_evaluation_dataset.jsonl").open("w", encoding="utf-8") as stream:
        for item in safe_rows.values(): stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    with (OUT / "topic_frequency.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["cluster", "message_frequency_including_repeats", "distinct_normalized_variants"])
        for name, _ in TOPICS:
            if topic_counts[name]: writer.writerow([name, topic_counts[name], len(topic_unique[name])])
    with (OUT / "intent_frequency.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["primary_intent", "messages_including_repeats"])
        intent_order = ["technical_diagnostics", "information_faq", "setup_connection",
                        "registration_renewal", "personal_status_or_action", "personal_status_check",
                        "employee_action", "accounting_document_process", "urgent_complaint",
                        "unclassified_by_rules"]
        for name in intent_order:
            if intent_counts[name]: writer.writerow([name, intent_counts[name]])
    return {"messages": len(source), "normalized_unique": len(exact_unique),
            "repeat_excess": len(source)-len(exact_unique), "exact_duplicate_groups": sum(n > 1 for n in counts.values()),
            "messages_in_duplicate_groups": sum(n for n in counts.values() if n > 1),
            "max_repeat_count": max(counts.values()), "conservative_fuzzy_groups": fuzzy_groups,
            "safe_unique_examples": len(safe_rows), "topic_counts": dict(topic_counts),
            "intent_counts": dict(intent_counts)}


def expected_behavior(intent: str) -> str:
    return {
        "urgent_complaint": "offer_specialist_promptly; collect only the minimum issue summary",
        "technical_diagnostics": "clarify_product_model_then_use_only_applicable_approved_kb; stop_if_no_confirmed_step",
        "setup_connection": "clarify_product_version_and_goal_then_use_applicable_approved_kb",
        "registration_renewal": "identify_service_and_authority; personal_status_or_change_requires_authorized_system_or_specialist",
        "accounting_document_process": "clarify_period_system_and_document; use approved source or accountant; do_not_submit_or_sign",
        "personal_status_or_action": "requires_authorized_crm_or_lk_integration_or_specialist; do_not_claim_status_from_kb",
        "employee_action": "requires_authority_and_external_system; offer specialist if no approved integration",
        "information_faq": "answer_from_approved_source_with_scope_and_limitations",
        "unclear": "ask_one_specific_clarifying_question_or_offer_specialist_if_urgent",
    }.get(intent, "manual_review")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages", required=True, type=Path, help="Private local TXT; never copied by this script")
    args = parser.parse_args()
    catalog = write_catalog()
    message_stats = write_messages(args.messages)
    (OUT / "analysis_metrics.json").write_text(json.dumps({"catalog": catalog, "messages": message_stats}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"catalog": catalog, "messages": {k: v for k, v in message_stats.items() if k not in {"topic_counts", "intent_counts"}}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
