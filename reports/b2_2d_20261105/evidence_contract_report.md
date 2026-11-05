# B2.2d — applicability and answer relevance, 05.11.2026

**IN_PROGRESS; quality gate NO-GO; not ready for the final ten holdout.** Candidate branch `codex/b22d-evidence-applicability` is separate from published `fb3aa6d922ca5d04f1eae91a5362723b605e692c`. u01/u02 are diagnostic regressions, not independent holdout. The remaining frozen ten were not run. d11 was used as an additional opposite-scope control, but it is a previously measured baseline case, not a new independent sample. Earlier results: [continuation report](continuation_20261105.md), [earlier published-runtime trace](bounded_live_20261105.json).

## Candidate and offline evidence

- The reducer retains an otherwise omitted substantive continuation as exact client text, without promoting it to a typed intent, operation, or outcome. The planner prompt explicitly treats it as unclassified text. [Saved-provider and Stage3 replay](applicability_replay_final_20261105.json) confirms the question reaches retrieval. A deterministic planner test selects the actual approved diagnostic section and produces the reconciliation/duplicate warning; this is an offline controlled result, not evidence of real model selection or SQLite E2E.
- Cross-category admission is allowed only for an approved diagnostic/check section containing both the exact observed symptom and the explicit object. Expansion and evidence filtering preserve this section-local condition. Draft, different symptom/object and mutation-operation controls reject it. The first attempt applied the bridge only in initial candidate selection: expansion dropped the section and h08 remained unavailable; [negative replay](applicability_first_replay_20261105.json) is retained. After the expansion/evidence fix, h08 reaches the applicable source; all normal service/model, source/SHA and safety checks remain.
- Explicit ordinary document exchange excludes sources whose title scopes their workflow to transport EPD, unless the request itself mentions transport. Explicit comparisons can inspect both. This is a directionally conservative scope rule, not a general claim that articles in these domains never intersect; false exclusions remain possible for mixed-domain documents.
- Up to 12 rather than 4 locally verified sections are available to the existing planner, so one four-section source no longer hides the second source. The existing planner is instructed to focus on the current question, distinguish workflow and product, avoid repeating the prior section, and preserve limitations. This adds no LLM call but increases prompt size; LIVE proves these instructions do not guarantee completeness.
- Information ranking uses the full current question as query context when a shorter model subgoal omits a distinguishing condition. For guarantee questions a relevant explicit limitation is prioritized over an adjacent positive fact. Saved u02 selection now finds the approved statement that third-party hubs have no guaranteed compatibility. This tests sentence selection, not an end-to-end live outcome. It is not a complete multi-goal or safety-context proof. u01 remains open: saved Understanding classified the suitability question as diagnosis; retrieval selected error articles and rejected the correct fiscal-drive article.

[Profile](evidence_contract_profile.log): 56 passed. [Full pytest](evidence_contract_full_pytest_final.log): 723 passed, 4 xfailed, 14 warnings. A first ranking test exposed that matching words starting with `не` treated “некоторых” as negation; the rule was narrowed to a separate negation/explicit limitation before the final run. The earlier full run preceded this final ranking change and does not substitute for the final run. No approved KB/index or production changes were made.

## LIVE AFTER

Actual `bot.handle_message`, current candidate, Groq, read-only Stage3, dedicated SQLite. [Full trace](evidence_contract_live.json) includes questions, answers, HTTP and usage, task frames, retrieval, scope and Planner where reached, checkpoint paths and before/after reopen state. Seven turns, 13 HTTP 200, **35 264 confirmed tokens**, no observed 429/403. All seven reopen comparisons true; seven pre-turn checkpoints plus conversations and expert isolated SQLite passed `quick_check`. All 35 runtime hashes match the trace and 270 KB file hashes match the prior protected receipt. Published production runtime was not changed. The last 10 holdout were not used. Historical confirmed usage for B2.2d including the earlier probe: 162 309 + 35 264 = **197 573**; previous failed 429 usage remains unknown.

### b01 / 1

**Вопрос:** В 1С:Бухгалтерии 3.0.207 банк отдельно списал деньги за возврат покупателю по карте. Какая операция для этого предусмотрена?

**Ответ:**

> Начиная с версии 3.0.207 в документе «Списание с расчётного счёта» появился вид операции «Возврат по эквайрингу». Он предназначен для случая списания банком денег за возврат по эквайрингу.
>
> Дополнительное условие источника (Передать бухгалтеру):
> Определение правильных проводок и разнесение комиссии при нетипичной схеме эквайринга.
>
> Источник: data/knowledge/1c/bank/acquiring-returns.md — Подтверждённое изменение

