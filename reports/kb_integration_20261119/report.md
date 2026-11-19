# KB B2 integration / Hubris LIVE — 19.11.2026

**Решение: KB merge в main BLOCKED.** Временное объединение сохранено локально в `codex/kb-b2-integration-20261119`, merge commit `4680aa0eac7eac2f612295ccd256f96846441e71`. История обеих сторон сохранена, конфликтов Git не было. В main оставлена прежняя KB. Production NO-GO, Experiment 2 Part A REVISE / A6 STOP; A7, Part B и Experiment 3 не начинались.

## Исходное состояние и архитектура

- До работы main и origin/main: `57e94e2554f6cfa32aeb4905bf48d3abd80135b5`; feature: `1b5280683ed922e67c41e119ba2743814c1ccdb5`; merge-base: `fb3aa6d922ca5d04f1eae91a5362723b605e692c`. Tracked tree был чистым; существующая `.worktrees/` не изменялась. Первый fetch успешен. Последующие fetch по SChannel, HTTP/1.1 и OpenSSL завершались TLS EOF; актуальность remote после первого fetch не выдумывается.
- Прочитаны README, master plan, последние записи PROJECT_STATE, runbook Hubris, retrieval/SQLite architecture, A6 и предыдущие LIVE-отчёты, handoff и реестры коллеги. Старые отчёты не использовались как доказательство работающего процесса.
- Telegram → `bot.handle_message` → модель Understanding и span-validation → SQLite / reducer-owned DialogueState, TaskFrame, проверки и контекст → Coordinator → Qdrant dense + BM25/RRF → фильтры approved, сервиса, модели, кода и операции → локальная сверка SHA/раздела → Planner и порядок технических шагов либо informational Selector/Composer → grounding/safety → Telegram. Социальный ответ и эскалация могут завершиться раньше поиска; общая память одна.
- Provider уже настроен в `.env`: Hubris `openai/gpt-oss-20b`, effort `low`. Но `.env` указывал Stage2 `knowledge_organized_stage2_20261022` и не включал SourceFirst/Coordinator/Composer. Для LIVE и ручного процесса использован явный process-only профиль, credentials не менялись. До запуска не было Python worker, Docker daemon/контейнер Qdrant были остановлены. Docker запущен; возобновлён именно существующий `rag-qdrant-1`, volume не пересоздавался.
- Известные ограничения main подтверждаются заново: ложные отказы, избыточные уточнения, выбор соседнего раздела, слабая смена предмета и readiness, узкий KB gap подписанного УПД в 1С. Ни main, ни кандидат не признаны готовыми для production.

## Что объединено во временном кандидате

Git diff feature относительно merge-base: **322 файла, +14 555 / −787**, включая **235 KB-путей**. Ветка не меняет app/bot pipeline, ingestion, retrieval или архитектуру: добавлены аудиты, реестры, draft-кандидаты и шесть утилит проверки. Изменения main в pipeline сохранены.

Фактическое сравнение загруженных документов с main: **229 карточек отличаются по полям; 221 — по body/content hash**, в том числе 169 остающихся approved и 52 draft. Разница с 235 raw-file changes объясняется форматированием/полями, которые loader не представляет. Поздний handoff коллеги про «24 файла, главным образом metadata» относится к последней локальной итерации на его ветке, а не ко всему diff с main. Нельзя принимать весь merge за metadata-only.

| Показатель | main | объединённая KB |
|---|---:|---:|
| Карточки / document_id | 269 | те же 269 |
| approved / draft | 206 / 63 | 204 / 65 |
| Все чанки | 934 | 1168 |
| Только approved чанки | 672 | 833 |
| Добавлено / удалено KB-путей, сменено ID | 0 | 0 |

