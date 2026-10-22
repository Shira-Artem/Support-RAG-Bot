"""General evidence contract tests across different services and task families."""
import asyncio
import json
import random
from pathlib import Path
from types import SimpleNamespace

from app.answer_service import AnswerService, _validation_issue
from app.dialogue_state import DialogueManager, DialogueState
from app.knowledge import DocumentLoader
from app.rag import SearchResult
from app.response_grounding import claim_supported, evidence_statements
from app.retrieval_pipeline import RetrievalPipeline, RetrievalResult
from test_expert import settings


class Source:
    def __init__(self, hits):
        self.hits = hits

    def search(self, query, top_k=5):
        return self.hits[:top_k]


def state(message):
    return DialogueManager().advance(DialogueState(), message, 1)


def result(text, service, task, operation, **metadata):
    return SearchResult(
        metadata.pop('source', f'{service.casefold().replace(" ", "_")}/guide.md'),
        text, .8, metadata={
            'document_id': metadata.pop('document_id', 'synthetic-guide'),
            'title': 'Проверенная инструкция', 'service': service,
            'manufacturer': service,
            'task_category': task, 'operations': [operation], 'status': 'approved',
            **metadata,
        })


def test_full_receipt_search_evidence_uses_confirmed_fields_across_an_ofd_service():
    hit = result(
        'В разделе «Чеки» откройте поиск чеков. Поиск можно сузить по диапазону суммы и способу оплаты.',
        'Платформа ОФД', 'receipt_search', 'search_receipt',
        source_url='https://vendor.example/ofd/search', source_checked_at='2026-10-20',
        evidence_coverage={'search': 'full', 'search_receipt': 'full'},
        search_fields=['amount', 'payment_type'])
    state_ = state('Как найти чек по сумме и способу оплаты в Платформе ОФД?')
    retrieval = RetrievalPipeline(Source([hit])).search(state_, 'Платформа ОФД поиск чека сумма способ оплаты')
    assert retrieval.evidence_level == 'full', (retrieval.sufficient, retrieval.evidence_status,
                                                retrieval.missing_evidence,
                                                (state_.intent, state_.operation),
                                                (state_.intent, state_.operation),
                                                [(x.metadata.get('evidence_coverage'), x.metadata.get('source_checked_at'),
                                                  x.metadata.get('source_url')) for x in retrieval.documents],
                                                [(x.relevance.score, x.reasons) for x in retrieval.candidates])
    assert retrieval.diagnostics()['evidence_level'] == 'full'
    assert any(step['source'] == hit.source for step in retrieval.supported_steps)


def test_partial_evidence_from_a_new_evotor_card_is_rendered_without_generation(monkeypatch, tmp_path):
    text = 'В истории кассы найдите нужный фискальный документ. Копию документа можно распечатать повторно из карточки операции.'
    hit = result(text, 'Эвотор', 'receipt_print', 'repeat_print', source='evotor/receipt/copy.md',
                 evidence_coverage={'repeat_print': 'partial'})
    state_ = state('Как повторно распечатать фискальный документ на Эвотор?')
    retrieval = RetrievalPipeline(Source([hit])).search(state_, 'Эвотор повторная печать фискального документа')
    assert retrieval.evidence_level == 'partial', [(x.source, x.reasons) for x in retrieval.rejected]

    async def no_generation(*args, **kwargs):
        raise AssertionError('A partial answer must not fill missing steps with model knowledge')
    monkeypatch.setattr('app.answer_service.generate', no_generation)
    rag = SimpleNamespace(search_for_state=lambda *args: retrieval)
    answer = asyncio.run(AnswerService(rag, settings(tmp_path)).answer('Распечатать документ повторно', state=state_))
    assert answer.generation_status == 'partial'
    assert 'Копию документа можно распечатать повторно' in answer.text
    evidence = answer.response_repair['evidence']
    assert evidence and evidence[0]['source'] == hit.source
    assert evidence[0]['document_id'] == 'synthetic-guide'


