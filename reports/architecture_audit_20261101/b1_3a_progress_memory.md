# B1.3a — Diagnostic Progress Memory, 03.11.2026

## Scope и исходное состояние

Проверены текущие `DialogueManager._reduce_progress()` / `observe_answer()`, `TaskContext.checks`, `shown_units` / `eligible_units`, `ConversationStore`, SourceFirst progress update и Telegram-эквивалентный `bot.handle_message`. Исходный Git HEAD перед работой — `7e795e5`; локально уже лежал незакоммиченный окончательный B1.2 gate с решением **B1.2 GO**. Его файлы сохранены. B1.1 — GO; общий B1 и production — NO-GO. Evidence admission, Planner, approved KB, Qdrant, `.env`, production SQLite и работающий Telegram worker не менялись.

Контракт ledger: опубликованный verified approved unit создаёт `asked`; сообщение клиента о выполнении без исхода не создаёт `passed`; только сообщение клиента с конкретным исходом меняет status и содержит `message_id`, exact quote, span. Запись проверки хранит `task_id`, `unit_id`, label, source, section, `source_verified`, `asked_message_id`, историю `observations` и `contradictions`. Составной unit не становится `passed` от результата одного компонента.

## Независимая матрица и baseline

Матрица реализована в [tests/test_b1_3a_progress_memory.py](../../tests/test_b1_3a_progress_memory.py); она не использует сохранённые Groq ответы как oracle.

| Контроль | Ожидаемое изменение |
|---|---|
| A / B | Published action → `asked`; «проверил» → `asked`, без результата |
| C / D | Явный положительный / отрицательный исход → `passed` / `failed` у конкретного unit |
| E | «не знаю» / «не проверял» → `unknown` / `not_done` |
| F | Положительный, затем отрицательный исход → актуальный `failed`, обе цитаты и contradiction |
| G | Два исхода в одной реплике → два соответствующих unit; отрицание второго не заражает первый |
| H | Частичный положительный исход → составной unit не `passed` |
| I / J | Смена модели / задачи → старые model-scoped или task-scoped checks не активны в новом scope |
| K | Повтор того же `message_id` и span → без дубля observations |
| L | Ошибка генерации, pending answer или Telegram send failure → действие не показано и не `asked` |
| Дополнительно | Короткое «Работает» относится только к единственному показанному check; «да», «нет», «не помогло» не дают результата; SQLite reopen сохраняет source metadata и ledger |

Baseline до ремонта: первые 7 независимых тестов дали **2 failed / 5 passed**: comma-separated results ошибочно ставили первый unit в `failed`, повтор события дублировал observation. После первого исправления расширенная матрица дала **2 failed / 7 passed**: короткое «Работает» не сопоставлялось с единственным показанным действием; generation error со stale `progress_update` ложно создавал `asked`. Первая версия short-result правила дала регрессию на B1 memory: фраза «Теперь интернет нестабилен» прикреплялась к чужому check; правило сужено до одного слова либо двух слов с начальным «не» при единственном shown unit. Отдельные baseline тесты также доказали отсутствие `task_id` у check, ложное `asked` при неудачной Telegram доставке и сохранение `passed` после «Я ошибся: диагностический отчёт не напечатался».

Причины: старый reducer делил только по `;.!?`, выбирал первый совпавший фрагмент и обрабатывал один текст повторно; `ConversationStore` принимал `progress_update` даже при ошибке генерации; `bot.handle_message` завершал assistant event до `reply_text`. Исправлено в существующих [app/dialogue_state.py](../../app/dialogue_state.py), [app/conversation_store.py](../../app/conversation_store.py), [bot.py](../../bot.py): разделение двух comma clauses только при двух независимых результатах с непересекающимися терминами утверждённой инструкции; idempotence по message/span; ограниченное short-result сопоставление; общий предикат отрицательного результата печати; verified source metadata; публикация progress только после успешной генерации и фактической доставки. Новых LLM-вызовов и параллельной памяти нет. Итог локальной матрицы: **12 passed**. Ранее пойманная short-result регрессия исправлена; B1 memory targeted прогон после неё: **23 passed**.

