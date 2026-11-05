"""Local corpus audit and pending independent holdout preparation, no network/LLM."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import yaml

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'reports/b2_2c_20261104'

HOLDOUT=[
 ('h01','kkt',['Эвотор 7.2 перестал выходить в интернет через SIM, по Wi-Fi работает. Что безопасно проверить по мобильной связи?'],['evotor/network/mobile-internet-first-checks.md'],'Проверки мобильного канала из источника, без переноса ОФД-инструкции и сброса настроек.'),
 ('h02','kkt',['На aQsi 5 индикатор мигает красным, касса долго лежала без зарядки. С чего начать?'],['aqsi_devices/errors/red-blinking-battery.md'],'Различить быстрое мигание и ровный свет; по статье быстрое мигание указывает на замену аккумулятора; проверить питание/аренду и поставщика, не разбирать корпус.'),
 ('h03','ofd',['Платформа ОФД пишет ФЛК 508. Правильно понимаю, проблема с датой чека, а не с оплатой?'],['platformaofd/flk/flk-508.md'],'Объяснить точный 508, не 507; проверить время без неподтверждённой корректировки расчёта.'),
 ('h04','ofd',['В Платформе ОФД касса попала в фильтр «Регистрация ККТ не завершена». Как проверить, действительно ли оформление в налоговой закончено?'],['platformaofd/fn/registration-status.md'],'Сверить отчёт на кассе и заявку/карточку регистрации в ФНС; не менять регистрационные параметры самостоятельно.'),
 ('h05','bank',['В 1С:Бухгалтерии 3.0.117 подключён ДиректБанк, но бухгалтер прислал выписку файлом. Чтобы загрузить файл, обмен с банком придётся отключить?'],['1c/bank/import-file-directbank.md'],'Не обязательно отключать; возможность с 3.0.117, формат и контроль дублей.'),
 ('h06','bank',['В 1С хочу свериться с контрагентом и понять расхождения, не меняя проведённые документы. С чего начать акт сверки?'],['1c/counterparty/reconciliation-act.md'],'Применимые сведения акта сверки; контрагент/период, не исправлять учёт автоматически.'),
 ('h07','edo',['В 1С один УПД от поставщика, а товар нужно принять на два склада. Есть ли штатная возможность так распределить?'],['1c/goods/single-upd-many-warehouses.md'],'Только подтверждённая версия и возможность, без выдуманного процесса подписания.'),
 ('h08','edo',['При приёмке УПД на Эвотор 7.3 появилось Unsupported document version. Что это может означать?', 'Товар ещё не сверяли. Можно уже подтвердить документ?'],['evotor/marking/receive-marked-upd-prereqs.md'],'Старый неподдерживаемый формат как возможность, не доказанная причина; не подписывать до сверки.'),
 ('h09','marking',['У aQsi Hub периодически отваливается подключённая периферия. Может ли дело быть в питании самого хаба?'],['aqsi_devices/peripherals/scanner-hub-power.md'],'Проверки питания по статье; не обещать совместимость произвольного устройства.'),
 ('h10','marking',['На физической aQsi 5 настраиваем разрешительный режим. Какие условия нужны до добавления токена и можно ли прислать токен вам?'],['aqsi_devices/marking/permission-setup.md'],'ПО/ФФД1.2/токен/синхронизация; не раскрывать токен, не отключать проверки.'),
 ('h11','other',['В aQsi Online забыли, где список касс с номерами ККТ и ФН. В каком разделе искать?'],['aqsi_online/account/my-cash-registers.md'],'Мои кассы и подтверждённые колонки, без выдуманных прав/регистрационных действий.'),
 ('h12','other',['У АТОЛ Онлайн добавляем ещё один адрес интернет-магазина для той же кассы. Какой порядок предусмотрен?'],['atol_online/settings/add-more-shop-urls.md'],'Точный подтверждённый порядок и ограничения статьи; без переноса на физическую кассу.'),
]

def main():
 docs=[]
 for p in sorted((ROOT/'data/knowledge').rglob('*.md')):
  s=p.read_text(encoding='utf-8-sig'); parts=s.split('---',2)
  if len(parts)<3: continue
  m=yaml.safe_load(parts[1]) or {}
  docs.append({'path':str(p.relative_to(ROOT)).replace('\\','/'),'metadata':m,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'body':parts[2]})
 groups={'evotor_receipt_copy':r'восстанов\w*.*чек|повтор\w*.*печат|копи\w*.*чек|печат\w*.*номер',
 'diadoc':r'диадок|diadoc','saby':r'\bsaby\b|сбис',
 'directbank':r'директбанк|directbank','aqsi_peripheral':r'aqsi|акси','bifit':r'бифит|bifit'}
 matches={k:[{'path':d['path'],'status':d['metadata'].get('status'),'title':d['metadata'].get('title'),'service':d['metadata'].get('service'),'model':d['metadata'].get('model'),'operations':d['metadata'].get('operations'),'evidence_coverage':d['metadata'].get('evidence_coverage'),'sha256':d['sha256']} for d in docs if re.search(pattern,json.dumps(d,ensure_ascii=False,default=str),re.I)] for k,pattern in groups.items()}
 result={'kind':'Full local frontmatter/body scan; lexical matches are candidates, not automatic semantic coverage verdicts. Manual decisions in kb_gap_matrix.csv.','document_counts':dict(Counter(d['metadata'].get('status') for d in docs)),'groups':matches}
 (DEST/'kb_coverage_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 baseline=json.loads((DEST/'baseline_frozen_v2.json').read_text(encoding='utf-8'))
 previous=[]
 def walk(v):
  if isinstance(v,dict):
   for k,x in v.items():
    if k in ('question','user_message','user_text') and isinstance(x,str): previous.append(x)
    else: walk(x)
  elif isinstance(v,list):
   for x in v: walk(x)
 for p in (ROOT/'reports/architecture_audit_20261101').glob('b2*.json'):
  try: walk(json.loads(p.read_text(encoding='utf-8-sig')))
  except ValueError: pass
 previous.extend(q for c in baseline['cases'] for q in c['turns'])
 import difflib
 norm=lambda s: re.sub(r'\W+',' ',s.lower()).strip()
 rows=[]
 for cid,group,turns,sources,minimum in HOLDOUT:
  coverage=[d for d in docs if d['path'].removeprefix('data/knowledge/') in sources]
  assert len(coverage)==len(sources) and all(d['metadata']['status']=='approved' for d in coverage)
  nearest=[]
  for q in turns:
   ranks=sorted([(difflib.SequenceMatcher(None,norm(q),norm(x)).ratio(),x) for x in set(previous)],reverse=True)
   nearest.append({'question':q,'nearest_previous':ranks[:3]})
   assert ranks[0][0]<.86,(cid,ranks[0])
  rows.append({'id':cid,'group':group,'turns':turns,'expected_minimum':minimum,'coverage':coverage,'novelty':nearest})
 (DEST/'holdout_reserved_NOT_RUN.json').write_text(json.dumps({'status':'RESERVED_NOT_RUN. Prepared during quota cooldown; not an AFTER result and not a passed independent holdout. Must recheck novelty and freeze after proven fixes before execution.','cases':rows},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 print(result['document_counts']); print('Holdout reserved',len(rows)); print({k:len(v) for k,v in matches.items()})

if __name__=='__main__': main()
