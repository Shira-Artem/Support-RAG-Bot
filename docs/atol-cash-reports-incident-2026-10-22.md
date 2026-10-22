# Инцидент: отчёты АТОЛ Онлайн, 22.10.2026

Источник фактов: `data/conversations.sqlite3`, сообщения 87–92. Активная коллекция зафиксирована в каждой диагностике: `knowledge_sprint_v1_20261022_quality_gate`. Запрос Qdrant на чтение подтвердил 2 чанка `atol-online-account-cash-reports`, статус `draft`; runtime работал с `demo=true`.

Карточка не попала в `candidates` ни разу. В исходном коде `retrieval.py` цифры `1.`, `2.`, `3.` из начала вопросов попадали в `codes`; каждый чанк без этой цифры исключался до расчёта BM25 и финального RRF. Dense позиции ниже воспроизведены чтением той же коллекции по сохранённым запросам после инцидента: исходная SQLite сохраняла score только для прошедших точек, поэтому их в ней нет.

| Ответ ID | DialogueState / операция | RAG query | Dense ранг целевой карточки | BM25 / финал до исправления | После исправления |
|---|---|---|---:|---|---:|
| 88 | `report/view_reports`, service=АТОЛ Онлайн | `сервис: АТОЛ Онлайн — просмотр отчётов — запрос клиента: 1. Где посмотреть отчёты по кассам после замены ФН в АТОЛ Онлайн?` | 1 | не рассчитан / отсутствует | 1 |

## Ответ 88

- `task_id`: `task:87`; переход: `new_task`.
- Целевая карточка в активной коллекции: есть; `task_category=cash_reports`, `operations=[view_cash_reports]`. В кандидатах: отсутствует.
- `evidence_status=none`, `sufficient=False`, `missing_evidence=[]`, `insufficiency_reason=no_task_matched_candidates`.
- `used_model=false`, `llm_call_attempted=false`, `generation_status=no_context`, `generation_reason=no_task_matched_candidates`.
- Ранний возврат сформирован в `app/answer_service.py` при `retrieval.sufficient=False`.
- Отклонённые кандидаты:

  - `atol-online-16668-fns-receipts-compliance`: `task_mismatch:receipt_search!=cash_reports`; RRF=0.044583, dense=0.61225784, BM25=8.89829.
  - `atol-online-14419-sugary-drinks-kkt-preparation`: `task_unconfirmed`; RRF=0.040045, dense=0.5284842, BM25=14.99561.
  - `atol-online-14145-closing-docs-april-2026`: `task_unconfirmed`; RRF=0.032787, dense=None, BM25=10.79226.
  - `atol-online-11078-change-plan`: `task_unconfirmed`; RRF=0.032258, dense=None, BM25=10.20666.
  - `atol-online-25514-referral-program-guide`: `task_unconfirmed`; RRF=0.031746, dense=None, BM25=9.82946.
  - `atol-online-18537-54fz-before-connecting`: `task_mismatch:equipment_setup!=cash_reports`; RRF=0.030769, dense=None, BM25=8.83224.
  - `atol-online-16667-ffd-105-vs-12-basics`: `task_unconfirmed`; RRF=0.030303, dense=None, BM25=8.81965.
  - `atol-online-25850-contacts`: `task_unconfirmed`; RRF=0.029851, dense=None, BM25=8.21937.
  - `atol-online-26409-tax-2026-vat-changes`: `task_unconfirmed`; RRF=0.029412, dense=None, BM25=8.0316.
  - `atol-online-11058-refund-unused-funds`: `task_unconfirmed`; RRF=0.028986, dense=None, BM25=6.63412.
  - `atol-online-16652-54fz-when-kkt-needed`: `task_mismatch:receipt_transmission!=cash_reports`; RRF=0.028571, dense=None, BM25=5.66623.
  - `atol-online-16656-patent-kkt-eligibility`: `task_unconfirmed`; RRF=0.028169, dense=None, BM25=5.37775.
  - `atol-online-14414-sugary-drinks-classification`: `task_unconfirmed`; RRF=0.027778, dense=None, BM25=5.26538.
  - `atol-online-16655-housing-utility-payments`: `task_unconfirmed`; RRF=0.027397, dense=None, BM25=4.10208.
  - `atol-online-18536-54fz-exemptions-diagnostics`: `task_unconfirmed`; RRF=0.027027, dense=None, BM25=3.71534.

| 90 | `report/view_reports`, service=АТОЛ Онлайн | `сервис: АТОЛ Онлайн — просмотр отчётов — запрос клиента: 2. Где посмотреть отчёты по кассам в АТОЛ Онлайн?` | 20 | не рассчитан / отсутствует | 2 |

## Ответ 90