## Реальный Groq E2E

Использован [bounded runner](run_b1_memory_live.py): настоящий `bot.handle_message`, Groq `openai/gpt-oss-20b` / `medium` с текущими настройками, изолированные SQLite с backup для продолжений, read-only Stage3 `green/934`, fake Telegram `reply_text`. На каждый ход сохранены raw/validated Understanding и diagnostics, TaskFrame/state до/после, точный ответ, HTTP trace и `sqlite_roundtrip_equal`. Никаких искусственно опубликованных units. Всего **16/26 HTTP-попыток, все 200, 0×429**; каждый ход — 1 или 2 вызова внутри текущего pipeline. Следующие unit ID сокращены в таблице: `P=f09c43177d5a42267fe0` — напечатать диагностический отчёт; `C=7ecc73b5ecb8e7125d80` — состояние EoU, интернет, настройки ОФД, очередь. Оба взяты из verified approved [статьи Эвотор 7.3](../../data/knowledge/evotor/ofd/evotor-7-3-ofd-connection.md), section «Что проверить сначала», `source_verified=true`.

Все реальные ходы и ответы полностью доступны в отдельных JSON; ниже ответ дан дословно, кроме явно помеченного длинного approved блока, полный текст которого сохранён в JSON. `raw → validated` указывает `relation/intent/operation`. TaskFrame до/после содержит `checks` с теми же статусами, что `TaskContext`; остальные факты (Эвотор 7.3, первоначальный symptom «чеки остаются на кассе и не доходят до ОФД») и `task:1` сохраняются на всех продолжениях. После каждого хода `DialogueState.to_dict()` до/после reopen равен побайтно по структуре (`sqlite_roundtrip_equal=true`).

| Ветка, ход, сообщение клиента | raw → validated; TaskFrame / checks до → после | Реальный ответ; HTTP; trace |
|---|---|---|
| S1/1 «На Эвотор 7.3 чеки остаются на кассе и не доходят до ОФД. Какую проверку сделать первой?» | `new_task/diagnose/diagnose → new_task/receipt/diagnose`; `null/[] → task:1/P asked` | «Статья производителя относит Эвотор 7.3 к группе моделей с диагностикой через отчёт. Под ролью администратора откройте „Настройки → Обслуживание кассы → Диагностика“ и напечатайте диагностический отчёт.» + source; 2×200; [JSON](b1_3a_live_s1_open_20261103.json) |
| S1/2 «Диагностический отчёт напечатал.» | `continue/receipt/diagnose → continue/receipt/diagnose`; `task:1/P asked → P passed, C asked` | «В нём проверьте состояние приложения EoU, доступ в интернет, адрес и порт ОФД…» — далее approved условные действия по сети, настройкам и очереди + source; 2×200; [JSON](b1_3a_live_s1_result_20261103.json) |
| S1/3 «Очередь неотправленных документов не уменьшается.» | `continue/diagnose/diagnose → continue/unknown/diagnose`; `task:1/P passed, C asked → P passed, C failed` | Повторён полный approved раздел «Что проверить сначала» + source; 2×200; [JSON](b1_3a_live_s1_negative_20261103.json) |
| S2/1 shared real opening S1/1; S2/2 «Проверил.» | `continue/general/status → continue/general/status`; `task:1/P asked → P asked` | «Удалось выполнить показанную проверку и каков её результат?»; 2×200; [JSON](b1_3a_live_s2_ambiguous_20261103.json) |
| S2/3 «Диагностический отчёт напечатал.» | `answer_to_clarification/receipt/diagnose → same`; `task:1/P asked → P passed, C asked` | Тот же опубликованный approved следующий шаг об EoU, интернете, настройках и очереди + source; 2×200; [JSON](b1_3a_live_s2_explicit_20261103.json) |
| S2/4 «Я ошибся: диагностический отчёт не напечатался.» | `answer_to_clarification/general/diagnose → answer_to_clarification/unknown/diagnose`; `task:1/P passed, C asked → P failed, C unknown` | «Удалось выполнить показанную проверку и каков её результат?»; 2×200; [JSON](b1_3a_live_s2_correction_20261103.json) |
| Дополнительная ветка от S1/2: «Интернет работает.» | `task:1/P passed, C asked → P passed, C unknown`, **C не passed** | Повторён approved раздел + source; 2×200; [JSON](b1_3a_live_s1_partial_20261103.json) |

