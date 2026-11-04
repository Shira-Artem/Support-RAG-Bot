"""Prespecified B2.2b.1 scenarios using the existing isolated live harness."""
import asyncio
import argparse
from types import SimpleNamespace
from run_telegram_equivalent_live import CASES, run

CASES.update({
    "b221_regression": ["У меня касса АТОЛ 30Ф, она же ATOL 30Ф. Чеки не доходят в Платформу ОФД. С чего начать проверку?"],
    "b221_other": ["На терминале Эвотор при продаже возникла ошибка ФН 235. С чего безопасно начать?"],
    "b221_separate": ["Производитель кассы Эвотор. Модель указана отдельно: 6. Документы застряли и не уходят оператору. Что проверить?"],
    "b221_conflict": ["Касса АТОЛ 30Ф показывает ошибку ФН 235. Можно ли применить инструкцию Эвотора для этой ошибки?"],
    "b221_switch": ["На кассе АТОЛ 30Ф документы не передаются в Платформу ОФД, с чего начать?", "Новая отдельная задача: на кассе Эвотор возникла ошибка ФН 235 при продаже. Что проверить?"],
})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="b221_regression,b221_other,b221_separate,b221_conflict,b221_switch")
    parser.add_argument("--output", default="reports/architecture_audit_20261101/b2_2b1_live_20261104.json")
    args = parser.parse_args()
    asyncio.run(run(SimpleNamespace(cases=args.cases, output=args.output, pause=12)))
