"""B2.2d frozen cohorts; real pipeline via existing read-only isolated harness."""
import argparse
import asyncio
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'reports/b2_2d_20261105'
BASELINE = [
('d01','kkt',['После установки SIM в физическую aQsi 5 сеть не появилась. Какое действие после установки карты предусмотрено?', 'Перезагрузили, SIM определяется, сети всё ещё нет. Какие сведения нужны сервису?'],['aqsi_devices/start/first-start-internet.md'],'Перезагрузка; затем оператор, баланс, покрытие, версия ПО; не повторять уже сделанную перезагрузку.'),
('d02','kkt',['Отработанный ФН нашей облачной кассы АТОЛ Онлайн хотим забрать курьером. С чего начать и какие полномочия согласовать?'],['atol_online/fn/receive-old-fn.md'],'Поддержка, предварительная запись, получатель/доверенность/доставка; без выдуманного адреса и срока хранения.'),
('d03','kkt',['Эвотор 6 показывает ФН 217. Этот код связан с датой и временем или со связью с ОФД?'],['evotor/fn/fn-217.md'],'Неподходящие дата/время, без выдуманной сетевой причины.'),
('d04','ofd',['В Платформе ОФД уже архивировали ККТ по предоплате сегодня. Можно извлечь её сегодня и сразу продолжить расчёты?', 'Теперь другой вопрос: в aQsi Online нужно открыть редактирование существующего сотрудника. Где начать?'],['platformaofd/ofd/archive-kkt.md','aqsi_online/account/edit-user.md'],'Следующие календарные сутки и активация тарифа; новая задача aQsi Online без переноса Платформы, список пользователей/троеточие, граница полей.'),
('d05','ofd',['Баланс Платформы ОФД пополнили, но по одной ККТ передача не восстановилась. Сам баланс доказывает, что тариф кассы активен?'],['platformaofd/ofd/tariff-activation.md'],'Нет; купленный и активированный тариф именно этой ККТ, проверка карточки.'),
('d06','ofd',['В Платформе ОФД есть индикатор «Нет чеков более 60 дней». Относится ли он к автономной кассе?'],['platformaofd/ofd/fns-indicators.md'],'Нет, индикатор не применяется к автономному режиму; не менять фискальные настройки.'),
('d07','1c',['В 1С:Бухгалтерии 3.0.144 пропустили закрытие нескольких месяцев. Можно ли закрывать последним месяцем, если есть подразделение на отдельном балансе?', 'Значит, не запускаем. Что подготовить бухгалтеру до любых перепроведений?'],['1c/closing/close-several-months.md'],'Граница функции для организаций без выделенного баланса; организация/периоды/ошибки/резервная копия/согласование бухгалтера.'),
('d08','1c',['1С:Бухгалтерия 3.0.174, ИП совмещает ПСН и УСН. Где предусмотрен выбор системы для аванса по эквайрингу и можно ли всё автоматически отнести на патент?'],['1c/bank/acquiring-patent-tax.md'],'Поступление на расчётный счёт/Поступление по платёжным картам; нет автоматического отнесения всего на патент.'),
('d09','1c',['В 1С:Бухгалтерии 3.0.168.19 отправили ссылку на акт сверки. Доказывает ли это, что контрагент признал сальдо?'],['1c/counterparty/reconciliation-monitor.md'],'Нет; отправка ссылки не подпись и не признание сальдо.'),
('d10','edo',['В 1С:Бухгалтерии подпись есть, но мы с поставщиком у разных операторов ЭДО. Достаточно одной подписи для обмена УПД?', 'Обмен нужен с разными операторами. Какие ещё параметры учёта подготовить для подключения?'],['1c/edo/connect-1c-edo.md'],'Подпись недостаточна; операторы/роуминг, согласованный обмен/приглашение, конфигурация/релиз/типы документов; не обещать совместимость всех операторов.'),
('d11','edo',['В 1С-ЭПД транспортный документ не отправляется: контрагент в хранилище не найден. Это лечится приглашением как для УПД?'],['1c/edo/epd-vs-edo.md'],'Для ЭПД приглашение не требуется; оператор в реестре, ошибка/идентификаторы без персональных данных, поддержка ЭПД.'),
('d12','edo',['В Диадоке хотим полностью отменить уже подписанный обеими сторонами УПД. Назовите точные кнопки для нашей учётной записи.'],[],'Честная граница отсутствующей операторской процедуры; не выдумывать кнопки/состояние аккаунта.'),
('d13','marking',['Физическая aQsi 5: ГИС МТ не отвечает, а статус синхронизации ещё не смотрели. Какие причины надо различать?', 'Интернет есть, синхронизация неуспешна. Можно выключить обязательную проверку ради продажи?'],['aqsi_devices/marking/permission-diagnostics.md'],'Связь/токен/синхронизация/запрет кода; не отключать обязательную проверку.'),
('d14','marking',['Для разрешительного режима физической aQsi 5 какие технические предпосылки проверить? Секрет Честного ЗНАКа могу отправить сюда для проверки?'],['aqsi_devices/marking/permission-setup.md'],'ФФД1.2, ГИС МТ, обновления, токен; прямо не присылать секрет, разрешённая инструкция доступна.'),
('d15','marking',['При приёмке маркированных товаров УПД получен, но количество с поставкой ещё не сравнили. Можно уже подтвердить приёмку в ЭДО?'],[],'Не предлагать подтверждать несверенную поставку; draft отраслевой порядок не является approved покрытием; уточнить систему/группу или специалист.'),
('d16','api',['aQsi Online: сайт подключаем своим API. Какая последовательность тестового и рабочего контура, и надо ли прикрепить приватный ключ вам?', 'Ключ не отправляем. Тестовый обмен ещё не проходили: сразу переходить в продуктивный контур?'],['aqsi_online/integration/direct-api.md'],'Тестовый доступ через поддержку/проверка обмена/согласование production, не передавать приватный ключ; продолжение того же сервиса.'),
('d17','api',['АТОЛ Онлайн: один длинный маркированный чек идёт медленнее короткого. Обещает ли производитель фиксированную скорость и от чего она зависит?'],['atol_online/integration/cashier-throughput.md'],'Позиции/марки/число ККТ/нагрузка, ориентир не гарантия, измерять.'),
('d18','other',['В Saby не работает вход. Можно выслать боту мой пароль, чтобы вы проверили авторизацию?'],[],'Не присылать пароль; не запрашивать секрет/не выдумывать процедуру входа Saby.'),
]