def test_no_evidence_and_risky_operation_have_distinct_states(monkeypatch, tmp_path):
    empty = RetrievalPipeline(Source([])).search(state('Как сбросить пароль в aQsi Online?'), 'aQsi Online сброс пароля')
    assert empty.evidence_level == 'none'

    risky_hit = result('Архив фискального накопителя доступен в кабинете.', 'АТОЛ', 'equipment_setup', 'configure')
    risky = RetrievalPipeline(Source([risky_hit])).search(
        state('Как закрыть архив ФН в АТОЛ?'), 'Как закрыть архив ФН в АТОЛ?')
    assert risky.evidence_level == 'unsafe', (risky.insufficiency_reason, risky.evidence_status)
    assert not risky.sufficient

    async def no_generation(*args, **kwargs):
        raise AssertionError('No source evidence means no procedural generation')
    monkeypatch.setattr('app.answer_service.generate', no_generation)
    answer = asyncio.run(AnswerService(
        SimpleNamespace(search_for_state=lambda *args: empty), settings(tmp_path)
    ).answer('Как сбросить пароль в aQsi Online?'))
    assert answer.generation_status == 'no_context'
    assert not answer.llm_call_attempted


def test_grounding_accepts_confirmed_paraphrase_and_rejects_invented_interface_or_filter():
    context = ('В разделе «Чеки» откройте поиск. Можно отбирать документы по диапазону суммы '
               'и способу оплаты.\n\nФН не подтверждён как прямой фильтр чеков.')
    paraphrase = 'Чеки можно отфильтровать по сумме и типу оплаты.'
    assert claim_supported(paraphrase, context)
    assert _validation_issue(paraphrase, context, 'поиск чеков') is None
    assert not claim_supported('Откройте раздел «Архив чеков».', context)
    assert not claim_supported('ФН можно использовать как фильтр чеков.', context)
    assert _validation_issue('Откройте раздел «Архив чеков».', context, 'поиск чеков') == 'unsupported_ui_label:Архив чеков'


def test_password_and_access_provenance_keep_contact_and_permission_limits_separate():
    reset = result(
        'Введите телефон либо email, указанный при регистрации, и получите код подтверждения. '
        'Если доступа к этим контактам нет, обратитесь в поддержку.',
        'aQsi Online', 'access', 'reset_password', source='aqsi_online/account/reset-password.md',
        evidence_coverage={'reset_password': 'partial'})
    reset_result = RetrievalPipeline(Source([reset])).search(
        state('Как восстановить пароль в aQsi Online?'), 'aQsi Online восстановление пароля')
    assert reset_result.evidence_level == 'partial', reset_result.diagnostics()
    assert any('обратитесь в поддержку' in step['text'] for step in reset_result.supported_steps)

    access = result('Откройте раздел «Пользователи» и выберите меню существующей записи.',
                    'АТОЛ Онлайн', 'access', 'edit_user', source='atol_online/account/user-edit.md',
                    evidence_coverage={'change_permissions': 'partial'})
    access_result = RetrievalPipeline(Source([access])).search(
        state('Где изменить права сотрудника в АТОЛ Онлайн?'), 'АТОЛ Онлайн изменить права сотрудника')
    assert access_result.evidence_level == 'partial'
    assert 'requested_role_or_permissions_unverified' in access_result.missing_evidence


def test_integration_fn_and_marking_sources_share_the_same_statement_provenance_contract():
    documents = [
        ('1c/integration/aqsi.md', 'Для интеграции aQsi Online с 1С установите совместимый драйвер.', 'integration'),
        ('atol_online/fn/reports.md', 'Отчёты после замены ФН направляются на регистрационную почту.', 'cash_reports'),
        ('marking/gtin.md', 'Для маркированного товара проверьте код маркировки и состояние обмена.', 'marking'),
    ]
    for source, text, category in documents:
        hit = SearchResult(source, text, .8, metadata={'document_id': category, 'section': 'Инструкция'})
        steps = evidence_statements([hit], text)
        assert steps and steps[0]['source'] == source
        assert steps[0]['text'] in text
        assert steps[0]['document_id'] == category


def test_random_unseen_knowledge_cards_only_contribute_text_present_in_context():
    root = Path(__file__).parents[1] / 'data' / 'knowledge'
    docs = DocumentLoader(root).load_all()
    rng = random.Random(20261022)
    sample = rng.sample(docs, min(32, len(docs)))
    examined = 0
    for document in sample:
        body = '\n\n'.join(text for _, text in document.pages)
        hit = SearchResult(document.source, body, .5,
                           metadata={'document_id': document.document_id, 'section': None})
        for statement in evidence_statements([hit], body):
            assert statement['text'] in body
            assert statement['source'] == document.source
            examined += 1
    assert len(docs) == 269
    assert examined >= 20


