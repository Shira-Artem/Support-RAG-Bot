"""Real bot baseline diagnostics on synthetic equipment-role questions."""
import asyncio
from types import SimpleNamespace
from run_telegram_equivalent_live import CASES, run

CASES.update({
    'role_compare': ['Для АТОЛ 30Ф нашёл инструкцию. Подойдёт ли она для моей кассы АТОЛ 55Ф?'],
    'role_peripheral': ['На кассе aQsi 5 подключён внешний сканер штрихкодов, он перестал считывать этикетки. Что проверить?'],
    'role_two': ['У нас две кассы Эвотор 6 и Эвотор 7.3, обе не передают чеки в ОФД. С чего начать?'],
})

if __name__ == '__main__':
    asyncio.run(run(SimpleNamespace(cases='role_compare,role_peripheral,role_two',
        output='reports/architecture_audit_20261101/b2_2b3_baseline_diagnostic_20261104.json', pause=0)))
