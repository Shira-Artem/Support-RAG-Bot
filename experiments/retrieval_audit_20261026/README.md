# Артефакты аудита

- [report.md](report.md) — метод, метрики, потери, metadata analysis, FN 234/235 и приоритеты.
- [questions_gold.jsonl](questions_gold.jsonl) — 54 анонимизированных реальных turn queries и предварительная gold-разметка.
- [annotation_protocol.md](annotation_protocol.md) — правила выборки, gold и границы retrieval.
- [preflight.json](preflight.json) — read-only Qdrant preflight и конфигурация коллекции.
- [approved_document_inventory.jsonl](approved_document_inventory.jsonl) — payload metadata approved Stage3 chunks; `text` исключён.
- [retrieval_results.jsonl](retrieval_results.jsonl) — кандидаты, ranks, applied filters, section data.
- [metrics.json](metrics.json) — общий Recall и point-level metadata coverage.
- [metrics_by_task_category.json](metrics_by_task_category.json) и [metrics_by_service.json](metrics_by_service.json) — разрезы с размером выборки.
- [loss_reasons.csv](loss_reasons.csv) / [loss_reasons.jsonl](loss_reasons.jsonl) — все потери правильных источников после фильтров.
- [soft_ranking_formula.json](soft_ranking_formula.json) — фиксированные аналитические веса и hard gates.
- [input_hashes.json](input_hashes.json) — хеши retrieval-кода и sanitized source snapshots.
- [run_audit.py](run_audit.py) — воспроизводимый offline/read-only runner.
