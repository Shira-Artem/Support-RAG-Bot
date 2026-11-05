# Реестр B2: ошибки и пробелы знаний

## Текущий итог B2.2c — 05.11.2026

**Sprint DONE, B2.3/production NO-GO.** Этот итог обновляет статусы исторических дополнений ниже; сами прежние наблюдения сохранены. B2.2b.3 equipment roles OPEN. [Итог](../b2_2c_20261104/final_report.md), [полная causal matrix](../b2_2c_20261104/causal_matrix_final.md).

| ID | Статус / новое evidence | Остаток |
|---|---|---|
| B2-C-01 / B2-C-03 | SCOPED FIX: единая model/service policy, k02 и k04 A, k01 первый ход A, финальный k03 A; negative models/cloud USB отказывают. | k01 продолжение E, primary k03 F сохранён; общей quality GO нет. |
| B2-C-02 | RESOLVED provider blocker после user-updated доступа; historical429 сохранены и Retry-After соблюдены. | Два отдельных400/schema failures за sprint — OPEN robustness, не quota. |
| B2-C-R2 | SCOPED FIX operation/domain/category, e02/s02 A; b01 первый ход A. | Общие ошибки classification/admission ещё дают F в holdout. |
| B2-C-R3 | SCOPED FIX полного how-to и bounded partial access, k02/s01 первый ход A; e01 пароль B. | Не доказан полный workflow конкретных прав; s01 continuation F. |
| B2-C-REL | OPEN: h06/h10 и m01/2 дают нерелевантный approved факт. | Проверять соответствие всем частям вопроса; grounding по SHA не заменяет relevance. |
| B2-C-SECRET | OPEN: h10 не предупреждает не присылать токен; safety-critical omission. | Общая multi-goal/secret-sharing boundary, без topic-specific patch. |
| B2-C-CONT | OPEN: b01/s01 теряют product/task route в продолжении; k01 повторяет уточнение. | Причинный reducer/Coordinator trace и общее сохранение scope при подзадаче. |
| B2-C-AUDIT | OPEN metadata/review: o04 write-процедура ошибочно preflight считалась read-only; h03 ожидаемый time-item ошибочен. | Поправки раскрыты, вопросы/минимумы сохранены; operation review и независимая проверка future rubric. |
| B2-C-KB | PREPARED5 draft, validated Loader/Chunker;13 тем в matrix. | SME review; approved/index не менялись. DirectBank/aQsi не объявлять целиком отсутствующими. |

Baseline24/30 A2/B2/D3/E3/F12/G2; primary AFTER11 A4/B1/E2/F3/G1; final holdout12 A3*/B1/E1/F5/G2. h03 rubric caveat: без него A2/11. Full702 passed/4 xfailed, profile180 passed. Следующий приоритет — relevance/safety-context и continuation route внутри B2; новая фаза не начата. [Runtime/integrity receipt](../b2_2c_20261104/release_integrity_20261105.json).


## Дополнение B2.2c — 04.11.2026

По новому заданию широкий sprint B2.2c начат; прежний следующий шаг по ролям больше не определяет приоритет. B2.2b.3 остаётся **OPEN**, исправления и AFTER отсутствуют. [Протокол](../b2_2c_20261104/protocol.md), [предварительная причинная матрица](../b2_2c_20261104/causal_matrix.md), [KB backlog](../b2_2c_20261104/kb_gap_matrix.csv).

| ID | Новое evidence / статус | Что ещё нужно |
|---|---|---|
| B2-C-01 | **OPEN, confirmed retrieval mechanism.** k01/1 ФН 234: `candidates=[]` при существующей approved manufacturer-wide статье. Ранний `requested_model` filter исключает `model=null`. [Live](../b2_2c_20261104/b22c_baseline_v3_live.json); [read-only counterfactual](../b2_2c_20261104/retrieval_counterfactual.json): три комбинации model/code absent → present, отрицательные code/model/brand контроли остаются absent. | Не внедрён. Один производитель, Scope/Planner не достигнуты, нет реального полезного AFTER; не объявлять общим решением B2. |
| B2-C-02 | **OPEN, provider blocker.** Groq TPD 199970/200000, k01/2 HTTP429, Retry-After 1213 с; предыдущие 115 с соблюдены. | Продолжение после cooldown, без смены ключа/организации/модели и без уменьшения completion allowance. Непроверенные случаи не засчитывать. |
| B2-C-03 | **OPEN, generic product-class model rejected in unresolved fallback.** [k02](../b2_2c_20261104/b22c_baseline_v4_live.json): правильный paper-print source найден, но task_unresolved; Planner получил нерелевантную продажу маркированного товара. [Predicate isolation](../b2_2c_20261104/fallback_predicate_isolation.json): `_matches_entity(aQsi 5, aQsi (физическая ККТ))=false`, изменение одного model_match возвращает fallback=true. | Это не исправленный B2.2b.3 и не новый KB gap. Не ставить model=True безусловно; согласовать общую applicability policy. Клиентский итог H: Planner 429, неверных инструкций не выдано. |
| B2-C-02 follow-up | После всех 1213 с k02 Understanding 200/2335 tokens, Planner **TPD** 429 Used199437/200000, Requested2234, Retry-After722 с от 20:53:18 МСК; следующий минимум 21:05:20 МСК. Runtime generation_reason ошибочно называет dimension=tpm, provider body=TPD; фактический dimension подтверждён capture. | Это не восстановленная ёмкость всего sprint. Всего с повторами 6 HTTP: 3×200/3×429, 7264 подтверждённых tokens. Два случая H, 22 не начаты, BEFORE/AFTER отсутствует. |
| B2-C-KB | **DRAFT ONLY.** Проверен корпус 269 карточек (206 approved/63 draft). Подготовлены определения/частичные дополнения Эвотор 7.3, Диадок, Saby, DirectBank; [точная матрица](../b2_2c_20261104/kb_gap_matrix.csv) разделяет gaps, partial coverage и runtime losses. | SME review и отдельное разрешение на approved/index; drafts вне основной KB. Персональная оплата не статический KB gap. |

