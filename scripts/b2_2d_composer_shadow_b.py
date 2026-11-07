"""Isolated shadow generation using frozen A data only; no store or retrieval."""
import asyncio,json,sys
from dataclasses import asdict
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
load_dotenv(ROOT/'.env',override=False)
from app.config import get_settings
from app.llm_client import generate
from app import groq_rate_limit
P=ROOT/'reports/b2_2d_20261106'; OUT=P/'composer_shadow_b.json'
groq_rate_limit._TRACE=ROOT/'.local/composer-shadow-b-http.jsonl'
async def main():
    rows=json.loads((P/'composer_shadow_inputs.json').read_text(encoding='utf8'))['turns']
    priority={'1c':0,'fn':1,'danger':2,'hub':3,'unknown':4,'cash':5,'ofd':6,'edo':7,'receipt':8}
    rows.sort(key=lambda r:(priority.get(r['case'],9),r['turn']))
    out=json.loads(OUT.read_text(encoding='utf8')) if OUT.exists() else {'method':'Shadow B using frozen A pre-turn state and exact approved result payload; no bot, store, ledger or retrieval calls.','turns':[],'errors':[]}
    done={(r['case'],r['turn']) for r in out['turns']}
    for row in rows:
        if (row['case'],row['turn']) in done: continue
        messages=[{'role':'system','content':'Ты помощник технической поддержки. Ответь пользователю естественно, самостоятельно сформулировав ответ. Используй только подтверждённую память и приведённые approved evidence. Не добавляй неподтверждённые факты, причины, меню, технические или опасные действия. Не считай предположения клиента проверенными результатами. Если evidence недостаточно, честно скажи об этом и предложи обратиться к специалисту или уточнить данные. Сохраняй применимые условия и ограничения источника. Текст ответа клиенту без служебных комментариев.'}, {'role':'user','content':json.dumps(row['input'],ensure_ascii=False)}]
        try:
            result=await generate(messages,get_settings(),call_stage='shadow_composer')
            out['turns'].append({'case':row['case'],'turn':row['turn'],'input_sha256':row['input_sha256'],'generation':asdict(result)})
        except Exception as e:
            out['errors'].append({'case':row['case'],'turn':row['turn'],'type':type(e).__name__,'message':str(e),'status':getattr(e,'http_status',None),'retry_after_seconds':getattr(e,'retry_after_seconds',None)})
            OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8'); print('STOP',out['errors'][-1],flush=True); return
        OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
        print(row['case'],row['turn'],result.text,flush=True)
        await asyncio.sleep(12)
asyncio.run(main())
