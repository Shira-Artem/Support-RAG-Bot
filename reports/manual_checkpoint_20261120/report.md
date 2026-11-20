# Контрольная точка ручного Telegram 19–20.11.2026

**Итог: evidence и воспроизводимые LIVE сохранены; общий прирост полезности не доказан, candidate/production NO-GO. Критический пробел очистки ФН исправлен и отдельно перепроверен; в рабочий бот кандидат не внедрялся.**

## Подтверждённое исходное состояние

Main/remote main: `44763e0aecb23f5fc4e702617f47f1b6230d7ec5` (проверено
`git ls-remote`, 20.11). Telegram worker 3232, launcher 13568, старт
20.11 10:02 MSK; receipt после инициализации 10:03:29, commit `1d88b42`.
Все 37 загруженных исходных файлов совпадают с текущим checkout; точное
число и hashes сохранены в receipt, результаты сверки — [runtime_before.json](runtime_before.json).
Используется Hubris `openai/gpt-oss-20b`, low; для ordinary conceptual
генерации существующий профиль medium. SourceFirst + Coordinator + Composer,
handoff delivery off. Список тестировщиков не публикуется.

KB B2 **уже объединена**, вопреки предпосылке нового задания:
feature `1b5280683ed922e67c41e119ba2743814c1ccdb5` — предок main через
`21b5fe9c02ad96a986b3389925d53aaf3d1c25dd`; remote refs подтверждены.
269 карточек: 204 approved / 65 draft. Qdrant
`knowledge_kb_b2_integrated_20261119` green / 833, полное сравнение каждого
payload с локальным approved corpus: **exact match**. Старые коллекции 672/934
сохранены. `.env`, рабочие SQLite, коллекции и polling не менялись.

Исторический кандидат `4680aa0` и его 84 дополнительных failures не исчезают:
[первоначальный отчёт](../kb_integration_20261119/report.md).
Позднейшая интеграция, изменения контрактов/fixtures, два full-suite результата
и ограничения описаны в [authoritative report](../kb_authoritative_20261119/report.md).
Это разные состояния кода. Старые 84 нельзя выдавать за текущий runtime,
как нельзя считать новые зелёные fixtures доказательством пользы разговора.

## Ручное evidence

SQLite открыт `mode=ro`, `quick_check=ok`; согласованный backup оставлен
только в ignored `.local/manual-checkpoint-20261120/snapshot.sqlite3`.
Экспорт: **24 хода / 13 диалогов / 24 исходных Understanding traces**.
Все traces связаны по exact current_message и ближайшему timestamp (<120 с).
Включены два ранних неудачных хода 19.11 до целевого окна; внутри окна
16:02–17:31 — M03–M11, 20.11 10:21–10:29 — M12–M24.
В SQLite нет хода ровно в 10:21: первый сохранён в 10:22:05.

* [Дословные сообщения и ответы](manual_answers.md).
* [Полные обезличенные diagnostics, KB fragments, Coordinator, состояния и raw Understanding](manual_evidence.json).
* [Походовая PASS / PARTIAL / FAIL матрица](manual_matrix.md), [JSON](manual_matrix.json).
* [Замороженный набор 65 ходов](scenarios.json): 24 прежних A/B/C, 24 ручных,
  17 дополнительных. Исторические тексты восстановлены по SHA256 из исходной
  SQLite, все 24 hashes совпали; grades A/B/C — достаточность KB, а не PASS.

Редакционная оценка ручного ответа: **3 PASS / 6 PARTIAL / 15 FAIL**.
Она оценивает конкретное продвижение клиента, не независимую истинность всей KB.
Пустой pending ответ M01 не считается доставленным. SQLite timestamps — время
записи, не время получения/доставки Telegram. Полного журналирования генерации
и grounding каждого старого хода нет; raw модельный текст доступен только там,
где реально сохранён diagnostics. Он отделён от опубликованного ответа.
Отсутствующие запросы/результаты не реконструировались.
Исторический corpus неоднороден: M02–M03 записаны со Stage3, M04–M24 —
с B2 integrated; у M01 collection/provider отсутствуют. SHA каждого старого
worker в per-turn diagnostics не записан и не приписывается ему по текущему HEAD.
[Походовая provenance](manual_provenance.json). Эта историческая матрица не
подменяет новое контролируемое65-turn сравнение.