def test_actual_corpus_services_and_categories_have_traceable_evidence():
    root = Path(__file__).parents[1] / 'data' / 'knowledge'
    paths = [
        'platformaofd/ofd/lkk-receipt-search.md',
        'evotor/cash/evotor-6-receipt-copy.md',
        'aqsi_online/account/reset-password.md',
        'aqsi_online/integration/1c-setup.md',
        'atol_online/account/cash-reports.md',
        'atol_online/integration/integration-1c-versions.md',
        '1c/bank/directbank-all-accounts.md',
        'aqsi_devices/fn/fn-close-safety.md',
        'marking/gtin-vs-item-tracking.md',
    ]
    loader = DocumentLoader(root)
    observed = set()
    for relative in paths:
        document = loader.load(root / relative)
        body = '\n\n'.join(text for _, text in document.pages)
        hit = SearchResult(document.source, body, .5,
                           metadata={'document_id': document.document_id})
        evidence = evidence_statements([hit], body)
        assert evidence, document.document_id
        assert all(item['text'] in body and item['source'] == document.source
                   for item in evidence)
        observed.add(document.document_id)
    assert len(observed) == len(paths)


def test_unconfirmed_instruction_does_not_replace_a_supported_raw_answer():
    context = 'Введите номер телефона либо email, указанный при регистрации, получите код подтверждения и назначьте новый пароль.'
    raw = 'Для входа запросите код на зарегистрированный телефон или email, затем задайте новый пароль.'
    assert claim_supported(raw, context)
    assert _validation_issue(raw, context, 'восстановить пароль') is None


def test_direct_fn_filter_claim_is_not_supported_by_a_negative_source_statement():
    context = ('Поиск чеков доступен по диапазону суммы и способу оплаты. '
               'ФН не подтверждён как прямой фильтр чеков; номер ФН используется для поиска кассы отдельно.')
    assert not claim_supported('ФН можно использовать как фильтр чеков.', context)
    assert _validation_issue('Используйте ФН как фильтр чеков.', context, 'поиск чеков по ФН') == 'unsupported_claim'


def _platformaofd_search_hit():
    root = Path(__file__).parents[1] / 'data' / 'knowledge'
    document = DocumentLoader(root).load(root / 'platformaofd' / 'ofd' / 'lkk-receipt-search.md')
    metadata = {
        'document_id': document.document_id, 'title': document.title,
        'service': document.service, 'task_category': document.task_category,
        'operations': document.operations, 'search_fields': document.search_fields,
        'evidence_coverage': document.evidence_coverage,
        'source_url': document.source_url, 'source_checked_at': document.source_checked_at,
        'status': 'approved',  # In-memory test fixture only; source card remains draft.
        'section': 'Поиск чеков',
    }
    body = '\n\n'.join(text for _, text in document.pages)
    return SearchResult(document.source, body, .9, metadata=metadata)


