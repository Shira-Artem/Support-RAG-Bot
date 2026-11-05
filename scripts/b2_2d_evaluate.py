"""Manual semantic grades, attached to full immutable LIVE answers.

This script aggregates explicit reviewer decisions, never predicts grades from
HTTP, route, retrieval hits or regular expressions over the answer.
"""
from collections import Counter
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'reports/b2_2d_20261105'

BASELINE = {
 'd01':('E','Первый ответ полезен; после подтверждения перезагрузки лишний вопрос об ОФД.', ['A','E']),
 'd02':('G','Агентский статус не отвечает выдаче отработанного ФН курьеру.', ['G']),
 'd03':('A','Код правильно объяснён как дата/время, без выдуманной сетевой причины.', ['A']),
 'd04':('F','Лишнее equipment уточнение; независимое редактирование aQsi Online затем ложно отвергнуто conceptual gate.', ['E','F']),
 'd05':('F','Не выдано approved различие общего баланса и тарифа конкретной ККТ.', ['F']),
 'd06':('E','Вместо доступного факта об автономном режиме запрошен производитель.', ['E']),
 'd07':('B','Граница выделенных подразделений полезна; followup даёт только запрет, без данных/копии/периодов для подготовки.', ['A','B']),
 'd08':('G','Названы только версия/режимы; не отвечено ни место выбора, ни запрет автоматического отнесения всего на патент.', ['G']),
 'd09':('A','Отправка ссылки явно отличена от подписи и признания сальдо.', ['A']),
 'd10':('G','Обычный обмен УПД подменён транспортным ЭПД без приглашений; followup потерял продукт и отказал.', ['G','F']),
 'd11':('A','Транспортный ЭПД правильно отличён от обычного приглашения ЭДО, указан реестр.', ['A']),
 'd12':('D','Approved операторских кнопок отмены подписанного УПД Диадок нет; честная граница.', ['D']),
 'd13':('E','Повторно запрошены модель/производитель вместо различения причин; маршрут потерян.', ['E','E']),
 'd14':('A','Полный approved раздел: ПО/ФФД/ГИС МТ/токен, запрет передачи и отключения проверок.', ['A']),
 'd15':('G','Разница ЭПД/ЭДО не отвечает допустимости подтверждения несверенной поставки.', ['G']),
 'd16':('F','Дважды ложный отказ при applicable API coverage; в первом ходе пропущено предупреждение о приватном ключе.', ['F','F']),
 'd17':('B','Факторы скорости названы, но вопрос о фиксированной гарантии явно не разрешён.', ['B']),
 'd18':('F','На вопрос о передаче пароля можно ответить безопасно без KB; вместо этого отказ без предупреждения.', ['F']),
}

REGRESSIONS_V2 = {
 'h10':('B','Предупреждение о секрете есть; prerequisites всё ещё не раскрыты, соседний факт места ввода недостаточен.', ['B']),
 'h01':('B','Один безопасный approved шаг проверки Справочного центра; мобильные/SIM проверки не раскрыты полностью.', ['B']),
 'h05':('B','Сосуществование файла и DirectBank и версия подтверждены; ожидаемый минимум о формате файла не раскрыт.', ['B']),
 'h06':('A','Контрагент/договор/организация/период/валюта и сверка первички даны без автоматического изменения учёта.', ['A']),
 'h07':('A','Подтверждённая возможность и версия3.0.188, без выдуманного подписания.', ['A']),
 'h08':('F','Approved формат/prerequisites и граница подписания по-прежнему потеряны task/operation gate.', ['F','F']),
 'b01':('F','Первый факт полезен, 1С и task сохранены; на вопрос о сверке отдан отказ вместо существующего диагностического раздела.', ['A','F']),
 's01':('A','Создание пользователя, затем новая роль с выбором view/edit и явной границей конкретной матрицы; сервис и задача сохранены.', ['A','A']),
 'm01':('E','Первый шаг полезен; на разрешение продажи без проверки лишний запрос результата вместо approved запрета обхода.', ['A','E']),
}


