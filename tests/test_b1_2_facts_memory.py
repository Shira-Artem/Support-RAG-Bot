"""B1.2 independent exact-evidence and persistence controls."""
from app.dialogue_state import DialogueManager, DialogueState, Fact, Observation
from app.dialogue_understanding import validate_response


def turn(manager, state, text, mid, *, relation="continue", symptom=None,
         entities=None, unknown=None, request_type="diagnosis"):
    obs = Observation(evidence=Fact.span(text, mid), relation=relation,
        intent="receipt", operation="diagnose", request_type=request_type,
        symptom=(Fact.span(text, mid, text.index(symptom), text.index(symptom) + len(symptom))
                 if symptom else None), entities=entities or {}, unknown_facts=unknown or {})
    return manager.advance(state, text, mid, observation=obs,
                           unknown_facts=list((unknown or {}).keys()))


def test_missing_provider_symptom_preserves_exact_diagnostic_turn_as_detail():
    manager = DialogueManager()
    text = "Пробитые документы не появились у оператора"
    state = turn(manager, DialogueState(), text, 1, relation="new_task")
    assert state.symptom is None
    assert any(f.quote == text and f.message_id == 1 for f in state.details)


def test_frame_contains_parameters_and_correction_history():
    manager = DialogueManager()
    first = "У Эвотор 7.3 чеки зависли"
    old = Fact.span(first, 1, first.index("Эвотор"), first.index("Эвотор") + len("Эвотор 7.3"))
    state = turn(manager, DialogueState(), first, 1, relation="new_task",
                 symptom="чеки зависли", entities={"equipment": [old]})
    update = "Адрес и порт сверены с оператором"
    state = turn(manager, state, update, 2, relation="parameter_update")
    correction = "Я перепутал модель: Эвотор 6"
    new = Fact.span(correction, 3, correction.index("Эвотор"))
    state = turn(manager, state, correction, 3, relation="contradiction",
                 entities={"equipment": [new]})
    assert state.task_frame.parameters[0].quote == update
    assert state.task_frame.superseded_facts[0] == old
    assert [f.value for f in state.task_frame.entities["equipment"]] == ["Эвотор 6"]
    assert DialogueState.from_dict(state.to_dict()).task_frame == state.task_frame


def test_repeated_conversational_turn_does_not_expand_detail_memory():
    manager = DialogueManager()
    first = "Чеки не попадают оператору"
    state = turn(manager, DialogueState(), first, 1, relation="new_task", symptom=first)
    for mid in range(2, 8):
        state = turn(manager, state, "Что дальше?", mid, request_type="information")
    assert not state.details


def test_unknown_keeps_exact_quote_until_confirmed_and_new_task_clears_it():
    manager = DialogueManager()
    opening = "Не знаю модель терминала"
    unknown = Fact.span(opening, 1, 0, len("Не знаю модель"))
    state = turn(manager, DialogueState(), opening, 1, relation="new_task",
                 unknown={"equipment": unknown})
    assert "equipment" in state.task_frame.unknown_facts
    assert state.task_frame.unknown_evidence["equipment"] == unknown
    assert not state.task_frame.entities.get("equipment")
    assert DialogueState.from_dict(state.to_dict()).task_frame.unknown_evidence == {"equipment": unknown}
    update = "Нашёл на корпусе: Эвотор 6"
    model = Fact.span(update, 2, update.index("Эвотор"))
    state = turn(manager, state, update, 2, entities={"equipment": [model]})
    assert "equipment" not in state.task_frame.unknown_facts
    assert "equipment" not in state.task_frame.unknown_evidence
    other = "В Saby пропал входящий документ"
    state = turn(manager, state, other, 3, relation="new_task", symptom="пропал входящий документ")
    assert not state.task_frame.unknown_evidence
    assert not state.task_frame.entities.get("equipment")