## Причины по цепочке

| Наблюдение | Подтверждённая цепочка | Что не доказано |
|---|---|---|
| Объясни попроще, M05 | Understanding/State сохранили кассу/general/explain. GeneralKnowledge prompt получает только последнюю просьбу без предмета. Полезный raw ответ сохранён, затем output gate отклонил как scope/relevance. Код сравнивает ответ только с лексикой последней реплики. | Нет основания объявлять это отсутствием знаний LLM либо KB. Состав отдельных boolean output predicates воспроизводится отдельно. |
| Срок ФН-235, M12 | Raw `device/status`, equipment ФН-235, без symptom/error_codes. Resolver regex принимает любой «ФН + число» за reported_error → unknown/diagnose. Readiness требует симптом. | «235» не подтверждён как ошибка; вывод о реальной неисправности неправомерен. |
| Чек не печатается, M24 | Symptom сохранён точно. Retrieval вернул чужие code-specific статьи; guard правильно запретил их, но `_unconfirmed_error_code_reply` при наличии symptom спрашивает повторно, что сломалось. Raw relation=new_task также потерял прежнюю общую задачу. | Память не потеряла текущий симптом: повтор вызван шаблоном, а не отсутствием текста в State. |
| DirectBank, M16 | Named product исключает общий model-only path. Approved evidence получено; Composer `unsupported_information_claim`, exact fallback, затем semantic relevance `irrelevant`. | Первоначальный Composer HTTP/raw не сохранён. Нельзя доказать, что relevance verdict ошибочен, или выдумать отклонённый текст. |
| Эвотор, M09/M17–M19 | Первый Planner source_order_complete=False. Позже точная секция найдена, но выдан только numbered unit с путём меню. Следующий numbered unit содержит печать отчёта. Ledger ждёт результат пути меню; reported internet/payment не подтверждают его. Уточнение шага трактуется как неопределённый результат, затем escalation. | Успешное сохранение фактов не доказывает пригодность unit/check модели. Ни интернет, ни оплата не доказывают печать отчёта. |
| АТОЛ Онлайн, M10/M11 | Платёж прошёл + чек не пришёл. Task projection даёт billing, применимые receipt/integration источники отбрасываются `task_mismatch:*!=billing`; `no_task_matched_candidates`. | Из двух отказов не следует отсутствие нужного контента вообще. Сообщения о полном молчании сверх сохранённых ходов не подтверждены. |
| Два ответа об ОФД, M06/M07 | Два одинаковых user rows, 17:24:18 и 17:24:33, по одному assistant row. | Нет Telegram update/message ID; повторный ввод, redelivery либо повтор handler не различимы. Два poller текущей инвентаризацией не обнаружены. |
| Недостоверные чеки, M08/M21 | Model-only без approved evidence. Existing normative sentence filter удаляет одну формулировку, но пропускает равнозначные «нет юридической силы»/«не фискальные», а также штрафы. diagnostics ошибочно сообщает отсутствие current rules. | Scope/safety не является фактологической проверкой. Нельзя считать generated/HTTP200 успехом. |

Разделение: строки выше подтверждены сохранёнными фактами и соответствующим
кодом; недетерминированный выбор LLM, производная потеря цели при продолжении,
и вклад расширенного корпуса в Planner остаются гипотезами до парных LIVE.

## Приоритеты до изменения кода

1. Передать общему разговорному ответу текущую цель/предмет из общей памяти;
   проверять релевантность продолжения относительно той же задачи.
2. Сохранить семантическое различие идентификатора оборудования и сообщённого
   кода ошибки; задавать уточнение недостающего факта с учётом уже известного
   симптома, сохраняя запрет чужих code-specific инструкций.
