from app.dialogue_state import DialogueState, Fact, TaskContext
from app.rag import SearchResult
from app.retrieval_pipeline import _document_exchange_scope_conflict, _exact_incident_section_bridge, _scoped_evidence_documents


def incident_state(symptom='Error code AX-94', subject='УПД', operation='diagnose'):
    message = f'{subject}: {symptom}'
    return DialogueState(task_context=TaskContext(task_id='task:1', intent='delivery_document', operation=operation,
        object=subject, task_fact=Fact.span(message, 1), symptom=Fact.span(message, 1, start=len(subject)+2, end=len(message))))


def test_cross_category_admission_requires_both_exact_incident_and_object():
    meta = {'status':'approved', 'task_category':'marking', 'operations':['check_marking_code'],
            'title':'Приёмка УПД', 'document_id':'a', 'section':'Частые проблемы'}
    hit = SearchResult('a.md', 'Error code AX-94 означает неподдерживаемую версию.', .8, metadata=meta)
    state = incident_state()
    assert _exact_incident_section_bridge(state, hit, meta)
    assert _scoped_evidence_documents([hit], 'edo', state)
    assert not _exact_incident_section_bridge(incident_state('Error code AX-95'), hit, meta)
    assert not _exact_incident_section_bridge(incident_state(subject='акт'), hit, meta)
    assert not _exact_incident_section_bridge(incident_state(operation='change'), hit, meta)
    assert not _exact_incident_section_bridge(state, hit, {**meta, 'status':'draft'})


def test_transport_source_does_not_authorize_ordinary_document_exchange():
    source = {'task_category':'edo', 'title':'Обмен транспортными ЭПД'}
    assert _document_exchange_scope_conflict('Как обменять УПД в ЭДО?', source)
    assert not _document_exchange_scope_conflict('Как обменять транспортный ЭПД?', source)
    assert not _document_exchange_scope_conflict('Чем ЭДО отличается от ЭПД?', source)
    assert not _document_exchange_scope_conflict('Как обменять УПД в ЭДО?', {**source,'title':'Обмен УПД в ЭДО'})

def test_information_selection_prefers_relevant_explicit_limit_over_adjacent_fact():
    from app.source_first_service import _focused_approved_sentence
    question = 'Для стороннего устройства возможна гарантия работы как у оригинала?'
    sections = [{'section':'Сведения', 'text': 'Для оригинального устройства предусмотрен режим работы. Для стороннего устройства гарантированной совместимости нет.'}]
    chosen = _focused_approved_sentence(sections, 'Возможна гарантия работы как у оригинала?', conceptual_question=question)
    assert chosen is not None
    assert 'стороннего устройства гарантированной совместимости нет' in chosen[1]


def test_saved_u02_information_selection_keeps_client_scope_and_direct_limit():
    import json
    from pathlib import Path
    from app.source_first_service import _focused_approved_sentence, _sections
    root=Path(__file__).resolve().parents[1]
    trace=json.loads((root/'reports/b2_2d_20261105/bounded_live_20261105.json').read_text(encoding='utf8'))
    turn=next(t for t in trace['turns'] if t['case']=='u02')
    body=(root/'data/knowledge/aqsi_devices/peripherals/scanner-hub-power.md').read_text(encoding='utf8').split('---',2)[2]
    text=dict(_sections(body))['Проверенная информация и первичная диагностика']
    picked=_focused_approved_sentence([{'section':'Проверенная информация и первичная диагностика','text':text}],
        turn['task_frame']['goals'][0]['value'],conceptual_question=turn['question'])
    assert picked and 'гарантированной совместимости нет' in picked[1]
