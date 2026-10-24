# V1.2-A — изолированный Typed Claim Validator

`validator.py` — независимый offline API: `Claim`, `Evidence`, `Scope`, `Decision`, `validate_claim`, `validate_ledger`, `coverage`. Никаких импортов production, БД, сети или LLM. Позиция claim — точный `answer[start:end]`; evidence — точный clause внутри approved source. `NEEDS_REVIEW` не является разрешением.

Запуск из корня проекта:

```powershell
py -3.14 -m pytest -q tests/test_typed_claim_validator.py
py -3.14 experiments/typed_claim_validator/replay.py
```

Replay проверяет SHA frozen raw ответов, ручной разметки и четырёх локальных approved источников, сверяет exact per-turn evidence. Старые ручные статусы используются только для оценки. Входы и baseline: [аудит V1.1](../claim_validation_audit/report.md), [решения V1.1](../claim_validation_audit/claim-decisions.json), [ручная разметка](../model_benchmark/claim-review.json).

- [report.md](report.md) — метод, итоги и решение по gate;
- [journal.md](journal.md) — ход, гипотезы и отрицательные результаты;
- [summary.json](summary.json) — агрегаты;
- [decisions.json](decisions.json) — все 316 verdict с причинами;
- [coverage.json](coverage.json) — ограничения по каждому из 30 ответов;
- [holdout_protocol.md](holdout_protocol.md) — протокол будущего независимого набора, зафиксированный до следующей настройки.

**Граница:** автоматического извлечения атомарных claims, типизации действий и всех содержательных spans из произвольного ответа здесь нет. Replay использует старые короткие цитаты как вход, а не доказывает способность найти все утверждения. `coverage.certified=false` для всех 30 ответов. Для внедрения нужен независимый extractor с собственной проверкой полноты и semantic verifier для парафраз, плюс holdout. В production не подключать.
