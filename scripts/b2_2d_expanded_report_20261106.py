"""Summarize recorded LIVE results; never invokes the provider."""
import json
import sqlite3
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root / 'reports/b2_2d_20261105'
reviews = {
 'd10': [('B', 'Подпись недостаточна, но прямо не разобран уже названный случай разных операторов.'), ('B', 'Все пять пунктов исходного раздела, но повторена известная подпись и добавлено служебное ограничение.')],
 'm01': [('A', 'Предложено открыть предупреждение у проблемной позиции.'), ('B', 'Запрет обхода присутствует, но рядом нерелевантные перерегистрация и ФН.')],
 'u01': [('B', 'Есть осторожность при переносе, но прямое условие о ранее использованном ФН не выбрано.')],
 'u02': [('F', 'Ложный отказ при наличии ранее выявленного approved ограничения совместимости.')],
 'N01': [('F', 'Отказ, хотя approved статья о счёте есть и была отвергнута по task mismatch.'), ('F', 'Повторный отказ при наличии approved ограничения по старому счёту.')],
 'N01_after': [('B', 'Назван раздел кабинета и поддержка; лишнее ограничение о старом счёте и служебная цитата.'), ('B', 'Есть запрет оплаты без проверки, но формулировка служебная и цитата об области применения лишняя.')],
 'N02': [('B', 'Верная дата пробития и маршрут, но много дополнительных условий.'), ('B', 'ФН не подменён ФД/ФП и отсутствие функции не утверждается; лишний блок условий.')],
 'N03': [('B', 'Названа совместимость физического сканера, но нет полезной конкретной проверки DataMatrix.'), ('F', 'Вместо ответа о смене USB-режима запрашивается результат прежней проверки.')],
 'N04': [('A', 'Не утверждает обязательную замену и предлагает проверить дату/время.'), ('F', 'Игнорирует сообщённую неправильную дату и снова просит результат проверки.')],
 'N05': [('B', 'Полезная сверка и осторожность, но лишний пункт о подписании через ЭДО.'), ('A', 'Исправление закрытого периода согласуется с бухгалтером; неподтверждённой проводки нет.')],
 'N06': [('F', 'Задача не определена; инструкции по приглашению нет.'), ('F', 'Отказ вместо инструкции по сотруднику; операция Диадока не перенесена.')],
 'N07': [('F', 'Вместо определения ФН выдана область применения источника.')],
 'negative': [('B', 'Адреса и порты не придуманы, но вопрос об ОФД не отвечает запросу и специалист не предложен.')],
}
lines = ['# B2.2d — расширенный LIVE, 06.11.2026', '',
         '**IN_PROGRESS / quality NO-GO / frozen holdout NO-GO.** Реальный Groq, bot.handle_message, read-only Stage3, отдельная SQLite на сценарий. Первоначальные прогоны — HEAD f743a619 до изменения runtime; N01_after — после изменения маршрутизации. Десять отложенных frozen-сценариев не запускались.', '',
         'Новые вопросы заморожены до запуска отдельно: [manifest](expanded_live_manifest_20261106.json), SHA-256 `f7cbb2d34126d6cf62f62b5130df5f67bed2386a416fad692c87f398a8abb3d0`. Из holdout использованы только ранее разрешённые u01/u02.', '']
