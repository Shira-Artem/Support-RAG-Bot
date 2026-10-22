import asyncio
from types import SimpleNamespace

from app.answer_service import AnswerService
from app.dialogue_state import DialogueManager, DialogueState, Fact
from app.knowledge import DocumentLoader, Chunker
from app.rag import SearchResult
from app.retrieval_pipeline import RetrievalPipeline, normalize_metadata, _procedure_matches
from test_expert import settings
from test_retrieval_pipeline import Source, _state


def hit(text, **metadata):
    return SearchResult(metadata.pop('source', 'aqsi_online/account/guide.md'), text, .04,
                        metadata={'document_id': 'guide', 'category': 'account', 'service': 'aQsi Online',
                                  'status': 'draft', **metadata})


def test_partial_existing_user_instructions_survive_without_fabricated_permissions(monkeypatch, tmp_path):
    instruction = hit('В списке «Пользователи» найдите существующую запись. '
                      'Меню с троеточием позволяет выбрать изменение записи.',
                      task_category='access', operations=['edit_user'], section='Открыть редактирование',
                      evidence_coverage={'change_permissions': 'partial'})
    warning = hit('Источник не подтверждает сохранение новой роли. Не выдавайте создание за изменение.',
                  task_category='access', operations=['edit_user'], section='Граница подтверждения')
    # The actual dense hit is the limitation; expansion must preserve the
    # separately chunked, confirmed navigation despite its sparse vocabulary.
    pipeline = RetrievalPipeline(Source([warning], {'guide': [instruction, warning]}))
    state = _state('Как изменить права существующего сотрудника в aQsi Online?')
    result = pipeline.search(state, 'aQsi Online изменение прав')
    assert result.documents and result.candidates and not result.rejected
    assert not result.sufficient and result.evidence_status == 'partial'
    assert all('не подтверждает' not in step['text'] for step in result.supported_steps)
    async def no_generation(*args):
        raise AssertionError('Partial source instructions do not need a paid call')
    monkeypatch.setattr('app.answer_service.generate', no_generation)
    rag = SimpleNamespace(search_for_state=lambda *args: result)
    answer = asyncio.run(AnswerService(rag, settings(tmp_path)).answer('Изменить права', state=state))
    assert answer.scenario == 'answer' and answer.generation_status == 'partial'
    assert 'троеточием' in answer.text and 'Полный порядок изменения прав' in answer.text
    assert not answer.llm_call_attempted


def test_relevance_and_reviewed_generic_workflow_do_not_prove_specific_permissions():
    instruction = hit('Создайте пользователя, укажите имя и email, назначьте роль и сохраните запись.',
                      task_category='access', operations=['add_employee'],
                      source_url='https://vendor.example/guide', source_checked_at='2026-10-22',
                      evidence_coverage={'add_employee': 'full'})
    pipeline = RetrievalPipeline(Source([instruction]))
    generic = _state('Как создать пользователя в aQsi Online?')
    assert pipeline.search(generic, 'aQsi Online создание пользователя').sufficient
    specific = DialogueManager().advance(generic, 'Хочу, чтобы он смотрел кассы, но не менял настройки.', 2)
    result = pipeline.search(specific, 'aQsi Online пользователь права')
    assert result.documents and not result.sufficient
    assert 'requested_role_or_permissions_unverified' in result.missing_evidence
    named = _state('Как создать пользователя с ролью «Менеджер» в aQsi Online?')
    assert not pipeline.search(named, 'aQsi Online роль Менеджер').sufficient


def test_warning_text_cannot_override_explicit_operations_or_supply_missing_steps():
    creation = hit('Источник не описывает изменение существующего пользователя.',
                   title='Добавление сотрудника', task_category='access', operations=['add_employee'],
                   section='Ограничения', evidence_coverage={'change_permissions': 'full'})
    state = _state('Как изменить права существующего сотрудника в aQsi Online?')
    result = RetrievalPipeline(Source([creation], {'guide': [creation]})).search(state, 'изменение прав')
    assert not result.documents and not result.sufficient
    assert 'operation_mismatch:change_permissions' in result.rejected[0].reasons


