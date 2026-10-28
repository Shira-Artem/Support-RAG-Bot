# Routing & Evidence Repair — шаг 1: Explicit Service/Entity Routing

**Дата:** 2026-10-28. **Область:** локальная копия, начальный HEAD `d6c1626c856f27f7ae8bff685fbb64bfb6e3aee4`, чистый `git status`. Approved KB, Qdrant, SQLite, Telegram-worker и `.env` не изменялись. Commit/push не выполнялись.

## Доказанная причина

- До изменения общий реестр `ENTITY_NAMES` не содержал Saby/СБИС, Диадок и БИФИТ. `LexicalAnalyzer` и `Understanding.validate_response` используют этот реестр; без него названный сервис не становился подтверждённым route.
- В `OBJECTS` алиас `документ` относился к `receipt/чек`. Входящий документ Saby поэтому получал `intent=receipt`, `object=чек`, `operation=search`, `expected_task=receipt_search`. При `routing_service=null` сервисный gate не мог отклонить статьи Платформы ОФД/АТОЛ Онлайн; до исправления финальный retrieval сообщал `full/sufficient`.
- Для Диадока исходная трасса имела `intent=delivery_document`, `object=УПД`, `operation=check`, `expected_task=edo`, но service route отсутствовал. Кандидат Диадок уже был в raw top-K и отклонялся по `operation_mismatch:check`. Значит подтверждённый в этом кейсе дефект был upstream в entity routing, а непопадание финальной статьи остаётся отдельным task/operation блокером.
- В исходном БИФИТ-трейсе не было route, а retrieval final содержал статьи Эвотор/aQsi. После добавления route они отклоняются существующим service gate. Отдельно трасса после entity repair показала второй дефект: широкое subset-сопоставление принимало generic `БИФИТ` за продукт `БИФИТ Касса`. Поэтому явный service gate теперь требует равенства токенов service metadata для route-slot `service`; manufacturer/software/model остались отдельными слотами.
- В Sprint 3 метрика `negative_cross_candidate_final_hits=1` считала статью Эвотор при запросе про Эвотор ложным cross-service hit: это был другой подходящий candidate, а не чужой сервис. Новая матрица хранит запрещённый target, другой финальный candidate с совместимым сервисом и реально foreign service отдельно.

## Изменения

- `app/dialogue_state.py`: data-driven алиасы Saby/СБИС, Диадок, БИФИТ и отдельное точное имя продукта БИФИТ Касса добавлены в существующий реестр. Удалён слишком общий алиас `документ` из объекта `чек`; при недостатке признаков объект остаётся `None`.
- `app/retrieval_pipeline.py`: service route требует совпадения всей канонической service метки с metadata; broad vendor substring больше не авторизует отдельный продукт. Manufacturer route, ПО, модель, operation/task applicability и остальные safety gates сохранены.
- Регрессии в `tests/test_dialogue_state.py`, `tests/test_dialogue_understanding.py`, `tests/test_metadata_retrieval_routing_v3.py`; воспроизводимые in-memory harness и live Groq runner: `scripts/diagnose_explicit_service_routing.py`, `scripts/run_routing_repair_live_e2e.py`.

## Baseline / after

Трасса использует локальный `LexicalAnalyzer`, 206 approved документов и 8 временных draft overlays, поданных как approved только в `QdrantClient(':memory:')`. Внешний LLM не вызывался. Полные entities, intent/object/operation/relation, route, analysis flag, RAG query, expected task, raw top-K, final evidence и rejection reasons сохранены в JSON. Для raw/validated Groq entities в baseline их нет: staging использовал lexical analyzer.