def test_provider_domain_drift_on_related_symptom_keeps_original_task():
    manager = DialogueManager()
    opening = "Эвотор не отправляет чеки оператору"
    state = turn(manager, DialogueState(), opening, 1, relation="new_task",
                 symptom="не отправляет чеки оператору")
    followup = "Очередь фискальных документов не сокращается"
    obs = Observation(evidence=Fact.span(followup, 2), relation="continue",
        intent="fiscal_drive", operation="diagnose", request_type="information",
        symptom=Fact.span(followup, 2, 0, len(followup)))
    after = manager.advance(state, followup, 2, observation=obs)
    assert after.task_id == state.task_id
    assert after.intent == "receipt"
    assert after.symptom == state.symptom
    assert any(f.quote == followup for f in after.details)


def test_unknown_number_claim_normalizes_to_unconfirmed_parameter():
    text = "Номер отправления пока не знаю"
    raw = {"request_type": "information", "relation": "continue", "intent": "delivery_document",
        "operation": "check", "object": None, "object_evidence": None, "goal": None,
        "symptom": None, "entities": [], "unknown_facts": [{"slot": "tracking_number",
            "evidence": {"quote": text}}], "specialist_requested": False,
        "specialist_evidence": None, "confidence": 0.9}
    _, _, unknown, obs = validate_response(raw, text, 2)
    assert unknown == ("parameter",)
    assert obs.unknown_facts["parameter"].quote == text
    assert not obs.parameters


def test_domain_drift_replay_survives_sqlite_reopen(tmp_path):
    from app.answer_service import Answer
    from app.conversation_store import ConversationStore
    from app.dialogue_understanding import Understanding, understanding_to_dict

    store = ConversationStore(tmp_path / "facts.sqlite3")
    cid = store.new(42, 42)
    rows = [
        ("Эвотор не отправляет чеки оператору", "new_task", "receipt", "не отправляет чеки оператору"),
        ("Очередь фискальных документов не сокращается", "continue", "fiscal_drive",
         "Очередь фискальных документов не сокращается"),
    ]
    for text, relation, intent, symptom in rows:
        obs = Observation(evidence=Fact.span(text, "current"), relation=relation,
            intent=intent, operation="diagnose", request_type="diagnosis",
            symptom=Fact.span(text, "current", text.index(symptom), text.index(symptom) + len(symptom)))
        payload = understanding_to_dict(Understanding("diagnosis", False, (), obs, {}, "test", 0))
        pending = store.begin(cid, text, semantic_mode=True, understanding=payload)
        store.complete(pending, Answer("test"))
        assert store.dialogue_state(cid).to_dict() == ConversationStore(store.path).dialogue_state(cid).to_dict()
    state = ConversationStore(store.path).dialogue_state(cid)
    assert state.task_id == "task:1"
    assert state.symptom.quote == rows[0][3]
    assert any(f.quote == rows[1][3] for f in state.details)


def test_explicit_manufacturer_and_model_correction_retires_old_scope():
    manager = DialogueManager()
    first = "На Эвотор 7.3 не уходят чеки"
    brand = Fact.span(first, 1, first.index("Эвотор"), first.index("Эвотор") + len("Эвотор"))
    model = Fact.span(first, 1, first.index("Эвотор"), first.index("Эвотор") + len("Эвотор 7.3"))
    state = turn(manager, DialogueState(), first, 1, relation="new_task",
                 symptom="не уходят чеки", entities={"manufacturer": [brand], "equipment": [model]})
    corrected = "Я перепутал производителя и модель: это АТОЛ 30Ф"
    new_brand = Fact.span(corrected, 2, corrected.index("АТОЛ"), corrected.index("АТОЛ") + len("АТОЛ"))
    new_model = Fact.span(corrected, 2, corrected.index("АТОЛ"))
    after = turn(manager, state, corrected, 2, relation="contradiction",
                 entities={"manufacturer": [new_brand], "equipment": [new_model]})
    assert after.task_id == state.task_id
    assert [f.value for f in after.task_frame.entities["manufacturer"]] == ["АТОЛ"]
    assert [f.value for f in after.task_frame.entities["equipment"]] == ["АТОЛ 30Ф"]
    assert {f.value for f in after.task_frame.superseded_facts} >= {"Эвотор", "Эвотор 7.3"}
    assert DialogueState.from_dict(after.to_dict()).task_frame == after.task_frame