Полный pytest текущего неизменённого runtime: 688 passed / 4 xfailed / 14 warnings (Python 3.14), профильные 75 passed. Эти проверки не закрывают LIVE quality gate и не заменяют 24 + AFTER + 12 independent holdout.

Дополнение 04.11.2026: кандидат «только claims, без fallback» проверен offline и отклонён: теряет оборудование и производителя в исходном случае, не исправляет периферию и роли сравнения. [Эксперимент](b2_2b3_report_20261104.md). Все открытые статусы ниже сохраняются; новых LIVE или AFTER нет.

Дополнение о LIVE 04.11.2026: поле роли в расширенном Understanding дважды классифицировало периферию/упоминание в документе как client_equipment. На неизменённом полном runtime сравнение АТОЛ сохранило обе модели и дало ложный вопрос об ОФД; новый случай сканера дал частичный ответ с одной кассой в equipment; две принадлежащие клиенту модели сохранились и бот запросил выбор. [Трассы и ограничения](b2_2b3_report_20261104.md). Исходные проблемы остаются открыты; AFTER нет.

04.11.2026. Статусы относятся к локальному runtime, не к production. Исходные traces и рубрики в связанных отчётах.

| ID / источник | Причина и статус | Проверка / результат после изменения |
|---|---|---|
| B2.2b.2 `b222_wrong_model`, [trace](b2_2b2_live_20261104.json) | Доказано: fallback без роли добавил модель инструкции как оборудование клиента. Открыто. | BEFORE ложное уточнение; AFTER отсутствует. |
| B2.2b aQsi scanner, [trace](b2_2b_live_final_20261104.json) | Доказано: модель заявила scanner как equipment, validator принял; object scanner отклонён и fallback выбрал кассу. Открыто, независимо от fallback модели. | Ложный отказ и нецелевое retrieval; AFTER отсутствует. |
| B2.2b.2 `b222_other`, [trace](b2_2b2_live_20261104.json) | aQsi 115: safety остановил запрос до retrieval; coverage есть. Открыто; способ безопасной обработки не проверен. | Нет полезной проверки; gate не ослаблялся. |
| B2.2b.1 раздельная модель 6, [trace](b2_2b1_live_remaining_20261104.json) | Не извлечена; точная первопричина не установлена. Открыто. | После изменения не проверено. |
| B2.2b.2 `b222_followup`, [trace](b2_2b2_live_20261104.json) | Код 3922: ложное уточнение, затем отказ при наличии approved статьи; вторая потеря retrieval/state требует диагностики. | Модель после reopen сохранена, полезный ответ отсутствует. |
| B2.2b.2 ФН 235, [отчёт](b2_2b2_report_20261104.md) | Неполная инструкция: отдельная проверка связи остаётся за отдельной статьёй; отсутствие полного порядка — ограничение evidence. | Первый безопасный шаг локально получен; полного решения нет. |
| B2.2b.2 `b222_software`, [trace](b2_2b2_live_20261104.json) | `1С-ЭПД` ошибочно попал в equipment; `general/explain` — наблюдаемая классификация, причина и влияние не установлены. | Полезный факт о приглашениях получен; самостоятельное исправление не проверено. |
| B2.2b duplicate, [отчёт](b2_2b_report_20261104.md) | Два совпадающих span одной модели; локально исправлено. | Исторический LIVE и SQLite reopen PASS; не обобщать на разные модели. |
| B2.2b.1 АТОЛ scope, [отчёт](b2_2b1_report_20261104.md) | Hardware scope читал ограниченную route-проекцию; локально исправлено. | Исторический LIVE исходного случая PASS, общая применимость не доказана. |

## KB backlog: Эвотор 7.3 — восстановление чека