В `draft` переведены `accounting/usn/usn-nds-exemption-2026.md` и `accounting/usn/usn-psn-income-2026.md`, `verified_at` очищен. Это снятие с клиентского поиска, а не утверждение нового налогового ответа. Четыре информационные карточки 1С лишились неподходящей operation; loader принимает пустые operations, но универсальная policy-совместимость не доказана. У aQsi integration изменены service/model/software/procedure scope: physical-device источник не должен разрешать cloud-процедуру. Два соответствующих теста всё ещё требуют старого cloud scope; их нужно разбирать как fixture drift, а не автоматически объявлять дефектом нового scope.

**52 внешних кандидата** остались draft вне `data/knowledge` и вне клиентского индекса. Validator кандидата: 52/52, 209 чанков, 0 errors/warnings. Исходные пять B2 drafts также не продвигались. Уникальность document_id, document body hash, chunk ID и отсутствие точных повторных чанков внутри approved-документа проверены. У всех карточек source_url заполнен. Semantic duplicates этим не исключены; у коллеги есть 16 overlap-пар и 19 сигналов разрыва слова при chunking. 269 card-review rows остаются warning, SME/content acceptance не закрыт, 17 P0 в аудите не означают 17 доказанных новых дефектов.

## Проверки и блокеры merge

- Интегрированный full pytest: **799 passed / 94 failed / 4 xfailed**, 256.83 s; [все ошибки](test_failures.json).
- Архив точного main: **880 passed / 12 failed / 4 xfailed**, 265.09 s. Десять ошибок общие с кандидатом. Две дополнительные ошибки архива — отсутствующий ignored 20-row evaluation fixture и отсутствие разрешения `langgraph` в архивном окружении. Первый fixture скопирован отдельно из существующего локального test input без изменения оригинала, единичный повтор прошёл. Это не превращает исходный полный запуск в PASS.
- **84 дополнительных failed test только у кандидата**; [поимённое сравнение](test_comparison.json). Они требуют triage: часть жёстко связана со старым текстом/heading, часть отражает изменение поведения. Тесты не переписаны и не заморожены ради зелёного результата.
- Schema/ingestion/index/quality contracts + receipt: **48 passed**. Отдельные receipt/Hubris/UTF-8 проверки после возврата в main: **27 passed**.
- Финальный full pytest рабочего main с его KB: **883 passed / 10 failed / 4 xfailed**, 244.87 s. Все десять failures уже присутствовали на исходном main. В рабочем окружении подтверждается ровно 84 дополнительных candidate-only failure.

Три контролируемых различия: все три соответствующих теста проходят на архивном main и падают с новой KB при том же app-коде:

1. `test_p02_directbank_diagnostics::test_rejected_actions_cannot_be_grounded_by_diagnostic_context`: `claim_supported` принимает «Измените настройки банковского обмена.» в диагностическом context, который раньше не разрешал это действие.
2. `test_source_first_dialogue_contract::test_information_composition_rejects_unsupported_claims_and_procedures`: `_validate_information_composition` принимает неподтверждённое «ОФД автоматически продлевает тариф кассы.» против расширенного approved-раздела.
3. `test_telegram_pilot_sqlite_replay::test_source_order_survives_sqlite_reopen_without_overriding_current_applicability`: ожидаемый следующий approved check заменяется `planner_could_not_select_safely`.

Это конкретные несовместимости данных и действующего контракта, достаточные для BLOCKED. Из них **не следует**, что эти две ошибочные фразы были сгенерированы в LIVE. Большая архитектурная переработка, ослабление safety, массовое снятие approved или подгонка под фразы не выполнялись. Код Understanding/retrieval/generation между вариантами одинаков; отличие runtime receipt на результаты этих проверок не влияет.

В candidate verifier обнаружен отдельный Windows-дефект: SHA manifest относится к LF Git blob, а `core.autocrlf=true` делает CRLF checkout CSV. Проверка теперь принимает только эквивалентное LF-представление и дополнительно сверяет исторический Git blob; baseline bytes/manifest не переписаны. После исправления 269/269 исторических хешей подтверждены, 69 текущих отличий от branch baseline, 0 смен ID, ровно два approved→draft.

