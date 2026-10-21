"""Offline seven-turn replay: local cards, lexical candidates, recorded LLM text.

No application runtime, credentials, embeddings, SQLite writes or Qdrant calls.
This verifies state, gates and response repair; it is not a live model evaluation.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.answer_service import AnswerService
from app.config import Settings
from app.dialogue_state import DialogueManager, DialogueState
from app.knowledge import Chunker, DocumentLoader
from app.llm_client import Generation
from app.rag import SearchResult, _char_ngrams, _cosine, _norm
from app.rag_query import build_rag_query
from app.retrieval_pipeline import RetrievalPipeline


class LocalCards:
    def __init__(self):
        root = ROOT / 'data/knowledge'
        loader, chunker = DocumentLoader(root), Chunker()
        self.chunks = [chunk for p in sorted(root.rglob('*.md')) for chunk in chunker.split(loader.load(p))]
        self.vectors = [(v, _norm(v)) for v in (_char_ngrams(c.text + ' ' + c.metadata['title']) for c in self.chunks)]
        self.pipeline = RetrievalPipeline(self)

    def search(self, query, top_k=100):
        vector = _char_ngrams(query); norm = _norm(vector)
        scored = sorted(((i, _cosine(vector, norm, v, n)) for i, (v, n) in enumerate(self.vectors)),
                        key=lambda pair: pair[1], reverse=True)
        return [SearchResult(self.chunks[i].metadata['source'], self.chunks[i].text, score,
                             lexical_score=score, metadata=self.chunks[i].metadata) for i, score in scored[:top_k]]

    def article(self, document_id):
        return [SearchResult(c.metadata['source'], c.text, 0, metadata=c.metadata)
                for c in self.chunks if c.metadata['document_id'] == document_id]

    def search_for_state(self, state, query):
        return self.pipeline.search(state, query)


async def replay():
    recorded = json.loads((ROOT / 'tests/fixtures/telegram-2026-10-21.json').read_text(encoding='utf-8'))
    source = LocalCards()
    # Explicit settings with a patched provider; never use configured credentials.
    settings = Settings(telegram_bot_token='', openrouter_api_key='', openrouter_model='offline',
                        app_name='offline', app_url='http://localhost', show_sources=False,
                        docs_dir=ROOT / 'data/knowledge', groq_api_key='offline-replay', llm_provider='groq')
    service, manager = AnswerService(source, settings), DialogueManager()
    states, rows = {}, []
    for turn in recorded['turns']:
        user, diagnostic = turn['user'], turn['diagnostics']
        previous = states.get(user['conversation_id'], DialogueState())
        state = manager.advance(previous, user['content'], user['id'])
        prompts = []
        async def recorded_generation(messages, config):
            prompts.append(messages)
            raw = diagnostic.get('raw_model_text')
            if not raw:
                # Historical turn 59 never called LLM; this is an explicit stub,
                # not an invented historical model answer or a quality claim.
                raw = json.dumps({'scenario': 'answer', 'response': 'В кабинете откройте раздел «Чеки» и задайте период.'})
            return Generation(raw, 'offline-recorded-output')
        with patch('app.answer_service.generate', recorded_generation):
            answer = await service.answer(user['content'], state=state)
        after_answer = manager.observe_answer(state, scenario=answer.scenario, reason=answer.scenario_reason,
                                              question=answer.text, message_id=user['id'] + 1,
                                              slot=answer.clarification_slot)
        states[user['conversation_id']] = after_answer
        rows.append(dict(message_id=user['id'], message=user['content'], before=previous.to_dict(),
                         after_user=state.to_dict(), after_answer=after_answer.to_dict(),
                         query=build_rag_query(state), answer=asdict(answer),
                         simulated_generation_calls=len(prompts), prompt=prompts,
                         output_kind='recorded' if diagnostic.get('raw_model_text') else 'explicit_stub'))
    return rows


def main():
    rows = asyncio.run(replay())
    out = ROOT / 'docs/incidents/2026-10-21'
    (out / 'replay.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Проверка семи сообщений после исправления', '',
             'Офлайн: все локальные карточки, символьный лексический поиск, штатный RetrievalPipeline. '
             'Платных вызовов — 0. Qdrant и dense retrieval не использованы. '
             'Генератор заменён сохранёнными ответами; для id=59 — явно помеченной заглушкой. '
             'Это проверка состояния, выбора знания и ремонта ответа, не измерение качества новой генерации.', '']
    for row in rows:
        s = row['after_user']; a = row['answer']; r = a['retrieval_diagnostics'] or {}
        lines += [f"## {row['message_id']}. {row['message']}", '',
                  f"Переход: {s['transition']}; task={s['task_id']}; {s['intent']} / {s['operation']} / {s['object']}", '',
                  'Сущности: ' + json.dumps(s['entities'], ensure_ascii=False), '',
                  f"RAG: {row['query']}", '',
                  'Выбрано: ' + ', '.join(item['source'] for item in r.get('selected', [])), '',
                  f"Достаточно: {r.get('sufficient')}; имитаций генерации: {row['simulated_generation_calls']}", '',
                  'Результат проверки с записанным ответом:', '', a['text'], '']
    (out / 'replay.md').write_text('\n'.join(line.rstrip() for line in lines), encoding='utf-8')
    print(f'Replayed {len(rows)} messages; paid calls=0')


if __name__ == '__main__':
    main()