**KB GAP**, не runtime bug: в локальной KB поиск по повторной печати и печати по номеру нашёл [статью Эвотор 6](../../data/knowledge/evotor/cash/evotor-6-receipt-copy.md), но не отдельный материал 7.3; поиск не доказывает отсутствие всех семантически эквивалентных формулировок. [Официальное руководство 7.3](https://evotor.ru/manuals/7-3/kak-vosstanovit-chek/) непосредственно описывает восстановление чека по известному номеру ФД. Наименование меню совпадает с материалом для 6, но это не даёт права переносить область модели 6. Возможен отдельный draft со scope 7.3 после проверки роли пользователя, версии интерфейса, вида документа и ограничений копии; официальный текст сам по себе не подтверждает все эти условия. Статус: кандидат для последующей подготовки и SME review; draft не создан, approved KB и индекс не изменялись.

## B2.2d — 05.11.2026: актуальный срез, LIVE INCOMPLETE

[Профильный отчёт](../b2_2d_20261105/report.md), [новый baseline18/24](../b2_2d_20261105/baseline_evaluation.json), [primary AFTER9/13](../b2_2d_20261105/regressions_v2_evaluation.json), [h10 release repeat](../b2_2d_20261105/b22d_release_regressions_live.json), [KB backlog](../b2_2d_20261105/kb_gap_backlog.csv). B2.3/production NO-GO. Статусы ниже не отменяют исторические эксперименты выше.

| ID | Доказанный механизм / результат | Остаток |
|---|---|---|
| B2-D-01 | h10: один информационный факт скрывал prerequisites и секрет; optional goal мог отсутствовать. Общий procedure-context route читает полный client span. Предупреждение независимо от provider success. Реальные v3 и release h10 полные A. | Проверки безопасности на новых сервисах в frozen holdout ещё не завершены. |
| B2-D-02 | h01 SIM/network предмет ошибочно попал в coarse error; h05 file-import в integration/connect. Предметная проекция исправлена, raw applicable targets восстановлены, LIVE B/B с консервативным frozen минимумом. | Не объявлять один безопасный шаг полной диагностикой; формат файла не раскрыт. |
| B2-D-03 | h06 procedure goal/сверка и h07 capability/version исправлены; regex считал3.0.188 нумерованным шагом. LIVE A/A. | Новая независимая общая точность ещё не измерена. |
| B2-D-04 | reducer продолжения explain/check/diagnose и access/credentials перестал безусловно создавать новую задачу. b01/s01/m01 сохраняют task/product после реального SQLite reopen; s01 LIVE A. | b01 остаётся F из-за operation metadata/неполного выбора; матрица прав конкретного инструмента не разрешалась. |
| B2-D-05 | m01 первая маркировочная проверка A; второй ход v2 E, Planner continuity скрывал warning того же источника. Новая same-source warning policy проходит offline SourceFirst reproduction; изменённый source по-прежнему fail-closed. | LIVE нового m01 кандидата НЕ выполнен из-за TPD; warning safety не объявлять LIVE закрытым. |
| B2-D-06 | h08 source есть, но task/operation mismatch edo/marking. | OPEN, не KB gap, gates не ослаблять. |
| B2-D-07 | Все18 baseline выполнены A4/B2/D1/E3/F4/G4, critical omissions2, неправильное контекстное разъяснение ЭПД/ЭДО1. Primary regressions A3/B3/E1/F2 против прежних F6/G3; h10 later A отдельно. | Наборы не объединять; финальный current-runtime suite повторён лишь частично. |
| B2-D-08 | Provider TPD несколько раз200000; пользователь явно обновлял `.env`, агент не менял. Latest full u01: Used199975, Requested2479, Retry-After1061с, earliest08:59:59 МСК. Минутные headers не TPD. | Holdout0/12 завершённых, u01 H,11 ещё не запускались; resume только с достаточной реальной ёмкостью. Исторический dimension=tpm telemetry misleading OPEN. |
| B2-D-09 | Проверка current GROQ_API_KEY совпала с `.env`, inherited override отсутствует; ключ из последнего запроса подтверждён по окончанию без публикации значения. Input redaction до Understanding/SQLite проверяется интеграционно. | Не включать значения секретов в traces; scan новых артефактов0. |

Пять drafts сохранены вне approved/index. Stage3 payload digest и KB hashes неизменны. Commit/push, Telegram pilot и production переключения отсутствуют. Владелец предложил продолжить после09:00 МСК; Retry-After не доказывает полного пополнения200000TPD.

Финал проверки перед паузой B2.2d:716 passed/4xfail, [full log](../b2_2d_20261105/full_pytest_privacy_final.log). Владелец попросил приостановиться; [промежуточный отчёт с успешными случаями и расходом](../b2_2d_20261105/interim_report.md). Все66 HTTP/44handle attempts учтены,39 ходов технически завершены; holdout0/12. Среднее3519tokens/ход, двухэтапный4802, подтверждено144564+99tokens. Работа IN_PROGRESS/LIVE INCOMPLETE, фоновых API-вызовов нет; возобновление по команде владельца, без B2.3/production GO.
