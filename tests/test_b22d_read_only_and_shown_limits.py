"""Closed operation bridge, expansion and focused continuation safety contracts."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml

from app.dialogue_state import DialogueState, DialogueManager, Fact, ActiveRoute
from app.dialogue_understanding import validate_response
from app.procedure_policy import read_only_check_section, section_check_compatible
from app.rag import SearchResult
from app.retrieval_pipeline import RetrievalPipeline
from app.source_first_service import SourceFirstService, _sections, _source_sections, _shown_section_limit
from app.config import Settings

ROOT = Path(__file__).resolve().parents[1]
SAVED = json.loads((ROOT / 'reports/b2_2d_20261105/evidence_contract_live.json').read_text(encoding='utf-8'))


def settings(tmp_path):
    return Settings(telegram_bot_token='', openrouter_api_key='', openrouter_model='offline',
        app_name='test', app_url='http://localhost', show_sources=True, docs_dir=tmp_path,
        llm_provider='groq', groq_api_key='offline', groq_model='openai/gpt-oss-20b', rag_engine='source_first')


def second_state(cid):
    turn = next(t for t in SAVED['turns'] if t['case'] == cid and t['turn'] == 2)
    before = DialogueState.from_dict(turn['state_before'])
    raw = SAVED['understanding_calls'][turn['understanding_call_indices'][-1]]['structured_output']
    _, _, unknown, obs = validate_response(raw, turn['question'], 3, before)
    return turn, DialogueManager().advance(before, turn['question'], 3, observation=obs, unknown_facts=list(unknown))


class ApprovedArticle:
    def __init__(self, source):
        self.source = source
        _, front, body = (ROOT / 'data/knowledge' / source).read_text(encoding='utf-8').split('---', 2)
        self.meta = yaml.safe_load(front)
        self.hits = [SearchResult(source, heading + '\n' + text, .9,
            metadata={**self.meta, 'source': source, 'section': heading, 'chunk_index': index})
            for index, (heading, text) in enumerate(_sections(body))]

    def search(self, query, top_k=100):
        return self.hits

    def article(self, doc_id):
        return self.hits if doc_id == self.meta['document_id'] else []

    def search_for_state(self, state, query):
        return RetrievalPipeline(self).search(state, query)


@pytest.mark.parametrize('text', [
    '1. Проверить версию конфигурации.\n2. Сверить номер и сумму документа.',
    'Открыть журнал документов. Сверить дату документа с датой продажи.',
])
def test_closed_language_accepts_independent_read_only_inspections(text):
    assert read_only_check_section({'status': 'approved'}, text)


@pytest.mark.parametrize('text', [
    'Проверить версию и изменить документ.',
    'Открыть банковские выписки и загрузить файл.',
    'Сверить сумму; провести документ.',
    'Перечитать регистр и выполнить обработку.',
    'Открыть документ возврата.',
    'Проверить документ и дать документ банку.',
    'Проверить версию. Создать возврат.',
    'Если банк списал деньги, подтвердить документ.',
    'Не отражать возврат повторно другим способом.',
    'Проверить настройки неизвестным способом.',
])
def test_unknown_or_mutating_clauses_fail_closed(text):
    assert not read_only_check_section({'status': 'approved'}, text)


def test_b01_real_pipeline_limits_expansion_and_renders_without_planner(monkeypatch, tmp_path):
    turn, state = second_state('b01')
    assert state.operation == 'check'
    rag = ApprovedArticle('1c/bank/acquiring-returns.md')
    from app.rag_query import build_rag_query
    result = rag.search_for_state(state, build_rag_query(state))
    assert result.sufficient
    assert {h.metadata['section'] for h in result.documents} == {'Диагностика'}
    sections = _source_sections(rag, result, ROOT, 12)
    assert len(sections) == 1 and sections[0]['read_only_check_contract']

    async def no_planner(*args, **kwargs):
        pytest.fail('second turn must select from its proved section contract')
    monkeypatch.setattr('app.source_first_service.generate', no_planner)
    answer = asyncio.run(SourceFirstService(rag, settings(tmp_path), ROOT).answer(
        turn['question'], state=state, history=[{'role': 'assistant', 'content': 'previous response'}],
        coordinator_decision={'route': 'technical_action'}))
    assert answer.scenario == 'answer'
    assert 'Сверить документ банка с исходной продажей/возвратом' in answer.text
    assert 'не отражать возврат повторно' in answer.text
    assert not answer.progress_update.get('check_updates')


@pytest.mark.parametrize('operation', ['change', 'load_bank_statements', 'import_bank_statement_file', 'return', 'unknown'])
def test_read_only_bridge_never_admits_other_operations(operation):
    _, state = second_state('b01')
    state.operation = operation
    rag = ApprovedArticle('1c/bank/acquiring-returns.md')
    result = rag.search_for_state(state, 'Сверить документ банка с исходной продажей')
    # An exact metadata operation retains its normal route, never the bridge.
    assert not any('closed_read_only_section_contract' in c.relevance.reasons for c in result.candidates)
    if operation not in {'load_bank_statements', 'unknown'}:
        assert not result.documents


def test_foreign_service_draft_and_mutating_request_do_not_use_bridge():
    _, state = second_state('b01')
    rag = ApprovedArticle('1c/bank/acquiring-returns.md')
    foreign = deepcopy(state)
    fact = Fact.span('Saby', 3)
    foreign.task_context.entities = {'service': [fact]}
    foreign.task_context.active_route = ActiveRoute('service', fact)
    assert not rag.search_for_state(foreign, 'Saby: сверить документ банка').documents
    meta = {**rag.meta, 'section': 'Диагностика'}
    text = next(h.text for h in rag.hits if h.metadata['section'] == 'Диагностика')
    assert not section_check_compatible('check', {**meta, 'status': 'draft'}, text, 'bank_statement')
    assert not section_check_compatible('check', meta, text, 'bank_statement', 'Как изменить документ?')
    assert not rag.search_for_state(state, 'Как изменить документ?').documents


def test_h08_new_limit_question_reuses_source_without_progress_mutation(monkeypatch, tmp_path):
    turn, state = second_state('h08')
    rag = ApprovedArticle('evotor/marking/receive-marked-upd-prereqs.md')
    before = state.to_dict()
    first = next(t for t in SAVED['turns'] if t['case'] == 'h08' and t['turn'] == 1)
    async def no_planner(*args, **kwargs):
        pytest.fail('focused approved limitation requires no Planner answer')
    monkeypatch.setattr('app.source_first_service.generate', no_planner)
    answer = asyncio.run(SourceFirstService(rag, settings(tmp_path), ROOT).answer(
        turn['question'], state=state, history=[{'role': 'assistant', 'content': first['answer']}],
        coordinator_decision={'route': 'technical_action'}))
    assert answer.scenario_reason == 'source_first_focused_shown_limit'
    assert 'Перед подтверждением УПД сверяют' in answer.text
    assert 'Не подписывайте УПД до проверки товара.' in answer.text
    assert 'Unsupported document version' not in answer.text
    assert not answer.progress_update
    assert state.to_dict() == before


def test_unconfirmed_conditions_foreign_action_and_unshown_source_cannot_be_promoted():
    item = dict(id='s::limits', source='data/knowledge/a.md', document_id='s',
        text='Если поставка спорная, не подписывайте УПД до проверки товара.')
    history = [{'role': 'assistant', 'content': item['text'] + '\n' + item['source']}]
    assert not _shown_section_limit('Можно подписать документ?', item, [item], history)
    item['text'] = 'Не подписывайте УПД до проверки товара.'
    history = [{'role': 'assistant', 'content': item['text'] + '\n' + item['source']}]
    assert not _shown_section_limit('Можно оплатить документ?', item, [item], history)
    assert not _shown_section_limit('Можно подписать акт?', item, [item], history)
    assert not _shown_section_limit('Можно подтвердить документ?', item, [item], history)
    assert not _shown_section_limit('Можно подписать документ?', item, [item], [])
    # Even a claimed completed inspection grants no positive permission.
    quotes = _shown_section_limit('Товар проверили. Можно подписать документ?', item, [item], history)
    assert quotes == [(item, item['text'])]