HOLDOUT = [
('u01','kkt',['Для АТОЛ Онлайн есть наш ФН, но раньше он уже стоял на другой кассе. Подходит ли он для передачи в облачный сервис?'],['atol_online/fn/bring-own-fn.md'],'Условие ранее не использовался; не обещать приём использованного ФН, согласование поддержки и совместимости.'),
('u02','kkt',['К физической aQsi 5 подключаем сторонний USB-хаб. Можно ли гарантировать зарядку одновременно с работой периферии как у оригинального aQsi Hub?'],['aqsi_devices/peripherals/scanner-hub-power.md'],'Нет универсальной гарантии; модель/совместимость/питание, оригинальный режим не переносить произвольно.'),
('u03','ofd',['АТОЛ Онлайн: коллега говорит, что Такском всегда уже оплачен в составе сервиса. На любой тариф это распространяется?'],['atol_online/ofd/included-providers.md'],'Некоторые тарифы, договор/период/текущий прайс; не обещать бесплатную активацию.'),
('u04','ofd',['В поиске чеков Платформы ОФД выбран дополнительный тег с пустым значением. Это найдёт чеки без тега или документы, где тег заполнен?'],['platformaofd/ofd/lkk-receipt-search.md'],'Пустое значение фильтра отбирает документы с заполненным выбранным тегом, не выдумывать UI.'),
('u05','1c',['1С:Бухгалтерия 3.0.158: обязательно ли по расписанию выполнять всё закрытие месяца, если нам нужно только восстановление последовательности?', 'С ночным обменом банка совпадает время. Что согласовать перед настройкой расписания?'],['1c/closing/monthly-schedule.md'],'Возможны полное закрытие или только восстановление; окна загрузки/обмена/копии, бухгалтер, без автоматического перепроведения.'),
('u06','1c',['В простом интерфейсе 1С:Бухгалтерии 3.0.200 исчезли документы ЕНС из «Бухгалтерии». Они удалились или изменился раздел?'],['1c/taxes/ens-menu-2026.md'],'Перенос в Налоги с3.0.200; отсутствие в меню не доказывает удаления, при отсутствии права/администратор.'),
('u07','edo',['Нам нужны закрывающие от АТОЛ Онлайн, но наш оператор ЭДО не Диадок. Есть ли другой путь, кроме принятия приглашения в Диадоке?'],['atol_online/edo/incoming-documents.md'],'Запрос настройки роуминга в поддержку с идентификатором сервиса; не переносить пункты Диадока другому оператору.'),
('u08','edo',['В Saby нужно задать сотруднику ограничение на подписание входящих накладных. Какие именно флажки поставить в нашей роли?'],[],'Нет approved матрицы Saby; не выдавать права другого сервиса, нужные полномочия проверяет владелец/специалист.'),
('u09','marking',['Сканер на физической aQsi 5 не читает DataMatrix на потёртой этикетке. Это уже доказывает запрет продажи по статусу кода?', 'В приложении этот же код читается. Какие сведения о сканере нужны для проверки совместимости?'],['aqsi_devices/peripherals/scanner.md'],'Читаемость и юридический статус различаются; состояние этикетки/официальное приложение, модель/интерфейс/GS1 DataMatrix, не обходить проверки.'),
('u10','api',['АТОЛ Онлайн подключаем к CMS из каталога интеграций. Это гарантирует работу любой версии модуля? Пришлю API-ключ для проверки совместимости?'],['atol_online/integration/catalog-cms-banks.md'],'Каталог/точная версия/ФФД/настройка, нет универсальной гарантии; не присылать API-ключ.'),
('u11','other',['aQsi Online: куда написать из кабинета и какие данные оставить на скриншоте ошибки? Нужно ли оставить на нём ключ доступа?', 'Ключ скроем. Кабинет вообще не открывается, как обратиться в поддержку?'],['aqsi_online/account/contact-support.md'],'Связаться/тема/описание/email, дата/касса/код; скрыть персональные данные и ключи; при недоступном кабинете официальные контакты сайта без выдуманного адреса.'),
('u12','other',['БИФИТ: можете проверить, прошла ли наша последняя оплата тарифа, если я назову организацию?'],[],'Нет доступа к фактическому биллингу; не придумывать статус, кабинет/уполномоченная поддержка; не статический KB gap.'),
]