def test_publisher_does_not_override_procedure_scope_and_expansion_cannot_reintroduce_it():
    foreign = hit('Откройте список касс в другом кабинете.', source='atol_online/ofd/activate.md',
                  service='АТОЛ Онлайн', procedure_service='Первый ОФД', task_category='cash_list',
                  operations=['list_cash_registers'])
    local = hit('Откройте «Мониторинг касс».', source='atol_online/fn/monitoring.md',
                service='АТОЛ Онлайн', document_id='local', task_category='cash_list', operations=['list_cash_registers'])
    # Even an inconsistent sibling must pass the procedure scope check.
    source = Source([foreign, local], {'local': [local, foreign]})
    state = _state('Как посмотреть список касс в АТОЛ Онлайн?')
    result = RetrievalPipeline(source).search(state, 'АТОЛ Онлайн список касс')
    assert result.sufficient and all(d.source == local.source for d in result.documents)
    assert 'procedure_service_mismatch:Первый ОФД' in result.rejected[0].reasons
    state = DialogueState(intent='device', operation='connect', entities={
        'service': [Fact.span('АТОЛ Онлайн', 1)], 'ofd': [Fact.span('Первый ОФД', 1)]})
    assert _procedure_matches(state, foreign.metadata)  # Explicit client scope permits an integration article.
    direct = _state('Как посмотреть список касс в Первом ОФД?')
    assert RetrievalPipeline(Source([foreign])).search(direct, 'Первый ОФД список касс').documents


def test_legacy_activation_title_is_not_a_cash_list_due_to_an_incidental_step():
    meta = normalize_metadata(dict(source='atol_online/ofd/activate.md', category='atol_online',
        title='Активация кассы в другом ОФД', text='Проверьте в кабинете ОФД список касс.'))
    assert meta['task_category'] == 'equipment_setup'


def test_error_article_subject_outweighs_transmission_but_generic_guides_stay_rejected():
    error = hit('ФН 235. Проверьте передачу чеков в ОФД.', source='evotor/fn/fn-235.md',
                title='Эвотор: ошибка ФН 235 / -3979', category='fn', manufacturer='Эвотор', service='Эвотор')
    generic = hit('Если ошибка ФН 235 мешает передаче чеков, проверьте связь с ОФД.',
                  document_id='generic', source='evotor/ofd/network.md', title='Проверка связи с ОФД',
                  category='ofd', manufacturer='Эвотор', service='Эвотор')
    other_vendor = hit('Ошибка ФН 235.', document_id='other', source='aqsi/errors/235.md',
                       title='Ошибка ФН 235', category='fn', manufacturer='aQsi', service='aQsi')
    result = RetrievalPipeline(Source([error, generic, other_vendor], {'guide': [error]})).search(
        _state('Эвотор ошибка ФН 235'), 'Эвотор диагностика ошибки ФН 235')
    assert result.sufficient and {d.source for d in result.documents} == {error.source}
    assert len(result.rejected) == 2
    assert any('task_mismatch:receipt_transmission!=error_diagnosis' in x.reasons for x in result.rejected)
    assert any('manufacturer_mismatch_or_unlabeled' in x.reasons for x in result.rejected)


def test_reviewed_coverage_and_procedure_scope_survive_chunking(tmp_path):
    path = tmp_path / 'guide.md'
    path.write_text('---\nprocedure_service: Example OFD\nevidence_coverage:\n  edit_user: partial\n'
                    '---\n# Guide\n\nEdit an existing user.', encoding='utf-8')
    meta = Chunker().split(DocumentLoader(tmp_path).load(path))[0].metadata
    assert meta['procedure_service'] == 'Example OFD'
    assert meta['evidence_coverage'] == {'edit_user': 'partial'}
