"""Prespecified B2.2b.2 scenarios via the isolated read-only live harness."""
import argparse
import asyncio
from types import SimpleNamespace
from run_telegram_equivalent_live import CASES, run

CASES.update({
    "b222_regression": ["На терминале Эвотор при продаже возникла ошибка ФН 235. С чего безопасно начать?"],
    "b222_other": ["На aQsi при закрытии архива ФН появляется ошибка 115. Какие безопасные проверки доступны до изменения настроек?"],
    "b222_unknown_model": ["Касса Эвотор: номер фискального документа известен, как повторно распечатать именно этот документ на кассе?"],
    "b222_wrong_model": ["На Эвотор 7.3 хочу повторно распечатать фискальный документ по известному номеру ФД. Подойдёт ли порядок для Эвотор 6?"],
    "b222_followup": ["На кассе Эвотор возник код 3922: часы терминала расходятся с фискальным модулем. С чего безопасно начать?", "Последний чек нашёл: время на нём правильное. Модель кассы Эвотор 7.3. Что проверить дальше?"],
    "b222_software": ["В 1С-ЭПД при отправке транспортной накладной получаю «контрагент в хранилище не найден». Нужны ли приглашения для перевозочных документов?"],
})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="b222_regression,b222_other,b222_unknown_model,b222_wrong_model,b222_followup,b222_software")
    parser.add_argument("--output", default="reports/architecture_audit_20261101/b2_2b2_live_20261104.json")
    args = parser.parse_args()
    asyncio.run(run(SimpleNamespace(cases=args.cases, output=args.output, pause=12)))