Inherited whitespace warnings полного branch diff сохранены, ручной текст интерфейса 1С не форматировался. Diff собственных main-изменений прошёл `git diff --check`.

## Индексы и источники

Созданы **две новые коллекции**, только из approved документов, штатным `QdrantStore.index(..., remove_missing=False)` и существующей embedding-моделью:

- `knowledge_kb_b2_base_20261119`: green / 672, 206 approved документов;
- `knowledge_kb_b2_integrated_20261119`: green / 833, 204 approved документа.

Каждый point ID, text и весь payload сопоставлены с текущим Chunker; совпадение точное. Все прежние коллекции сохранили число точек, delete/recreate/switch alias не было. Клиентский LIVE читал их через ReadOnlyQdrant. Существующая Stage3 `knowledge_stage3_retrieval_20261022` также **побайтно совпала по 934 payload с main**, 672 approved points; это stronger evidence, чем одна green/count-проверка. Новая KB действительно загружена и участвовала в retrieval, что видно по selected source/section и ответу DirectBank. Не следует считать её активной коллекцией штатного бота: кандидат заблокирован.

[Полный инвентарь/изменённые поля/индексы](kb_inventory.json), [Stage3 verification](stage3_verification.json). Семь выбранных HTTP source checks: 1С, aQsi, Платформа ОФД — 200; четыре Evotor URL — 403, без успешного повторного чтения. [Детали](source_links.json). Успешный HTTP не удостоверяет все утверждения, 403 не означает отсутствующую статью. Полная повторная проверка всех 416 source-review URLs не заявляется.

## Настоящий Hubris LIVE

Реальный `bot.handle_message`, Understanding, reducer/SQLite, Coordinator, hybrid retrieval, Planner/Selector/Composer при достижении ветки. Изолированы только Telegram transport и хранилища. Synthetic user=42, отдельные диалоги и DB; клиентские данные не читались и не отправлялись. Профиль обоих вариантов одинаков: Hubris `openai/gpt-oss-20b` / low, SourceFirst, Coordinator, Composer on, отдельный selector flag off, без автоматических повторов LLM. Provider/model не менялись.

15 основных диалогов плюс два safety/context контроля: приветствие/small talk, ОФД, D01/D03/D04/D07/D08, чек Эвотор 6, 6 lite, DirectBank, physical/cloud aQsi, недостаток данных, специалист, архив ФН, отозванная налоговая карточка, EoU missing и FN234 с результатом проверки. Кандидатский первый блок остановился на transport error; D04 в следующем блоке также не дошёл до HTTP. Оставшиеся **разные** случаи выполнялись последовательно отдельно, без повторения этих неуспешных ходов и без конкурирующих pipelines. Ошибки сохранены в знаменателе.

| Измерение | main KB | новая KB |
|---|---:|---:|
| Сохранённые ходы | 28 | 27 |
| HTTP | 46×200 | 44×200 |
| Ошибочные ходы | 0 | 3, до HTTP |
| prompt / completion / total tokens | 75540 / 10532 / 86072 | 90594 / 9752 / 100346 |
| Reported cost, коп. | 58 | 60 |
| Сумма latency ходов | 227.072 s | 254.246 s |
| SQLite reopen equality | 28/28 | 27/27 |

Итого: **55 ходов, 90×HTTP 200, 186418 tokens, 118 коп. / 1.18 ₽ reported usage**. Ошибок HTTP 4xx/5xx в записанных вызовах нет. Три хода кандидата — Understanding transport failures D03/4, D04/1 и Selector ConnectTimeout налогового вопроса. До-HTTP попытки не имеют usage в capture; сумма не выдаётся за независимую сверку провайдерского биллинга. Latency — сумма внутри ходов, не время всей работы с загрузкой моделей и диагностикой.