3. Исправить неполное применение уже существующей границы неподтверждённых
   правовых/фискальных утверждений. Grounding не отключать; новый pipeline,
   модельный этап или запреты модели не добавлять.

Фрагментация Эвотор/ledger, DirectBank evidence selection и billing projection
АТОЛ остаются отдельными диагностированными проблемами. Не менять их вслепую
вместе с этими тремя механизмами. Полный production/quality gate NO-GO.

## LIVE и проверка кандидата

Используется существующий `run_telegram_equivalent_live.py` через
[тонкий manifest runner](../../scripts/run_conversation_cycle_20261120.py).
Изолированы только Telegram delivery (перехват, без polling) и SQLite;
Understanding/Planner/Composer/relevance — настоящие HTTP Hubris,
retrieval — существующий Qdrant с read-only proxy. Mock текст не служит
доказательством LIVE качества. Базовый прогон начат до изменений app.
Фактические результаты и ограничения приведены в итоговой таблице ниже.

Baseline из основной директории: `.venv/Scripts/python.exe -X utf8 scripts/run_conversation_cycle_20261120.py --cohort historical_abc,manual,additional --output .local/manual-checkpoint-20261120/baseline-unique.json`.
Каждому запуску нужен уникальный output stem: harness не перезаписывает SQLite.
Секреты читаются из существующего окружения/.env без вывода.

Сравнение KB проводится на одном app-коде, модели и manifest, разных
approved-only коллекциях и строго соответствующих source roots. Никакой merge,
переиндексации или подмены рабочего Qdrant для сравнения не требуется.


## Минимальный candidate и отрицательные результаты

Checkpoint evidence commit: `9119f04122f090a69c3fc9e5ced0351e022f0024`,
ветка `codex/manual-conversation-20261120`; push не выполняется.
Проверка M05 всех output predicates: citation/normative/imperative/unsafe=false;
current-turn overlap=false, saved subject overlap=true.
[Детерминированное causal replay](causal_predicate_replay.json) не заменяет LIVE.

Внесены три механизма из приоритетов: JSON current_message + active_task в
существующий general prompt; релевантность продолжения с текущей задачей;
сохранение status/search/explain для FN identifiers без положительно сообщённой
ошибки и уточнение известного object/symptom; existing normative output gate
распознаёт более общий класс правовых последствий, санкций и отрицания фискального
статуса. Новых model calls/stages/prompts-запретов нет. Технические scope/source
и unsafe-operation guards сохранены.

Первый intake-вариант был слишком широк: трактовал любое symptom как конкретную
поломку, дал два новых падения старых vague-symptom contracts. Он сужен до
подтверждённых object+symptom; прежние expectations не переписаны.
Full suite baseline:923 passed/10 failed/4 xfailed; первый candidate:935/12/4;
финальный:937/те же10/4. Targeted197 passed. [Поимённое сравнение](pytest_comparison.json).

Baseline LIVE остановился после52 ходов: реальный HTTP200 с неверной структурой
Understanding (structured_response_shape), не rate limit и не transport.
Ошибка и неисполненные ходы сохранены. Для завершения создан immutable app
snapshot из44763e0;37/37 canonical LF hashes совпадают. Первое сравнение raw
bytes не прошло из-за смешанных Windows line endings; не объявлено exact-byte PASS.
[Архивная сверка](baseline_archive_verification.json). Один контролируемый
повтор всего дополнительного explain-сценария и оставшиеся сценарии выполняются
последовательно, не заменяя первоначальную неудачную попытку.


## Candidate LIVE: критический NO-GO и safety repair