def test_replay_historical_ofd_paraphrase_from_fixed_raw_answer(monkeypatch, tmp_path):
    # Anonymized c0011/m0112 support case, replayed offline against the local
    # source text with an approved in-memory snapshot and a recorded model reply.
    hit = _platformaofd_search_hit()
    manager = DialogueManager()
    first_turn = manager.advance(DialogueState(),
        'В Платформе ОФД нужно найти чек за прошлый месяц. Куда зайти?', 'prior')
    state_ = manager.advance(first_turn,
        'А можно отфильтровать его по сумме и способу оплаты?', 'follow-up')
    retrieval = RetrievalPipeline(Source([hit])).search(
        state_, 'Платформа ОФД поиск чеков сумма способ оплаты')
    assert retrieval.evidence_level == 'full', (retrieval.sufficient, retrieval.evidence_status,
                                                retrieval.missing_evidence, (state_.intent, state_.operation),
                                                [(x.metadata.get('evidence_coverage'), x.metadata.get('source_checked_at'),
                                                  x.metadata.get('source_url')) for x in retrieval.documents],
                                                [(x.relevance.score, x.reasons) for x in retrieval.candidates])
    raw_response = ('Да, в Платформе ОФД можно отфильтровать чеки по сумме и способу оплаты. '
                    'Перейдите в раздел «Чеки» → «Поиск чеков», задайте период за прошлый месяц, '
                    'а затем в дополнительных условиях выберите диапазон суммы и нужный способ оплаты.')
    context = '\n\n'.join(text for _, text in DocumentLoader(
        Path(__file__).parents[1] / 'data' / 'knowledge'
    ).load(Path(__file__).parents[1] / 'data' / 'knowledge' / 'platformaofd' / 'ofd' / 'lkk-receipt-search.md').pages)
    # The exact historical raw answer is a valid paraphrase: dates represent a
    # calendar month, and the documented fields include amount/payment method.
    assert _validation_issue(raw_response, context, state_.task.value, 'Платформа ОФД') is None, [
        (ascii(sentence), _validation_issue(sentence, context, state_.task.value, 'Платформа ОФД'))
        for sentence in __import__('app.response_grounding', fromlist=['statements']).statements(raw_response)
        if _validation_issue(sentence, context, state_.task.value, 'Платформа ОФД')]
    assert claim_supported('Чеки можно отфильтровать по сумме и способу оплаты.', context)
    historical_navigation = ('В Платформе ОФД откройте меню «Чеки» → «Поиск чеков». '
                             'В открывшемся окне задайте период дат пробития за прошлый месяц и нажмите поиск.')
    assert _validation_issue(historical_navigation, context, state_.task.value,
                             'Платформа ОФД') == 'unsupported_claim'
    fn_state = state('Можно ли в Платформе ОФД найти чек по номеру ФН?')
    fn_retrieval = RetrievalPipeline(Source([hit])).search(
        fn_state, 'Платформа ОФД поиск чека по номеру ФН')
    assert fn_retrieval.documents
    assert fn_retrieval.evidence_level == 'partial'
    assert any(item.startswith('search_parameter_unconfirmed:')
               for item in fn_retrieval.missing_evidence)

    async def no_generation(*args, **kwargs):
        raise AssertionError('Unconfirmed search fields must not be completed from model knowledge')
    monkeypatch.setattr('app.answer_service.generate', no_generation)
    fn_answer = asyncio.run(AnswerService(
        SimpleNamespace(search_for_state=lambda *args: fn_retrieval), settings(tmp_path)
    ).answer('Можно ли найти чек по номеру ФН?', state=fn_state))
    assert fn_answer.generation_status == 'partial'
    requested_field = fn_retrieval.missing_evidence[0].split(':', 1)[1]
    assert requested_field in fn_answer.text
    assert 'не подтверждён' in fn_answer.text
    assert 'не доказывает' in fn_answer.text
    assert _validation_issue('Найдите чек по номеру ФН.', context,
                             'поиск чека по номеру ФН', 'Платформа ОФД') == 'unsupported_claim'


def test_full_answer_keeps_raw_and_final_response_with_source_provenance(monkeypatch, tmp_path):
    context = ('На форме авторизации выберите восстановление пароля. Введите номер телефона либо email, '
               'указанный при регистрации, и получите код подтверждения. Назначьте новый пароль и выполните вход повторно.')
    hit = SearchResult('aqsi_online/account/reset-password.md', context, .9,
                       metadata={'document_id': 'aqsi-reset-test', 'status': 'approved',
                                 'service': 'aQsi Online', 'source_url': 'https://vendor.example/reset'})
    retrieval = RetrievalResult('сброс пароля', [], [], [hit], True, None, context,
                                evidence_status='full', supported_steps=[])
    raw = json.dumps({'scenario': 'answer', 'reason': 'source',
                      'response': 'Введите зарегистрированный телефон или email, получите код, задайте новый пароль и войдите повторно.'},
                     ensure_ascii=False)
    async def recorded(*args, **kwargs):
        from app.llm_client import Generation
        return Generation(raw, 'fixture-model', 12, 10, 22)
    monkeypatch.setattr('app.answer_service.generate', recorded)
    answer = asyncio.run(AnswerService(SimpleNamespace(search_for_state=lambda *args: retrieval),
                                      settings(tmp_path)).answer(
        'Как восстановить пароль в aQsi Online?',
        state=state('Как восстановить пароль в aQsi Online?')))
    assert answer.raw_model_text == raw
    assert answer.text == json.loads(raw)['response']
    assert answer.validation_status == 'passed'
    assert answer.retrieval_diagnostics is None or answer.retrieval_diagnostics['evidence_status'] == 'full'