| Сценарий | Baseline | После шага 1 |
|---|---|---|
| Saby: входящий документ | Нет route; `receipt/чек + search`; `receipt_search`; финальные Platforma OFD и ATOL Online, `full/sufficient` | Route `Saby`; object `None`, intent `unknown`, operation `search`; cash-search articles отклонены `service_mismatch_or_unlabeled`; только временный Saby draft может пройти как `partial`, approved-only final пуст |
| Диадок: исходящий УПД/статус | Нет route; candidate Диадок в top-K, rejection `operation_mismatch:check` | Route `Диадок` сохранён; чужие service candidates отклонены; сама статья всё ещё отклоняется `operation_mismatch:check`, final пуст |
| БИФИТ: POS-терминал | Нет route; Эвотор/aQsi final, `sufficient=true` | Route `БИФИТ Касса`; Эвотор/aQsi отклонены; final пуст из-за неподходящей task/applicability |
| БИФИТ без продукта | Нет route; временная статья БИФИТ Касса стала `partial/sufficient` | Route `БИФИТ`; статья `БИФИТ Касса` отклонена service gate; final пуст |
| БИФИТ Касса: столы | Route отсутствовал; draft о web-бронировании в final, `partial/sufficient` | Продуктовый route `БИФИТ Касса`; тот же draft остаётся в final при неразрешённом task. Это зафиксированный Task/Sufficiency blocker, не исправлялся в шаге 1; в approved-only final пуст |

## Offline контроль

- 31 сценарий: все 16 исходных Sprint 3 случаев, независимые формулировки Saby/Диадок/БИФИТ, чужой/неназванный сервис, БИФИТ vs БИФИТ Касса, AТОЛ Онлайн vs АТОЛ, и positive controls AТОЛ Онлайн, Эвотор 6, aQsi Online/1С и Платформа ОФД.
- 4 отрицательные пары после исправления: **0** запрещённых target в final, **2** кейса с другим candidate того же маршрута, **0** случаев реально чужого сервиса в final. Старый cross-service false positive был ошибочной метрикой на подходящем candidate Эвотор.
- Регрессии: утверждённый поиск Эвотор 6 остаётся `full`; Platforma OFD receipt search — `full`; approved-only ATOL Online и исходная aQsi Online query сохраняют baseline результат. В overlay запуске ATOL query остаётся без final, как и baseline overlay до изменения; временная ATOL API draft меняет raw competition, но сама отклоняется task gate. Положительная aQsi Online integration проверяется отдельным retrieval regression, где физическая aQsi отклоняется.
- `python -m pytest -q`: **535 passed, 4 xfailed, 13 warnings**. После дополнительного aQsi same-vendor scope assertion targeted suite: **92 passed**.
- `python scripts/source_scope_offline_e2e.py`: **15/15**, read-only Stage3; локальные fixtures, 0 live provider calls. Stage3 server сообщил версию 1.15.4 при клиенте 1.19.1 (предупреждение совместимости).
- Артефакты полного сравнения: [baseline JSON](routing_repair_baseline.json), [after JSON](routing_repair_after.json). Первый intermediate post-run сохранён исторически в [routing_repair_after_initial.json](routing_repair_after_initial.json); финальный результат — `routing_repair_after.json`.

## Live E2E и остатки

Groq был настроен на `openai/gpt-oss-20b`; отправлена одна безопасная синтетическая Understanding попытка. Ответ не получен: DNS завершился `getaddrinfo failed` (`ConnectError`) для `api.groq.com`. Answer-generation вызов не запускался. Реальный ответ не симулировался; live gate остаётся неподтверждённым.

- **EDO Task Routing (следующий отдельный блокер):** Диадок status остаётся `operation=check` против metadata `exchange_edo_documents`; raw candidate есть, final нет. Не менялось в этом шаге.
- Saby получает `expected_task=None` после удаления ошибочного object binding. Нет подходящего approved Saby evidence; временный draft в staging не даёт права на production answer.
- BIFIT terminal запрос грубо классифицируется как network/error_diagnosis. При named БИФИТ чужие Эвотор/aQsi больше не проходят, но task category и applicability остаются.
- Явное `БИФИТ Касса` + запрос о столах всё ещё может выбрать draft о web-бронировании при `task=None`; relationship detector/sufficiency policy не менялись.
- В `experiments/architecture_recovery_audit` есть сохранённый 24-case frozen JSON, но нет runnable replay harness; повторно исполнен действующий 15-case Stage3 E2E и весь pytest suite.

**Решение:** offline GO для этого ограниченного исправления; production/runtime GO не выдавался. Live Groq E2E заблокирован DNS, EDO Task Routing и BIFIT task/sufficiency блокеры остаются для последующих шагов. После отчёта работа остановлена.