- `task_id`: `task:87`; переход: `continue_task`.
- Целевая карточка в активной коллекции: есть; `task_category=cash_reports`, `operations=[view_cash_reports]`. В кандидатах: отсутствует.
- `evidence_status=none`, `sufficient=False`, `missing_evidence=[]`, `insufficiency_reason=no_task_matched_candidates`.
- `used_model=false`, `llm_call_attempted=false`, `generation_status=no_context`, `generation_reason=no_task_matched_candidates`.
- Ранний возврат сформирован в `app/answer_service.py` при `retrieval.sufficient=False`.
- Отклонённые кандидаты:

  - `atol-online-25514-referral-program-guide`: `task_unconfirmed`; RRF=0.045098, dense=0.55074847, BM25=9.88182.
  - `atol-online-16668-fns-receipts-compliance`: `task_mismatch:receipt_search!=cash_reports`; RRF=0.044071, dense=0.5693928, BM25=6.72231.
  - `atol-online-18537-54fz-before-connecting`: `task_mismatch:equipment_setup!=cash_reports`; RRF=0.038115, dense=0.47553056, BM25=7.3036.
  - `atol-online-14419-sugary-drinks-kkt-preparation`: `task_unconfirmed`; RRF=0.032787, dense=None, BM25=8.8394.
  - `atol-online-26409-tax-2026-vat-changes`: `task_unconfirmed`; RRF=0.032258, dense=None, BM25=8.07856.
  - `atol-online-22552-cashier-throughput`: `task_unconfirmed`; RRF=0.030769, dense=None, BM25=6.35902.
  - `atol-online-16656-patent-kkt-eligibility`: `task_unconfirmed`; RRF=0.030303, dense=None, BM25=6.16624.
  - `atol-online-16652-54fz-when-kkt-needed`: `task_mismatch:receipt_transmission!=cash_reports`; RRF=0.029851, dense=None, BM25=5.71115.
  - `atol-online-16667-ffd-105-vs-12-basics`: `task_unconfirmed`; RRF=0.029412, dense=None, BM25=5.57407.
  - `atol-online-18536-54fz-exemptions-diagnostics`: `task_unconfirmed`; RRF=0.028986, dense=None, BM25=4.44997.
  - `atol-online-14414-sugary-drinks-classification`: `task_unconfirmed`; RRF=0.028571, dense=None, BM25=4.21106.
  - `atol-online-16655-housing-utility-payments`: `task_unconfirmed`; RRF=0.028169, dense=None, BM25=4.15262.

| 92 | `report/view_reports`, service=АТОЛ Онлайн | `сервис: АТОЛ Онлайн — просмотр отчётов — запрос клиента: 3. Где посмотреть отчёты после замены ФН?` | 1 | не рассчитан / отсутствует | 1 |

## Ответ 92

- `task_id`: `task:87`; переход: `continue_task`.
- Целевая карточка в активной коллекции: есть; `task_category=cash_reports`, `operations=[view_cash_reports]`. В кандидатах: отсутствует.
- `evidence_status=none`, `sufficient=False`, `missing_evidence=[]`, `insufficiency_reason=no_task_matched_candidates`.
- `used_model=false`, `llm_call_attempted=false`, `generation_status=no_context`, `generation_reason=no_task_matched_candidates`.
- Ранний возврат сформирован в `app/answer_service.py` при `retrieval.sufficient=False`.
- Отклонённые кандидаты:

  - `atol-online-16668-fns-receipts-compliance`: `task_mismatch:receipt_search!=cash_reports`; RRF=0.043155, dense=0.5660786, BM25=5.94651.
  - `atol-online-14419-sugary-drinks-kkt-preparation`: `task_unconfirmed`; RRF=0.04, dense=0.5006283, BM25=11.74079.
  - `atol-online-25514-referral-program-guide`: `task_unconfirmed`; RRF=0.032787, dense=None, BM25=6.99307.
  - `atol-online-16667-ffd-105-vs-12-basics`: `task_unconfirmed`; RRF=0.032258, dense=None, BM25=6.68632.
  - `atol-online-18537-54fz-before-connecting`: `task_mismatch:equipment_setup!=cash_reports`; RRF=0.031746, dense=None, BM25=6.525.
  - `atol-online-26409-tax-2026-vat-changes`: `task_unconfirmed`; RRF=0.030769, dense=None, BM25=5.3883.
  - `atol-online-16656-patent-kkt-eligibility`: `task_unconfirmed`; RRF=0.030303, dense=None, BM25=3.92066.
  - `atol-online-14414-sugary-drinks-classification`: `task_unconfirmed`; RRF=0.029851, dense=None, BM25=3.85956.
  - `atol-online-16652-54fz-when-kkt-needed`: `task_mismatch:receipt_transmission!=cash_reports`; RRF=0.029412, dense=None, BM25=3.31601.
  - `atol-online-16655-housing-utility-payments`: `task_unconfirmed`; RRF=0.028986, dense=None, BM25=2.71577.
  - `atol-online-18536-54fz-exemptions-diagnostics`: `task_unconfirmed`; RRF=0.028571, dense=None, BM25=2.45973.

## Повторение отказа

Все сообщения 87, 89 и 91 остались в `task:87`; новые номера не добавили значимых фактов. Старый код повторил один и тот же шаблон отказа. Сообщение 93 уже было без номера и привело к другому, рискованному отказу (`rejected`), что дополнительно подтверждает роль числового фильтра. Исправление удаляет только номера списка из поисковых токенов и оставляет точные коды ошибок. Новый диалог при повторном `no_context` меняет ответ на просьбу о новой детали или предложении специалиста.
