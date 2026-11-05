"""Offline probe: what happens if only provider entity claims are trusted?"""
import copy
import json
from pathlib import Path
from unittest.mock import patch

from app.dialogue_understanding import validate_response

ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / 'reports/architecture_audit_20261101/b2_2b2_live_20261104.json'


def main():
    data = json.loads(TRACE.read_text(encoding='utf-8'))
    turn = next(t for t in data['turns'] if t['case'] == 'b222_wrong_model')
    original = data['understanding_calls'][turn['understanding_call_indices'][0]]['structured_output']
    scenarios = [
        ('reference_first', 'Инструкция АТОЛ 30Ф подойдёт для моей кассы АТОЛ 55Ф?', ['АТОЛ 30Ф', 'АТОЛ 55Ф']),
        ('two_owned', 'У меня две кассы АТОЛ 30Ф и АТОЛ 55Ф, обе не печатают.', ['АТОЛ 30Ф', 'АТОЛ 55Ф']),
        ('uncertain', 'В инструкции встречается АТОЛ 30Ф, модель моей кассы неизвестна.', ['АТОЛ 30Ф']),
        ('negated', 'У меня не АТОЛ 30Ф, а АТОЛ 55Ф.', ['АТОЛ 30Ф', 'АТОЛ 55Ф']),
    ]
    results = []
    for name, text, mentions in scenarios:
        raw = copy.deepcopy(original)
        raw.update(object=None, object_evidence=None, goal=None, symptom=None,
                   entities=[{'slot': 'equipment', 'value': x, 'evidence': {'quote': x}} for x in mentions])
        with patch('app.dialogue_understanding._extract_known_entities', lambda *a, **k: None):
            obs = validate_response(raw, text, 1)[3]
        results.append({'case': name, 'message': text, 'raw_claims': raw['entities'],
                        'equipment': [f.value for f in obs.entities.get('equipment', [])]})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
