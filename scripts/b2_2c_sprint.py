"""Frozen B2.2c independent live quality sprint. No runtime replacements."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'reports/b2_2c_20261104'

# Expected outcomes are evidence minima, not expected literal answers.
BASELINE = [
('k01', 'kkt', ['На Эвотор 7.3 выскочила ФН 234. Это уже обязательно менять накопитель или можно сначала что-то проверить?', 'Дата на экране правильная, а время пока не сверял. С чего продолжить?'], ['evotor/fn/fn-234.md'], 'Проверить дату и время; замена не автоматический вывод, регистрационные действия специалисту.'),
('k02', 'kkt', ['На aQsi 5 кончилась лента прямо при продаже. Бумагу вставили, покупатель уже заплатил. Как допечатать, чтобы не пробить второй чек?'], ['aqsi_devices/errors/paper-print-retry.md'], 'Проверить существующий чек в истории, повтор печати; не создавать второй фискальный чек.'),
('k03', 'kkt', ['В АТОЛ Онлайн хочу заранее понять, сколько ещё проживёт ФН у каждой нашей кассы. Где это видно?'], ['atol_online/fn/monitoring.md'], 'Мониторинг касс, виджет прогнозируемого времени эксплуатации ФН; границы срока/заполненности.'),
('k04', 'kkt', ['Эвотор 7.3 ругается на ФН 212 при попытке работы. Что означает этот код?'], ['evotor/fn/fn-212.md'], 'Объяснить код по источнику, различить регистрацию и неисправность; не выполнять регистрацию.'),
('o01', 'ofd', ['Платформа ОФД показывает ФЛК 507 у одного чека. Что там не сходится и какие данные приготовить поддержке?', 'То есть просто отправить этот же чек ещё раз будет достаточно?'], ['platformaofd/flk/flk-507.md'], 'Несоответствие итога и форм оплаты, реквизиты/теги; повтор не обещает исправления.'),
('o02', 'ofd', ['В Платформе ОФД хочу убрать запасную кассу из текущих отчётов на пару месяцев. Архив в кабинете для этого подходит?'], ['platformaofd/ofd/archive-kkt.md'], 'Назначение архива, отсутствие активного тарифа; не снятие с учёта ФНС.'),
('o03', 'ofd', ['В АТОЛ Онлайн собираюсь выгрузить чеки за прошлую неделю одним файлом, а не открывать каждый. Где начать?'], ['atol_online/receipts/receipt-journal-export.md'], 'Применимый порядок журнала/экспорта и фильтра периода из источника.'),
('o04', 'ofd', ['В Платформе ОФД надо найти номер установленного ФН, коробка потерялась. Это видно в кабинете?'], ['platformaofd/fn/fn-number-in-lkk.md'], 'Карточка ККТ/номер ФН по статье; не выдумывать значение.'),
('b01', 'bank', ['В 1С:Бухгалтерии 3.0.207 банк отдельно списал деньги за возврат покупателю по карте. Какая операция для этого предусмотрена?', 'Банк списал отдельно, из следующего поступления ничего не удерживал. Что сверить, чтобы не отразить возврат дважды?'], ['1c/bank/acquiring-returns.md'], 'Списание с расчётного счёта/Возврат по эквайрингу с 3.0.207; сверить схему банка и исходный возврат, без двойного отражения.'),
('b02', 'bank', ['1С:Бухгалтерия 3.0.195: хочу, чтобы ДиректБанк сам забирал выписки утром. От чего зависит такая возможность?'], ['1c/bank/directbank-auto-schedule.md'], 'Расписание с 3.0.195, поддержка банка, интервалы/готовность выписки; без выдуманных кнопок.'),
('b03', 'bank', ['Наш банк не умеет прямой обмен с 1С. В Бухгалтерии 3.0.203 есть вариант забирать его выписки через банк-посредник?'], ['1c/bank/directbank-other-banks.md'], 'Возможность с 3.0.203, зависит от посредника/списка банков, не универсальный импорт.'),
('b04', 'bank', ['После загрузки выписки в 1С вижу два одинаковых платежа. Можно просто массово удалить дубли? Банк и релиз сейчас назвать не могу.'], ['1c/bank/import-file-directbank.md','1c/bank/directbank-auto-schedule.md'], 'Без массового удаления; сверка оригинала/проводок, уточнение банка/версии или специалист.'),
('e01', 'edo', ['Жду закрывающие от АТОЛ Онлайн через Диадок. Где принять приглашение именно от них?', 'Теперь отдельный вопрос: как в aQsi Online восстановить забытый пароль?'], ['atol_online/edo/incoming-documents.md','aqsi_online/account/reset-password.md'], 'Контрагенты/Приглашают вас/ООО АТОЛ ОНЛАЙН; затем новая задача сброса без переноса scope.'),
('e02', 'edo', ['Собираемся подключить 1С-ЭДО для УПД новому поставщику. Какие сведения подготовить перед настройкой?'], ['1c/edo/connect-1c-edo.md'], 'Конфигурация/релиз, подпись, операторы/роуминг, приглашение, тип документов.'),
('e03', 'edo', ['В Диадоке документ висит с надписью «Ожидается аннулирование». Кто должен нажать какую кнопку, чтобы снять его окончательно?'], [], 'Проверить отсутствие операторской процедуры; честная граница, без выдуманного аннулирования.'),
('e04', 'edo', ['В Saby сотрудник случайно отклонил входящий акт. Как вернуть его в прежнее состояние?'], [], 'Проверить покрытие; не переносить инструкции других операторов, специалист при отсутствии процедуры.'),
('m01', 'marking', ['На Эвотор 7.3 при оплате пишет «Марка не была проверена». Как выяснить, какая позиция мешает?', 'Предупреждение у одной бутылки нашёл. Можно её пока продать без проверки?'], ['evotor/marking/code-check-error-first-steps.md'], 'Открыть описание проблемной позиции/точную ошибку; не обходить проверку.'),
('m02', 'marking', ['На физической aQsi 5 хотим подключить весы ШТРИХ-СЛИМ 200. Какая связь и где проверить, что касса их видит?'], ['aqsi_devices/peripherals/scales.md'], 'USB-C/Hub, Настройки/Основные настройки/Весы, USB permission; применимость пары.'),
('m03', 'marking', ['В Платформе ОФД жёлтый показатель ЦРПТ. Это уже доказанное нарушение или надо открыть конкретные чеки?'], ['platformaofd/marking/crpt-indicators.md'], 'Жёлтый требует проверки, отчёт маркировки; один цвет не доказательство нарушения.'),
('m04', 'marking', ['Для интеграции с АТОЛ Онлайн хочу сначала гонять тестовые чеки, не боевые. Что предусмотрено для проверки API?'], ['atol_online/integration/api-test.md','atol_online/integration/test-cashier.md'], 'Тестовая среда/касса по документации; не создавать боевую фискализацию.'),
('s01', 'other', ['В aQsi Online новый сотрудник, своей записи у него ещё нет. Как завести ему вход в кабинет?', 'Роль ещё не создали. Где задать ей права просмотра и редактирования?'], ['aqsi_online/account/add-user.md','aqsi_online/account/create-role.md'], 'Пользователи/Добавить/имя/email/роль; создание роли и выбор инструментов, без обещаний скрытых полномочий.'),
('s02', 'other', ['В aQsi Online хочу получать каждый день отчёт по чекам на почту. Есть такая настройка в профиле?'], ['aqsi_online/account/settings.md'], 'Общее/автоматическая отправка отчёта за день; не придумывать расписание.'),
('s03', 'other', ['Объясните без сложных слов: зачем интеграции нужен HTTP-статус и чем 404 отличается от 500?'], [], 'Общее корректное объяснение, явно model knowledge, без притворного approved источника.'),
('s04', 'other', ['Можете сказать, оплачен ли у нашей организации тариф aQsi Online на следующий месяц? Доступа в кабинет под рукой нет.'], [], 'Персональный статус неизвестен; кабинет/уполномоченная поддержка, не выдумывать оплату.'),
]

def freeze():
 import difflib, re, yaml, subprocess
 DEST.mkdir(parents=True,exist_ok=True)
 old=[]
 def walk(v):
  if isinstance(v,dict):
   for k,x in v.items():
    if k in ('question','user_message','user_text') and isinstance(x,str): old.append(x)
    elif k=='role' and x=='user' and isinstance(v.get('content'),str): old.append(v['content'])
    else: walk(x)
  elif isinstance(v,list):
   for x in v: walk(x)
 files=list((ROOT/'reports/architecture_audit_20261101').glob('b2*.json'))
 for p in files:
  try: walk(json.loads(p.read_text(encoding='utf-8-sig')))
  except (ValueError,UnicodeError): pass
 normalize=lambda s: re.sub(r'\W+',' ',s.lower()).strip()
 cases=[]
 for cid,group,turns,sources,minimum in BASELINE:
  coverage=[]
  for source in sources:
   p=ROOT/'data/knowledge'/source; text=p.read_text(encoding='utf-8-sig'); m=yaml.safe_load(text.split('---',2)[1]); assert m['status']=='approved'
   coverage.append({'source':source,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'metadata':m,'body':text.split('---',2)[2]})
  nearest=[]
  for q in turns:
   rank=sorted(((difflib.SequenceMatcher(None,normalize(q),normalize(x)).ratio(),x) for x in set(old)),reverse=True)
   nearest.append({'question':q,'previous_nearest':[{'ratio':round(r,4),'question':x} for r,x in rank[:3]]})
   assert not rank or rank[0][0]<.86,(cid,rank[0])
  cases.append({'id':cid,'group':group,'turns':turns,'expected_minimum':minimum,'coverage':coverage,'novelty':nearest})
 data={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'previous_live_files':[str(p.relative_to(ROOT)) for p in files], 'previous_questions':len(set(old)), 'rubric':{'A':'полный полезный ответ','B':'полезный неполный','C':'необходимое уточнение','D':'обоснованный KB gap/специалист','E':'ложное уточнение','F':'ложный отказ','G':'неверный/нерелевантный; danger отмечается отдельно','H':'технически незавершённый'},'evaluation':'По каждому ходу и всему диалогу вручную; A отдельно от B/C/D; KB и general knowledge отдельно. Полный ответ оценивается относительно вопроса, не нахождения статьи.','cases':cases}
 p=DEST/'baseline_frozen.json'
 if p.exists():
  p=DEST/'baseline_frozen_v2.json'; assert not p.exists()
  data['amendment']='Before any b01 provider call: manual semantic audit excluded all-accounts question as same scenario as B2.1 despite lexical difference. Replaced with acquiring-return accounting, same group and turn count. v1 preserved. k01 alone already attempted; no replaced-case output observed; runtime unchanged.'
 p.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 print('Frozen',len(cases),'cases',sum(len(x['turns']) for x in cases),'turns; prior',len(set(old)),'questions; SHA256',hashlib.sha256(p.read_bytes()).hexdigest())

if __name__=='__main__':
 parser=argparse.ArgumentParser(); parser.add_argument('--freeze',action='store_true'); parser.add_argument('--cases'); parser.add_argument('--not-before-utc'); parser.add_argument('--output'); args=parser.parse_args()
 if args.freeze: freeze()
 else:
  if not args.output: parser.error('--output is required for LIVE; use a new unique run name to preserve previous SQLite/traces')
  from b2_2c_live_harness import CASES,run
  frozen=DEST/'baseline_frozen_v2.json'
  data=json.loads((frozen if frozen.exists() else DEST/'baseline_frozen.json').read_text(encoding='utf-8'))
  CASES.update({x['id']:x['turns'] for x in data['cases']})
  async def scheduled_run():
   if args.not_before_utc:
    from datetime import datetime,timezone
    deadline=datetime.fromisoformat(args.not_before_utc)
    assert deadline.tzinfo is not None
    while (delay:=(deadline-datetime.now(timezone.utc)).total_seconds())>0:
     print('Provider cooldown; seconds remaining',round(delay),flush=True)
     await asyncio.sleep(min(30,delay))
   await run(SimpleNamespace(cases=args.cases or ','.join(x['id'] for x in data['cases']),output=args.output,pause=12))
  asyncio.run(scheduled_run())