total = Counter(); turns = 0; reopen = 0; dbcount = 0
for case, ratings in reviews.items():
    path = folder / f'expanded_live_20261106_{case}.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    assert len(data['turns']) == len(ratings)
    http = data.get('http_trace', [])
    total.update(str(h['http_status']) for h in http)
    tokens = sum((h.get('usage') or {}).get('total_tokens') or 0 for h in http)
    total['tokens'] += tokens
    total['unknown_usage'] += sum(not h.get('usage') for h in http)
    private = root / '.local' / ('telegram-equivalent-' + path.stem)
    for db in private.glob('*.sqlite3'):
        with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as conn:
            assert conn.execute('pragma quick_check').fetchone()[0] == 'ok'
        dbcount += 1
    lines += [f'## {case}', '', f'[Полная трасса]({path.name}): Understanding, TaskContext, candidates/rejected/reasons, Planner, SourceFirst, Ledger до/после, HTTP, usage и состояния после reopen. HTTP: {len(http)}, tokens: {tokens}.', '']
    for t, (grade, reason) in zip(data['turns'], ratings):
        turns += 1
        reopen += bool(t['sqlite_reopen_equal'])
        diag = t.get('diagnostics') or {}
        lines += [f"### Ход {t['turn']} — {grade}", '', '**Вопрос:** ' + t['question'], '', '**Ответ:**', '', '```text', t['answer'], '```', '', f"**Оценка:** {reason} Причина pipeline: `{diag.get('scenario_reason')}`. SQLite reopen: `{t['sqlite_reopen_equal']}`. Задержка хода: {t['latency_ms']} мс.", '']
lines += ['## Причины, исправление и ограничения', '',
 '- N01: Understanding дал billing, но общее выражение о облачной кассе сработало раньше billing в `_state_task_category`; approved `renewal-invoice.md` отвергнут `task_mismatch:billing!=settings`. Условный приоритет billing требует и intent billing, и собственного признака billing в тексте. N01 повторён LIVE; получены оба ответа выше. Прочие исходные сценарии после изменения не повторялись.',
 '- m01: Planner выбрал применимый раздел с запретом обхода, SourceFirst скопировал его целиком вместе с чужой тематикой. Это не устранено.',
 '- u02: фильтрация оставила пустой набор (`no_task_matched_candidates`); ранее обнаруженное approved ограничение не дошло до ответа. u01 выбрал общую статью вместо прямого условия. Не устранено.',
 '- N03/N04: Planner выбрал раздел, но guard ProgressLedger потребовал результат ранее показанного шага, не отвечая на новое содержание. Для N04 пользователь сообщил конкретный результат; обобщённое безопасное сопоставление с ledger не доказано. Не устранено.',
 '- N07: информационный селектор выбрал цитату об области применения вместо определения, хотя определение было среди approved evidence. Не устранено.',
 '- N06: первая реплика получила `dialogue_state_unresolved`, вторая — `no_task_matched_candidates`. Отрицательный контроль не выдал адреса, но запросил ОФД вместо специалиста. Не устранено.',
 '- d10: все пять исходных пунктов вышли без объявления их выполненными, однако известная подпись повторена; общий учёт известных фактов остаётся открытым.',
 '', f'Всего: {turns} ходов, {reopen}/{turns} SQLite reopen equality; {dbcount} SQLite/checkpoint quick_check=ok; HTTP {dict((k,v) for k,v in total.items() if k not in ("tokens", "unknown_usage"))}; подтверждённый usage {total["tokens"]} tokens, неизвестный usage ответов {total["unknown_usage"]}. Исходные отдельные базы находятся в `.local/telegram-equivalent-expanded_live_20261106_*`.',
 '', 'Stage3 934/green и полный id/payload SHA `9c0b418d56afd8c12aad5125d5a4b0c2d62ec491f03fd91b63e7fddb8b3e4b63`, а также хеши защищённых файлов совпали с предыдущим сохранённым снимком `fixes_integrity_before.json`; непосредственно перед запуском новый снимок не снимался. Контейнер существующего Qdrant был остановлен и запущен для доступа к Stage3; API использовался только на чтение. Production и Telegram pilot не запускались.',
 '', 'Профиль: 25 passed. Первый запуск нового теста имел FrozenInstanceError из-за изменения immutable Fact; исправлена только тестовая конструкция, повтор прошёл. Полный pytest и финальный статус см. в журнале проекта.',
 '', 'Кандидат не готов к независимому frozen holdout: ошибки памяти, релевантности и полезности ответа остаются на нескольких разных доменах. Требуются общие контракты и отрицательные контроли; не добавлять фразовые исключения и не менять approved KB без согласования.']
(folder / 'expanded_live_report_20261106.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('turns', turns, 'reopen', reopen, 'sqlite', dbcount, 'stats', dict(total))
