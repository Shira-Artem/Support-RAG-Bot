import json
from pathlib import Path

from app.dialogue_state import DialogueManager, DialogueState, Fact, Observation
from app.dialogue_understanding import validate_response
from app.rag_query import build_rag_query


def test_saved_live_continuation_without_optional_spans_is_retained():
    path = Path(__file__).resolve().parents[1] / 'reports/b2_2d_20261105/b22d_regressions_live.json'
    trace = json.loads(path.read_text(encoding='utf-8'))
    state = DialogueState()
    for turn in [t for t in trace['turns'] if t['case'] == 'b01']:
        raw = trace['understanding_calls'][turn['understanding_call_indices'][-1]]['structured_output']
        _, _, unknown, observation = validate_response(raw, turn['question'], turn['turn'], state)
        state = DialogueManager().advance(state, turn['question'], turn['turn'], observation=observation, unknown_facts=list(unknown))
    assert state.details[-1].value == turn['question']
    assert turn['question'] in build_rag_query(state)


def test_empty_continuation_does_not_add_context_and_new_task_does_not_inherit():
    manager = DialogueManager()
    first = 'Проверить подключение сервиса.'
    state = manager.advance(DialogueState(), first, 1, observation=Observation(intent='general', operation='explain', relation='new_task', request_type='information', evidence=Fact.span(first, 1)))
    text = 'Что дальше?'
    continued = manager.advance(state, text, 2, observation=Observation(intent='general', operation='explain', relation='continue', request_type='information', evidence=Fact.span(text, 2)))
    assert not continued.details
    text = 'Другой вопрос: как найти сотрудника?'
    changed = manager.advance(continued, text, 3, observation=Observation(intent='access', operation='search', relation='new_task', request_type='information', evidence=Fact.span(text, 3)))
    assert changed.task_id != state.task_id
    assert first not in build_rag_query(changed)

def test_b01_saved_followup_can_render_new_diagnostic_section(monkeypatch, tmp_path):
    import asyncio
    from types import SimpleNamespace
    from app.config import Settings
    from app.llm_client import Generation
    from app.rag import SearchResult
    from app.retrieval_pipeline import RetrievalResult, EvaluatedDocument, Relevance
    from app.source_first_service import SourceFirstService, _sections
    root = Path(__file__).resolve().parents[1]
    trace = json.loads((root/'reports/b2_2d_20261105/b22d_regressions_live.json').read_text(encoding='utf-8'))
    turns = [t for t in trace['turns'] if t['case']=='b01']
    state = DialogueState()
    for turn in turns:
        raw = trace['understanding_calls'][turn['understanding_call_indices'][-1]]['structured_output']
        _, _, unknown, obs = validate_response(raw, turn['question'], turn['turn'], state)
        state = DialogueManager().advance(state, turn['question'], turn['turn'], observation=obs, unknown_facts=list(unknown))
    source = '1c/bank/acquiring-returns.md'
    body = (root/'data/knowledge'/source).read_text(encoding='utf-8').split('---',2)[2]
    scope = {'document_id':'batch-20261013-bank-acquiring-returns', 'source':source, 'status':'approved',
             'service':'1С:Бухгалтерия 8', 'manufacturer':'1С', 'model':'1С:Бухгалтерия 8, редакция 3.0',
             'task_category':'bank_statement', 'operations':['load_bank_statements']}
    hits = [SearchResult(source, text, .9, metadata={**scope,'section':heading}) for heading,text in _sections(body)]
    selected = EvaluatedDocument(source, scope['document_id'], 'approved', scope, {}, Relevance('match','match',.9),selected=True)
    retrieval = RetrievalResult('query',[selected],[],hits,True,None,' '.join(h.text for h in hits),evidence_status='source_confirmed')
    class Rag:
        retriever = SimpleNamespace(store=SimpleNamespace(collection='offline'))
        def search_for_state(self, _state, query):
            assert turns[-1]['question'] in query
            return retrieval
    async def planner(messages, settings, *, call_stage='generation'):
        payload=json.loads(messages[-1]['content'])
        chosen=next(s for s in payload['candidate_sections'] if s['section']=='Диагностика')
        return Generation(json.dumps({'mode':'select','section_id':chosen['id'],'applicability_confirmed':True,'source_order_complete':True,'reason':'current follow-up'}), 'offline')
    monkeypatch.setattr('app.source_first_service.generate',planner)
    settings=Settings(telegram_bot_token='',openrouter_api_key='',openrouter_model='model',app_name='test',app_url='http://localhost',show_sources=True,docs_dir=tmp_path,llm_provider='groq',groq_api_key='test',groq_model='openai/gpt-oss-20b',rag_engine='source_first')
    answer=asyncio.run(SourceFirstService(Rag(),settings,root).answer(turns[-1]['question'],state=state,
        history=[{'role':'assistant','content':turns[0]['answer']}],coordinator_decision={'route':'technical_action'}))
    assert answer.scenario == 'answer'
    assert 'Сверить документ банка с исходной продажей/возвратом' in answer.text
    assert 'не отражать возврат повторно' in answer.text
    assert answer.text != turns[0]['answer']