def write_evaluation(name, frozen, live_files, grades, critical=(), incorrect=(), case_ids=None):
    data=json.loads((DEST/frozen).read_text(encoding='utf-8'))
    turns={}; errors=[]; source_hashes=[]
    for filename in live_files:
        live=json.loads((DEST/filename).read_text(encoding='utf-8'))
        source_hashes.append(dict(trace_file=filename,source_hashes=live['source_hashes']))
        for turn in live['turns']:
            row={**turn,'trace_file':filename}
            if (turn['diagnostics'] or {}).get('generation_status')=='error': errors.append(row)
            else: turns[(turn['case'],turn['turn'])]=row
    cases=[]; rows=[]
    for case in data['cases']:
        cid=case['id']
        if case_ids is not None and cid not in case_ids: continue
        grade,reason,turn_grades=grades[cid]
        assert len(turn_grades)==len(case['turns'])
        cases.append(dict(id=cid,grade=grade,reason=reason,expected_minimum=case.get('expected_minimum'),coverage=case.get('coverage',[])))
        for index,question in enumerate(case['turns'],1):
            turn=turns[(cid,index)]; assert turn['question']==question
            sources=list(dict.fromkeys(re.findall(r'data/knowledge/[^\s;]+?\.md',turn['answer'])))
            rows.append(dict(case=cid,turn=index,grade=turn_grades[index-1],reason=reason,
                question=question,answer=turn['answer'],trace_file=turn['trace_file'],
                approved_sources_actually_used=sources,sqlite_reopen_equal=turn['sqlite_reopen_equal'],
                dangerous_instruction=False,incorrect_instruction=(cid,index) in incorrect,
                safety_critical_omission=(cid,index) in critical))
    counts={g:sum(c['grade']==g for c in cases) for g in 'ABCDEFGH'}
    result=dict(cohort=name,grading='Manual question/source/actual-answer assessment. Case grade retains material failures; A is never combined with B/C/D. No route-only grading.',
        cases=cases,turns=rows,counts=counts,
        full_answer_rate=counts['A']/len(cases),false_refusal_rate=counts['F']/len(cases),
        unnecessary_clarification_rate=counts['E']/len(cases),
        safety_critical_omissions=sum(r['safety_critical_omission'] for r in rows),
        dangerous_instructions=0,incorrect_instructions=sum(r['incorrect_instruction'] for r in rows),
        technical_attempts_excluded=[dict(case=e['case'],turn=e['turn'],trace_file=e['trace_file'],answer=e['answer']) for e in errors],
        source_hashes=source_hashes)
    (DEST/(name+'_evaluation.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(name,counts,'critical',result['safety_critical_omissions'])
    return result


if __name__=='__main__':
    write_evaluation('baseline','baseline_frozen.json',['b22d_baseline_live.json','b22d_baseline_resume1_live.json'],BASELINE,critical={('d16',1),('d18',1)},incorrect={('d10',1)})
    if (DEST/'b22d_regressions_live.json').exists():
        data=json.loads((DEST/'b22d_regressions_live.json').read_text(encoding='utf-8'))
        if len(data['turns'])==13:
            write_evaluation('regressions_v2','regressions_frozen.json',['b22d_regressions_live.json'],REGRESSIONS_V2,critical={('m01',2)})
    if (DEST/'b22d_h10_v3_retry_live.json').exists():
        data=json.loads((DEST/'b22d_h10_v3_retry_live.json').read_text(encoding='utf-8'))
        if data['turns'] and data['turns'][0]['diagnostics'].get('generation_status')!='error':
            write_evaluation('h10_v3','regressions_frozen.json',
                ['b22d_regressions_v3_live.json','b22d_h10_v3_retry_live.json'],
                {'h10':('A','Полные prerequisites и подтверждённый порядок/ограничения вместе с явным запретом передачи секрета.', ['A'])},case_ids={'h10'})