**Оценка:** Useful factual start; prior version also did this.

### b01 / 2

**Вопрос:** Банк списал отдельно, из следующего поступления ничего не удерживал. Что сверить, чтобы не отразить возврат дважды?

**Ответ:**

> Для этой задачи в «1С» не нашёл подтверждённой применимой инструкции в базе знаний. Можно оформить заявку специалисту кнопкой ниже; доставка сотруднику пока не настроена.

**Оценка:** F — false refusal; Understanding returned check and the correct approved diagnostic section was rejected by operation mismatch.

### h08 / 1

**Вопрос:** При приёмке УПД на Эвотор 7.3 появилось Unsupported document version. Что это может означать?

**Ответ:**

> Сообщение `Unsupported document version` может указывать на неподдерживаемый старый формат УПД. Ошибки электронной подписи, расхождения кодов и количеств, а также юридически значимое подписание спорных документов следует передавать специалисту по ЭДО. Не подписывайте УПД до проверки товара.
>
> Источник: data/knowledge/evotor/marking/receive-marked-upd-prereqs.md — Частые проблемы

**Оценка:** A for this turn — relevant format explanation and warning.

### h08 / 2

**Вопрос:** Товар ещё не сверяли. Можно уже подтвердить документ?

**Ответ:**

> Этот раздел инструкции уже приведён, а следующего подтверждённого шага для вашего случая не нашёл. Запросите специалиста кнопкой ниже.

**Оценка:** F — repeated selected section triggers refusal even though prior answer included the relevant warning.

### d10 / 1

**Вопрос:** В 1С:Бухгалтерии подпись есть, но мы с поставщиком у разных операторов ЭДО. Достаточно одной подписи для обмена УПД?

**Ответ:**

> Для работы 1С-ЭДО нужны подходящая электронная подпись, подключение к оператору ЭДО и согласованный электронный документооборот с контрагентом. В 1С предусмотрен помощник подключения.
>
> Дополнительное условие источника (Ограничение):
> Статья о подключении датируется прошлым периодом. Актуальность тарифов, договора и интерфейса нужно проверять на текущем сервисе; не обещать бесплатную отправку или совместимость всех операторов.
>
> Источник: data/knowledge/1c/edo/connect-1c-edo.md — Общие принципы

**Оценка:** B — ordinary EDO and limitations, but incomplete roaming detail.

### d10 / 2

**Вопрос:** Обмен нужен с разными операторами. Какие ещё параметры учёта подготовить для подключения?

**Ответ:**

> 1. Конфигурацию 1С и её релиз.
>
> Источник: data/knowledge/1c/edo/connect-1c-edo.md — Что уточнить перед инструкцией

**Оценка:** E/B — only one prerequisite was returned; the requested full set remains incomplete.

### d11 / 1

**Вопрос:** В 1С-ЭПД транспортный документ не отправляется: контрагент в хранилище не найден. Это лечится приглашением как для УПД?

**Ответ:**

> Для обмена электронными перевозочными документами (ЭПД), включая роуминг, приглашение контрагента не требуется: документ отправляется адресату. Оператор получателя должен быть включён в реестр операторов ГИС ЭПД Минтранса.
>
> Дополнительное условие источника (Важно):
> Правила приглашений для обычного ЭДО и транспортного ЭПД различаются. Нельзя смешивать эти процессы.
>
> Источник: data/knowledge/1c/edo/epd-vs-edo.md — Подтверждённое разъяснение

**Оценка:** A — transport rule and distinction; historical baseline control, not independent holdout.

## Remaining work

b01 is not end-to-end fixed: the real new observation `check` exposed a separate operation-compatibility rejection for the approved “Диагностика” section. The existing bank exception recognizes only a reviewed “Безопасная диагностика” section. Extending that exception to all similarly named sections would not establish that their full actions are safe/read-only; a section-level review/contract and negative mutation tests are needed before doing so. h08 follow-up needs a source-verified focused warning without replaying an entire already shown section. d10 follow-up needs all applicable independent prerequisites and the roaming boundary; m01 retains its unrelated escalation text. u01 is not corrected; u02 improvement has only offline evidence. Semantic multi-part coverage and warning selection remain unproven. Therefore this branch must not be characterized as completion of B2.2d or as ready for the untouched holdout or production. No quality percentage is inferred from these repeated diagnostic cases.
