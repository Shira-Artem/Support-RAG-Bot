import json
from pathlib import Path

import pytest

from app.answer_service import Answer
from app.conversation_store import ConversationStore
from app.dialogue_state import DialogueManager, DialogueState, Fact
from app.dialogue_understanding import Understanding, _deduplicate_equipment, _equipment_identity, understanding_to_dict, validate_response

TRACE = Path(__file__).resolve().parents[1] / 'reports/architecture_audit_20261101/b2_1_live_20261104.json'


def test_saved_provider_entities_collapse_and_survive_sqlite_reopen(tmp_path):
    trace = json.loads(TRACE.read_text(encoding='utf8'))
    turn = trace['turns'][1]
    raw = trace['understanding_calls'][turn['understanding_call_indices'][0]]['structured_output']
    question = turn['question']
    kind, specialist, unknown, obs = validate_response(raw, question, 1)
    assert [f.value for f in obs.entities['equipment']] == ['Эвотор 7.3']
    store = ConversationStore(tmp_path / 'isolated.sqlite3')
    cid = store.new(42, 42)
    payload = understanding_to_dict(Understanding(kind, specialist, unknown, obs, {}, 'fixture', 0))
    pending = store.begin(cid, question, semantic_mode=True, understanding=payload)
    store.complete(pending, Answer('test'))
    state = ConversationStore(store.path).dialogue_state(cid)
    assert state.task_entity('equipment') == 'Эвотор 7.3'
    assert len(state.task_frame.entities['equipment']) == 1
    assert state.task_frame.entities['equipment'][0].quote == 'Эвотор 7.3'


@pytest.mark.parametrize('a,b', [('Касса АТОЛ 30Ф','АТОЛ 30Ф'), ('терминал aQsi 5','aQsi 5'), ('ККТ Штрих-М 01Ф','Штрих-М 01Ф'), ('касса Эвотор 7.3','evotor 7.3')])
def test_equivalent_known_full_models_deduplicate(a, b):
    facts = [Fact(a, 1, a, 0, len(a)), Fact(b, 1, b, 20, 20 + len(b))]
    entities = {'equipment': facts.copy()}
    _deduplicate_equipment(entities, [])
    assert len(entities['equipment']) == 1


@pytest.mark.parametrize('a,b', [('Эвотор 6','Эвотор 7.3'), ('АТОЛ 30Ф','АТОЛ 30'), ('aQsi 5','aQsi 6'), ('АТОЛ 30Ф','Штрих-М 30Ф')])
def test_distinct_models_not_collapsed(a,b):
    entities = {'equipment': [Fact(a, 1, a, 0, len(a)), Fact(b, 1, b, 20, 20 + len(b))]}
    _deduplicate_equipment(entities, [])
    assert len(entities['equipment']) == 2


def test_ambiguous_or_generic_value_never_coalesces():
    assert _equipment_identity('Касса 30Ф') is None
    assert _equipment_identity('АТОЛ 30Ф версия 2') is None


def test_repeated_model_is_grounded_inside_each_unique_evidence_span():
    from app.dialogue_understanding import validate_response
    text = 'Физическая касса aQsi 5, терминал aQsi 5: сканер не читает DataMatrix.'
    raw = {'request_type': 'diagnosis', 'relation': 'new_task', 'intent': 'device',
           'operation': 'diagnose', 'object': None, 'object_evidence': None,
           'goal': None, 'symptom': None, 'unknown_facts': [],
           'specialist_requested': False, 'specialist_evidence': None, 'confidence': .9,
           'entities': [{'slot': 'equipment', 'value': 'aQsi 5', 'evidence': {'quote': 'Физическая касса aQsi 5'}},
                        {'slot': 'equipment', 'value': 'aQsi 5', 'evidence': {'quote': 'терминал aQsi 5'}}]}
    _, _, _, obs = validate_response(raw, text, 1)
    assert [fact.value for fact in obs.entities['equipment']] == ['aQsi 5']
    fact = obs.entities['equipment'][0]
    assert text[fact.start:fact.end] == fact.quote == 'aQsi 5'
