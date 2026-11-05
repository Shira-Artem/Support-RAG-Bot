"""Synthetic role-capability probe against Groq, without changing runtime."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import get_settings
from app.dialogue_state import DialogueState
import app.dialogue_understanding as understanding
import httpx

CASES = [
    ('reference_first', 'Для АТОЛ 30Ф нашёл инструкцию. Подойдёт ли она для моей кассы АТОЛ 55Ф?'),
    ('client_first', 'Моя касса Штрих-М 01Ф не печатает. Можно ли использовать инструкцию для Штрих-М 02Ф?'),
    ('peripheral', 'На кассе aQsi 5 подключён внешний сканер штрихкодов, он перестал считывать этикетки. Что проверить?'),
    ('two_owned', 'У нас две кассы Эвотор 6 и Эвотор 7.3, обе не передают чеки в ОФД. С чего начать?'),
    ('unknown', 'В документе упомянута касса АТОЛ 30Ф, а модель нашего оборудования пока неизвестна. Как проверить связь?'),
    ('negation', 'У меня не Эвотор 6, а Эвотор 7.3. Как проверить связь с ОФД?'),
]


async def main():
    out = ROOT / 'reports/architecture_audit_20261101/b2_2b3_role_understanding_live_retry_20261104.json'
    original_schema = understanding.response_schema
    original_post = httpx.AsyncClient.post
    records = []
    def schema():
        result = original_schema()
        entity = result['schema']['properties']['entities']['items']
        entity['properties']['role'] = {'type': 'string'}
        entity['required'].append('role')
        return result
    async def post(client, url, *args, **kwargs):
        req = kwargs.get('json')
        if req and str(url).startswith('https://api.groq.com/'):
            payload = json.loads(req['messages'][0]['content'])
            payload['rules'].append('For every equipment entity set role to client_equipment, referenced_equipment, peripheral, or uncertain according to its role in the current message. A mention alone does not establish client ownership. Include all named equipment mentions even if they are only references.')
            req['messages'][0]['content'] = json.dumps(payload, ensure_ascii=False)
        return await original_post(client, url, *args, **kwargs)
    def capture(**record):
        records.append(record)
    with patch.object(understanding, 'response_schema', schema), patch.object(understanding, '_append_local_trace', capture), patch.object(httpx.AsyncClient, 'post', post):
        for name, question in CASES:
            while True:
                try:
                    await understanding.understand_message(question, name, [], DialogueState(), get_settings())
                except Exception as exc:
                    print(name, type(exc).__name__, getattr(exc, 'http_status', None), flush=True)
                    out.write_text(json.dumps({'cases': CASES, 'records': records}, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
                    delay = getattr(exc, 'retry_after_seconds', None)
                    if getattr(exc, 'code', None) != 'groq_quota_deferred' or not delay:
                        break
                    await asyncio.sleep(delay + 1)
                    continue
                print(name, 'completed', flush=True)
                out.write_text(json.dumps({'cases': CASES, 'records': records}, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
                break

if __name__ == '__main__':
    asyncio.run(main())