Baseline:67 попыток/65 уникальных planned rows (две explain-попытки повторены
контролируемо),122 HTTP200+1 HTTP502,169 коп. reported usage.
Первый candidate:65 planned rows,16 PASS/17 PARTIAL/32 FAIL по редакционной
рубрике; baseline65:15 PASS/17 PARTIAL/33 FAIL. Такой счёт **не означает
улучшения**: candidate выдал1 неподтверждённую опасную инструкцию против0
в этом baseline. [Критический ответ и причина](critical_erasure_failure.json).
Он выдумал меню очистки фискальной памяти, обойдя model-only eligibility при
ошибочном Understanding information/general/explain. Общий guard не имел
семейства очистки/стирания/сброса фискальной памяти. Это подтверждённая дыра
существующей политики, а не основание вводить новый pipeline или запреты в prompt.

General factual quality также не пройдена. Candidate приписал ОФД выдачу
фискального номера/подписи. [ФНС относит формирование фискального признака к
функциям ФН](https://www.nalog.gov.ru/rn77/related_activities/registries/reestr_fiscal/);
[конкретный ответ и граница внешней проверки](factual_review.json). Это отдельная
ошибка от юридических последствий неоплаты: последние здесь не реконструируются
как универсальный налоговый вывод. Lexical normative filter не является
фактологическим grounding. Продолжения с аналогиями также дают датчики,
plug-and-play assurances и смешение ФНС/ОФД.

Разрешённые точечные изменения остались в трёх механизмах. В третий (существующая
safety/grounding boundary) добавлено распознавание destructive action + fiscal
storage с обоими порядками слов; очередь печати/кэш/Wi-Fi отдельно не блокируются.
Новая модельная стадия и новая LLM-инструкция не добавлены.
[Safety pytest](pytest_safety_summary.json):116 targeted passed; full950 passed/
те же10 failed/4 xfailed. Первый LIVE safety-повтор26 ходов завершён. После коррекции приоритета guard
выполнены ещё9 ходов; первый опасный ответ сохранён и не заменяется retest.

Другие реальные отрицательные результаты: Selector отверг полноценный JSON в
Markdown fence при finish_reason=stop, а не нехватке token budget.
[Точная трасса](selector_envelope_failure.json). Ещё один Understanding вернул
недекодируемый JSON; это отдельно от первого structural shape error и HTTP502.
Изначальный helper останавливал batch на schema errors; продолжение запускает
следующее planned сообщение без retry модели, с тем же сохранённым SQLite и
равенством полного state. При resume ошибочно выбран общий фильтр:2 лишних
независимых turns/5 HTTP200/7 коп. сохранены отдельно и исключены из A/B.
Их тестовый процесс остановлен, pointer исходного тестового диалога восстановлен
с проверкой state equality. Рабочая manual SQLite не затронута. Стоимость/trace
незавершённого in-flight вызова при этой остановке неизвестны. Не считать их0.
Добавлены preflight исходного порядка/входов/кода/профиля и per-HTTP запись на диск.


## Итоговые LIVE и сравнение KB

| Серия | Ходы (attempts) | PASS / PARTIAL / FAIL | Reported коп. | Результат |
|---|---:|---:|---:|---|
| Ручной Telegram19–20.11 | 24 | 3 / 6 / 15 | Не полностью сохранены | Контрольная точка, не acceptance |
| Исходный app + текущая B2 | 65 unique / 67 attempts | 15 / 17 / 33 | 169 | Baseline,0 опубликованных destructive instructions в выборке |
| Первый candidate + B2 | 65 | 16 / 17 / 32 | 180 | **NO-GO:1 invented fiscal-memory erasure procedure** |
| Тот же первый candidate + pre-B2 | 65 | 14 / 21 / 30 | 161 | Общего победителя нет;0 destructive procedures в этом проходе |
| Safety repair, первый повтор | 26 | 10 / 6 / 10 | 38 | Опасных меню0;2 сброса ошибочно ушли в intake вместо escalation |
| Final safety, targeted repeat | 9 | 8 / 1 / 0 | 17 | 6/6 ответственных запросов эскалированы, specialist wording truthful; два других target не заблокированы |
| Ошибочный resume, исключён | 2 | Не включён | 7 | Отдельные raw/answers; in-flight billing неизвестен |

Первые65 оценок не присваиваются финальному safety patch. Последние9 —
узкий safety gate, а не повтор65 или доказательство общего улучшения.
Полная [65-row таблица](comparison.md), [JSON с причинами, latency и стоимостью](comparison.json),
[CSV](comparison.csv), [редакционные оценки](live_assessments.json),
[распределение компонентов](component_distribution.md).
Все raw requests/responses, сохранённые intermediate stages, actual answers,
полные states и sources находятся в [live](live/): JSON.gz и читаемые answers.md.
Формат распаковки — UTF-8 JSON через Python gzip.open; пропуски baseline явно
описаны в metrics, не достроены предположениями.

Итого234 завершённых HTTP-backed turn attempts:412 HTTP200,1 HTTP502,
9 попыток без HTTP-статуса,777537 reported tokens,572 reported коп. (5,72 руб.).
Это сумма сохранённого usage, не сверенный счёт провайдера. Неизвестная
стоимость прерванного in-flight вызова и usage без ответа не принимаются за0.
[Полные суммы и SHA compressed traces](run_totals.json). HTTP200 не означает
валидный JSON, полезный ответ или grounding PASS. SQLite reopen равенство
подтверждено для каждого сохранённого completed attempt.

KB comparison контролирует37/37 app hashes, Hubris model/effort, вопросы,
изоляцию SQLite и корректный source root. Различаются corpus/index и наблюдаемые ответы API. Изоляция и сегментация дают
разные непрозрачные task/message IDs; сетевые условия не фиксированы,
побайтовая идентичность provider payload не утверждается. Промежуточное
понимание и память отличаются как реальные результаты тракта. Оба corpus полностью совпадают со
своими approved-only payload: [current](runtime_before.json),
[pre-B2](pre_b2_index_verification.json). У обычных model-only ходов KB вообще
не вызывалась; их разницу нельзя приписать корпусу.

Наблюдаемые различия: B2 дала полезное определение DirectBank и полный billing
slice АТОЛ, но DirectBank снова отказал в финальном повторе. В pre-B2 ФН231
дал безопасную проверку отчёта, B2 выбрала описание причины без подтверждённых
параметров клиента. Эвотор/продолжение и оплата→неполученный чек АТОЛ не решены
обеими KB. Marking/role slices местами полнее с B2. Один проход не устанавливает
устойчивую причинную победу KB. Новая KB уже merged, её не объединяли повторно
и не откатывали; изолированный старый root/672-point index не повреждён.
Результаты старого4680aa0 сохранены отдельно от поздней исправленной интеграции.
[Оба исторических grounding control на текущем коде](kb_grounding_controls.json)
не дают выдуманного автопродления/повторного импорта/переподключения.

## Финальные изменения и границы

* Контекст: current_message + reducer-owned object/task/goals/details переданы
  существующему general generator; continuation relevance использует тот же task.
* Понимание/уточнение: голый номер ФН не переопределяет semantic status/search/explain
  в reported_error; intake учитывает подтверждённые object+symptom. Если Understanding
  не сохранил object или уже назвал задачу diagnose, полный разговор ещё ломается.
* Existing safety/grounding: дополнен класс нормативных утверждений; отдельно
  исправлена обнаруженная дыра destructive fiscal-storage actions. В9-turn повторе
  явная опасная операция проверяется до incomplete-task intake; later assembled-query
  guard сохранён для контекстных продолжений. Новых модельных стадий, prompts-запретов,
  ослабления approved/scope/order checks или отключения grounding нет.

Последний full pytest: **952 passed / те же10 failed / 4 xfailed**,
[поимённая сверка](pytest_final_summary.json). Старые10 — реальные ограничения
ledger/SQLite contracts, а не разрешение production. Фактологическое качество
model-only по-прежнему не доказано; существующий lexical filter его не обеспечивает.
Результат6/6 dangerous requests относится к перечисленным русским формулировкам,
не универсальная гарантия для любого языка/эвфемизма.

Ни одна кнопка отправки реальному специалисту этим harness не нажималась.
Проверено обещание локального handoff без доставки, не фактическая доставка.
В исходной manual SQLite48 messages; feedback/support_requests/escalation_events=0.
Ответы этого цикла перехватывались на Telegram transport; они не объявляются
полученными владельцем в Telegram. Работающий ручной worker проверяется отдельно.

## Следующий рекомендуемый эксперимент

На тех же вопросах об ОФД/ФН и продолжениях проверить фактическое ядро ответа
через **существующий grounded Composer с approved evidence**, с повторными
реальными Hubris calls и сохранением обычной социальной беседы без обязательной KB.
Сначала отделить способность корректно объяснить предоставленные факты от ошибок
автоматического отбора, затем проверить полный текущий тракт. Успех: отсутствие
выдуманного источника фискального признака/нефискальности и полезное продолжение.
Разрыв атомарной проверки Эвотора и billing projection АТОЛ остаются в backlog;
нового pipeline, A7/PartB/Exp3 или rollout этот отчёт не разрешает.


## Git и идентичность проверенного кода

Контрольная точка:`9119f04122f090a69c3fc9e5ced0351e022f0024`;
pre-safety app:`5bcfd71d150a119eb07679dc47c826618f76a614`;
финальные минимальные app/safety изменения:`3aa1f68d94d2256c8d58e7bfdd71a5cfe55c9551`.
[Идентичность37 исходных файлов](code_identity.json) связывает реальные процессы
и working-tree delta с коммитом; один HEAD не считается доказательством runtime.
Ни push, ни merge candidate в main не выполнялись. Candidate сохраняется отдельно
для ревью; финальное состояние основного checkout и worker фиксируется ниже.


## Завершение: работающий бот и расположение изменений

Кандидат изолирован в managed checkout `manual-conversation-review`, ветка
`codex/manual-conversation-20261120`. Проверенные app изменения — коммит
`3aa1f68d94d2256c8d58e7bfdd71a5cfe55c9551`; последующие commits этой ветки
документируют результаты. В основную директорию возвращён **main с прежним
app-кодом**. Там публикуются только локальный docs/evidence checkpoint и QA
инструменты; новые app guards/контекст в рабочий Telegram не развёрнуты.
В review нет копии секретного `.env`.

[Финальная read-only сверка](runtime_after.json): worker3232/launcher13568
не перезапускались; свежий getUpdates HTTP200,37/37 source bytes совпадают
со startup receipt1d88b42, SQLite quick_check=ok,48 исходных messages и все
проверенные state/feedback/request таблицы равны начальному private snapshot.
При checkout восстановлены исходные line endings resolver; code diff с
startup Git по app/bot.py пуст. Qdrant green/833 exact approved payload,
KB blobs совпадают с feature. Рабочая `.env` не редактировалась. Другого polling
не запускали. Эти факты доказывают сохранность действующего процесса/данных,
а не отсутствие прежних ошибок разговора или получение новых QA-ответов в Telegram.

Для candidate replay из основной директории используйте существующую `.venv`
и явный `--code-root` review checkout. Например, в PowerShell:

```powershell
& .venv/Scripts/python.exe -X utf8 scripts/run_conversation_cycle_20261120.py --code-root 'C:/Users/Shira/.codex/worktrees/manual-conversation-review/Rag' --cohort historical_abc,manual,additional --output .local/manual-checkpoint-20261120/replay-unique.json
```

Runner загружает credentials из основной директории без копирования в review,
а app/harness импортирует из указанного checkout. SQLite/HTTP traces будут
изолированы в review/.local, Telegram token заменён synthetic transport boundary,
Qdrant разрешает только read operations. Для любого нового запуска выбирайте
уникальный output stem. Финальный952/10/4 pytest относится к **candidate**;
для возвращённых QA helpers на main отдельно27 passed. Полный app-suite main
в начале цикла был923/10/4, его код остаётся прежним. Push не выполнялся.