Дословные вопросы/ответы/источники: [answers.md](answers.md). Походовые state before/after, Understanding, Coordinator, query, выбранные источники, scope, Planner, HTTP и usage: [live_summary.json](live_summary.json). Полные model request/response traces и SQLite остались ignored в `.local/kb-integration-20261119/live-*.json` и соответствующих `telegram-equivalent-*` каталогах root/архивного baseline; private JSON checksums включены в summary. Ключи не экспортированы; данные тестов синтетические. Лейблы provider в старой ветке ошибки `bot.py` могут быть Groq/OpenRouter; attribution здесь берётся из фактических Hubris HTTP calls и setup, а не из этого legacy ярлыка.

### Полезность — ручная оценка без слепой разметки

| Случай | Старая KB | Новая KB | Вывод |
|---|---|---|---|
| Small talk | Приветствие, затем отказ по KB | Отказ по KB уже на первой реплике, затем «Какой сервис?» | Универсальный разговор не улучшился. |
| Что такое ОФД | Отказ Selector | Правильное определение с source qualifier | Положительный пример; единичная stochastic пара не доказывает причинный общий выигрыш. |
| D01, интернет работает | Учёл интернет, просит модель | Соседний симптом «(!) ОФД»/24h, затем завершение вместо продвижения | Потеря полезности при продолжении; диагноз 24h клиентом не сообщён. |
| D03 неизвестный код | Непродуктивные уточнения | Уточнение, escalation, transport fail | Не исправлен; последний ход несопоставим. |
| D04 / отдельный FN234 контроль | Безопасная проверка даты/времени | D04 transport fail; в новом контрольном диалоге сразу responsible-operation refusal | Расширение раздела смешало полезный первый check и изменение даты; safety блокирует весь выбранный section. |
| D07 Эвотор 7.3 | Предупреждение про EoU вместо начала диагностики | Симптом вместо диагностического действия | Первый полезный шаг не получен. |
| Подписанный УПД / 1С | Уточнение, KB gap, безопасный отказ Planner | Материально то же | Узкий gap не заполнен внешними draft-кандидатами. |
| Копия Эвотор 6 / 6 lite | Отказы | Отказы | Не улучшилось. |
| DirectBank расписание | Общая возможность + условия | Настоящие исходные шаги UI и расписания | Конкретный KB-backed выигрыш: новые UI-пункты отсутствовали в старой карточке. В ответе нет явного порога версии 3.0.195; имеются опции автосоздания/проведения — полнота инструкции не равна разрешению для любой конфигурации. |
| aQsi physical/cloud | Без переноса процедуры | Без переноса процедуры | Scope сохранён, полезного ответа нет. |
| Недостаток сведений | Общий вопрос о желаемом результате | Более осмысленный запрос наблюдаемого результата без угадывания кода | Ограниченный conversational выигрыш, не доказан как следствие KB. |
| Специалист | Просит сначала описать вопрос | То же | Доставка не настроена; UI-confirmation покрыта существующими offline тестами, не реальной доставкой сотруднику. |
| Закрыть архив / EoU missing | Блокировка / нерезультативное уточнение | Блокировка / нерезультативное уточнение | В LIVE не выдана опасная фискальная процедура. |

**Полезность в целом не улучшена доказательно; release NO-GO.** Ни одного выполнения/публикации опасного фискального порядка не наблюдалось в этих 55 ответах. Это не доказательство общей безопасности: новая KB оставляет риск ложного grounding, а D01/D07 дают неприменённый к фактам симптом. Нельзя свести safety к отсутствию команд в этом маленьком наборе.

Старый A/B/C baseline **8 A / 24 B / 3 C на 35 вопросах** оценивал достаточность KB, а не эти ответы. Старый B+ аудит использовал другую 24-case выборку (13/9/2) и местами deterministic/oracle arms. A6 — отдельный 12-case holdout, опубликованные 5/12→3/12, с оговорками разметки; этот holdout не открывался заново целиком. Здесь другие единицы, состав, source content и провайдер по сравнению с частью Groq-отчётов. Пересчитывать прежние A/B/C или заявлять рост процента по этому диагностическому набору нельзя. Текущая matched comparison на одном Hubris лучше изолирует KB, но один последовательный sample на вопрос, неослеплённая оценка, transport loss и variance модели ограничивают причинность.