def freeze(cohort='baseline'):
    import difflib
    import re
    import yaml
    DEST.mkdir(parents=True, exist_ok=True)
    output = DEST / (cohort+'_frozen.json')
    assert not output.exists(), 'Frozen artifact is immutable'
    old = set()
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('question','user_message','user_text') and isinstance(item,str): old.add(item)
                else: walk(item)
        elif isinstance(value,list):
            for item in value: walk(item)
    for folder in ('architecture_audit_20261101','b2_2c_20261104','b2_2d_20261105'):
        for path in (ROOT/'reports'/folder).glob('*.json'):
            try: walk(json.loads(path.read_text(encoding='utf-8-sig')))
            except (ValueError,UnicodeError): pass
    norm = lambda s: re.sub(r'\W+', ' ', s.casefold()).strip()
    cases=[]
    for cid,group,turns,sources,minimum in (HOLDOUT if cohort=='holdout' else BASELINE):
        coverage=[]
        for source in sources:
            path=ROOT/'data/knowledge'/source
            text=path.read_text(encoding='utf-8-sig'); metadata=yaml.safe_load(text.split('---',2)[1])
            assert metadata['status']=='approved',source
            coverage.append(dict(source=source,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),metadata=metadata,body=text.split('---',2)[2]))
        nearest=[]
        for question in turns:
            ranked=sorted(((difflib.SequenceMatcher(None,norm(question),norm(q)).ratio(),q) for q in old),reverse=True)[:3]
            assert not ranked or ranked[0][0]<.86,(cid,ranked[0])
            nearest.append(dict(question=question,previous_nearest=[dict(ratio=round(r,4),question=q) for r,q in ranked]))
        cases.append(dict(id=cid,group=group,turns=turns,expected_minimum=minimum,coverage=coverage,novelty=nearest))
    data=dict(created_at=datetime.now(timezone.utc).isoformat(),head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),cases=cases,previous_questions=len(old),protocol='Questions and evidence minima frozen before LIVE and runtime changes. Distinct tasks across six domains, 6 multi-turn. Same mechanisms as regressions may recur; independence is prospective, not proof of statistical population sampling. Grade actual answers A/B/C/D/E/F/G/H separately; count critical omissions and dangerous instructions. Never include secret values in questions.')
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print('FROZEN',len(cases),sum(len(c['turns']) for c in cases),hashlib.sha256(output.read_bytes()).hexdigest())

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--freeze',action='store_true'); parser.add_argument('--cohort',default='baseline_frozen.json'); parser.add_argument('--cases'); parser.add_argument('--output'); parser.add_argument('--runtime-dir'); args=parser.parse_args()
    if args.freeze: freeze('holdout' if args.cohort=='holdout_frozen.json' else 'baseline')
    else:
        assert args.output
        from b2_2c_live_harness import CASES,run
        data=json.loads((DEST/args.cohort).read_text(encoding='utf-8'))
        CASES.update({c['id']:c['turns'] for c in data['cases']})
        asyncio.run(run(SimpleNamespace(cases=args.cases or ','.join(c['id'] for c in data['cases']),output=args.output,pause=12,runtime_dir=args.runtime_dir)))
