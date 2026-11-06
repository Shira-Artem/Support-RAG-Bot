import json
from dataclasses import replace
from pathlib import Path

from app.dialogue_state import DialogueState
from app.retrieval_pipeline import _state_task_category


def test_billing_intent_survives_generic_cloud_product_description():
    trace = Path(__file__).resolve().parents[1] / 'reports/b2_2d_20261105/expanded_live_20261106_N01.json'
    state = DialogueState.from_dict(json.loads(trace.read_text(encoding='utf-8'))['turns'][0]['state_after'])
    assert _state_task_category(state, state.task.value) == 'billing'


def test_settings_without_billing_evidence_stays_settings():
    trace = Path(__file__).resolve().parents[1] / 'reports/b2_2d_20261105/expanded_live_20261106_N01.json'
    state = DialogueState.from_dict(json.loads(trace.read_text(encoding='utf-8'))['turns'][0]['state_after'])
    state.task_context.intent = 'settings'
    state.task_context.task_fact = replace(state.task_context.task_fact, value='Как изменить параметры облачной кассы?')
    state.task_context.goals = []
    assert _state_task_category(state, state.task.value) == 'settings'
