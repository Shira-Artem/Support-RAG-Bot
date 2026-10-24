# Model Benchmark A/B — Groq GPT-OSS 20B и 120B

Изолированный парный прогон 2026-10-24 на неизменённых 15 ходах пяти Oracle RAG сценариев. Меняется только `model`; source selection, системная инструкция, формат prompt, temperature `0.2`, reasoning effort `medium` и лимит `3072` completion tokens одинаковы. История каждого обращения развивается отдельно внутри каждой модели. Поэтому первый prompt сценария совпадает между моделями, а следующие могут различаться прошлым ответом соответствующей модели.

## Артефакты

- [Критерии до запуска](criteria.md) и исходная [Oracle-рубрика](../oracle_rag/criteria.md).
- [CLI](cli.py), [raw trace](results.json) с exact prompt, историей, evidence, настройками, ответом, usage и latency; [все сырые ответы для чтения](responses.md).
- [Ручная claim-level разметка](claims.py), [проверенный JSON](claim-review.json), [таблица 15 ходов](turn-comparison.md), [подробный отчёт](report.md).

## Повторение

Из корня репозитория:

```powershell
.\.venv\Scripts\python.exe experiments/model_benchmark/cli.py smoke
.\.venv\Scripts\python.exe experiments/model_benchmark/cli.py run --output experiments/model_benchmark/new-results.json
```

`smoke` делает только read-only проверку Oracle SHA, всех реплик/evidence/prompt, approved Qdrant chunks и доступности обеих моделей через Groq `/models`. Если модель не отображается активной, выполнение останавливается до генерации; подмены нет. Groq [API reference](https://console.groq.com/docs/api-reference) описывает `medium` для обеих GPT-OSS моделей. В рабочем прогоне обе модели вернули запрошенные ID и `finish_reason=stop` на всех ходах.

`run` запрещает перезаписывать файл, ограничен 30 attempts и 30 successful responses, не повторяет ошибочный запрос. Есть pacing между вызовами и ограничение оценённой скользящей суммы токенов. При provider error код и `retry-after` сохраняются без тела ошибки/ключа; история данного обращения для этой модели прекращается. В данном прогоне ошибок API не было. `review.py` проверяет, что каждая размеченная цитата встречается в неизменённом ответе, а `supported`-ссылка действительно указывает на раздел переданного документа; `results.json` он не изменяет.

Тестовые реплики синтетические. Нет записи в SQLite/Qdrant, индексации, Telegram или production-код. Секреты не сохраняются. Если ответ содержал бы email, телефон или ключ, CLI сохранил бы отредактированную копию с флагом; в этом прогоне `redaction_applied=false` у всех 30 ответов.