S2 — отдельное продолжение из backup **реального** checkpoint после S1/1, с той же опубликованной проверкой P и новым живым `bot.handle_message` на каждом последующем ходе. Это две ветки одного реального opening, а не два независимых открытия. Перед этим проверены два независимых естественных открытия: «Эвотор 6 печатает чеки, но оператор их не видит. С какой проверки начать?» ([JSON](b1_3a_live_s2_open_20261103.json), 1×200) и «На Эвотор 7.3 фискальные документы остаются в очереди и у оператора их нет. Что проверить?» ([JSON](b1_3a_live_s2_open_alt_20261103.json), 1×200). Оба ответа были «Для этой задачи в „Эвотор“ не нашёл подтверждённой применимой инструкции…», `shown_units=[]`, `checks=[]`, SQLite equal. Поэтому для них проверка результата без опубликованного действия была бы недостоверной; SourceFirst/Planner не менялись. Это отдельная зависимость качества выбора approved источника для B1.3b/B2.

### Exact evidence и отрицательные контроли

- P: `asked_message_id=2`, source `data/knowledge/evotor/ofd/evotor-7-3-ofd-connection.md`, verified true, `task_id=task:1`. В S1 result — `passed` от user `message_id=3`, exact «Диагностический отчёт напечатал». В S2 branch — `passed` от `message_id=5`, затем `failed` от `message_id=7`, exact «Я ошибся: диагностический отчёт не напечатался»; `observations=[passed,failed]`, `contradictions=[m5→m7]`.
- C: `asked_message_id=4`, тот же verified source и task. В S1 negative — `failed` с exact «Очередь неотправленных документов не уменьшается», user `message_id=5`; P остаётся `passed`. В S2 correction C становится `unknown` из-за пересечения общего блока с частичным исправлением P; результат C **не утверждён**, P корректно `failed`. Отдельная положительная ветка «Интернет работает» также оставляет C `unknown` с цитатой, не `passed`.
- «Проверил» не даёт положительной observation и не меняет P. Два неудачных независимых открытия не имеют фиктивно показанных checks. Ошибки генерации/доставки и replay одного события покрыты SQLite/deterministic тестами; в live HTTP ошибок не было. Модель и task scope, короткие «да/нет/не помогло», русская неопределённость и несколько результатов в одной реплике проверены независимой матрицей.

## Финальные проверки и решение

`python -m pytest -q`: **628 passed, 4 xfailed, 14 warnings, 0 failed**. Целевые B1.1/B1.2, ProgressLedger и Telegram SQLite replay включены в полном наборе; отдельный targeted regression run указан в журнале. Все 9 новых live JSON имеют `sqlite_roundtrip_equal=true`; ответ действительно прошёл fake Telegram до `ConversationStore.complete`. Суммарный live бюджет соблюдён: **16/26**. По контракту B1.3a нет ложного успеха, отрицательный исход и исправление не теряются, unit/task/model scope и история сохраняются, составная проверка не завершена частичным результатом. **B1.3a GO** для памяти диагностического прогресса; общий B1 и production остаются **NO-GO**. Повтор уже выполненных рекомендаций и два открытия без применимого источника записаны как отдельные проблемы качества ответа / выбора источника для возможного B1.3b/B2, без начала этих этапов.
