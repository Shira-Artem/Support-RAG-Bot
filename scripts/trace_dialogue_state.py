"""Offline state trace: python -m scripts.trace_dialogue_state [--full].

No SQLite connection, retrieval, embeddings, provider settings or model calls.
Use --input with a JSON array of client messages to trace another conversation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.dialogue_state import DialogueManager, DialogueState
from app.rag_query import QueryNeedsClarification, build_rag_query


EXAMPLE = [
    'Как добавить сотрудника в aQsi Online?',
    'А какую роль ему назначить?',
    'Мне нужно, чтобы он мог смотреть кассы и отчёты, но не менять настройки.',
    'А где изменить права уже созданному сотруднику?',
    'А если я использую АТОЛ Онлайн, там это делается так же?',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='JSON array of client messages')
    parser.add_argument('--full', action='store_true', help='Include all fact provenance and state fields')
    args = parser.parse_args()
    messages = json.loads(args.input.read_text(encoding='utf-8')) if args.input else EXAMPLE
    if not isinstance(messages, list) or not all(isinstance(m, str) and m.strip() for m in messages):
        parser.error('input must be an array of nonempty strings')
    manager, state = DialogueManager(), DialogueState()
    for i, message in enumerate(messages, 1):
        state = manager.advance(state, message, i)
        try:
            query = build_rag_query(state)
        except QueryNeedsClarification:
            query = None
        summary = state.to_dict() if args.full else {
            'task_id': state.task_id, 'revision': state.revision, 'intent': state.intent,
            'operation': state.operation, 'object': state.object, 'transition': state.transition,
            'entities': {k: [f.value for f in values] for k, values in state.entities.items()},
            'goals': [f.value for f in state.goals], 'constraints': [f.value for f in state.constraints],
            'analysis_required': state.analysis_required,
        }
        print(json.dumps({'message': i, 'user': message, 'state': summary, 'rag_query': query}, ensure_ascii=False))


if __name__ == '__main__':
    main()