## Main, Telegram и откат

В main внесены только точность Hubris receipt (`model`/`reasoning_effort` вместо OpenRouter labels), параметры harness `--collection/--expected-points` с прежними defaults и один regression test receipt: commit `edac2274901e0bc543fb809b01fe4ad7397e1d1c`. Генерация ответов, KB и safety policy main не менялись. Отчёт и хронология сохраняются отдельным documentation commit. Интеграционная ветка не отправлена в remote; remote feature не менялась. **Обычный `git push origin main` завершился TLS handshake failure до публикации. Изменения остаются локальными, force push не применялся.** Последний подтверждённый origin/main — `57e94e2`; новое удалённое состояние после потери связи не подтверждено.

Telegram: **не работает; оба ограниченных штатных запуска завершились до polling на `getMe` NetworkError**. Оба прошли SQLite/Qdrant initialization; правильный receipt Hubris сохранён. Это не работающий бот. До запуска checkout lock был свободен; единственный успешный `getWebhookInfo` вернул 200 / no webhook / 0 pending. Локальные другие poller не обнаружены; существующий webhook не удалялся отдельной командой. Попытка verified TLS1.2 не помогла и не внесена в runtime. Проверка сертификатов не отключалась. Telegram connectivity и факт настоящего входящего пользовательского сообщения не подменяются mocked transport LIVE. На финальной проверке собственные launcher/worker процессы завершены; конкурирующий polling не оставлен.

Process-only ручной профиль: main + Stage3 / Hubris / low, три существующих tester IDs из `.env` без вывода значений, SourceFirst+Coordinator+Composer, отдельная SQLite и handoff outbox в `.local/kb-integration-20261119/manual/`, доставка специалисту off. `.env` не переписывался. Startup launcher и safe HTTP method/status capture: `.local/kb-integration-20261119/start_bot.py`; логи `.local/kb-integration-20261119/bot-*.log`, trace `manual/telegram-http.jsonl`. Этот trace не содержит token, Telegram URLs, message payload или клиентских IDs. [Безопасная startup-сводка](runtime_status.json).

Финальная read-only сверка через GitHub connector `compare(57e94e2, main)` вернула **identical / 0 ahead / 0 behind**: remote main по-прежнему `57e94e2554f6cfa32aeb4905bf48d3abd80135b5`. Доступ connector не означает, что локальный Git TLS transport заработал; публикация через иной API вместо запрошенного обычного push не выполнялась.

[15 ручных сообщений/диалогов и ожидаемые признаки](../../docs/MANUAL_TELEGRAM_20261119.md). При недоступном Telegram сначала восстановить доступ к `api.telegram.org`, затем запускать этот launcher. Не запускать второй экземпляр поверх занятого `.local/bot.lock`; при 409 остановить только собственный новый процесс. Нельзя обещать доставку специалисту без настроенного/согласованного получателя.

Откат данных не требуется: старые collections/SQLite сохранены, активная KB main не переключалась. Candidate доступен по `4680aa0`; его осмотр не требует изменения рабочего main. Диагностический main commit можно отменить обычным revert после остановки собственного worker; force push не нужен. Кандидатскую коллекцию сохраняем для воспроизводимого review, не удаляем.

## Следующий конкретный шаг

Разобрать 84 candidate-only failure на fixture drift и нарушения действующего контракта. Первые обязательные проверки — два ложных grounding допуска и безопасная атомарная дата/время-проверка ФН 234, не смешанная с последующей мутацией. Сохранить ручные шаги 1С и scope cloud/physical. Затем повторить узкие проверки и matched LIVE перед новым решением о merge; SME-очередь и два налоговых draft остаются отдельно. Новая масштабная реализация Task/Evidence из архитектурного предложения этим отчётом не разрешена и не начата.
