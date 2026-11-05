"""General source-scope, category and partial-evidence regression contracts."""
from pathlib import Path
from types import SimpleNamespace
import asyncio
import json

import pytest

from app.dialogue_state import ActiveRoute, DialogueState, Fact
from app.scope_policy import assess_source_scope, generic_physical_model, matches_model_scope
from app.retrieval import Retriever
from app.retrieval_pipeline import RetrievalPipeline, _access_evidence, _state_task_category
from app.task_operation_resolver import resolve_task_operation
from app.rag import SearchResult


def state_for(question, *, intent="device", operation="check", **entities):
    state = DialogueState(intent=intent, operation=operation, task=Fact.span(question, 1))
    state.task_context.entities = {key: [Fact.span(value, 1)] for key, value in entities.items()}
    for slot in ("service", "ofd", "software", "manufacturer"):
        if slot in entities:
            state.task_context.active_route = ActiveRoute(slot, state.task_context.entities[slot][0])
            break
    return state


@pytest.mark.parametrize("brand,model", [("aQsi", "aQsi 5"), ("Эвотор", "Эвотор 10")])
def test_document_product_class_does_not_require_a_numbered_model(brand, model):
    scope = {"service": brand, "manufacturer": brand,
             "model": brand + " (физическая ККТ)", "task_category": "error_diagnosis"}
    result = assess_source_scope(state_for("Проверить питание", manufacturer=brand, equipment=model), scope)
    assert result.missing == result.mismatches == ()
    assert assess_source_scope(state_for("Проверить питание", manufacturer=brand), scope).missing == ()
    assert not matches_model_scope(scope["model"], brand + " Online", brand)


def test_named_models_and_conflicts_remain_binding_for_all_categories():
    for category in ("error_diagnosis", "sales", "peripheral_setup"):
        scope = {"service": "aQsi", "manufacturer": "aQsi", "model": "aQsi 5Ф", "task_category": category}
        assert "model" in assess_source_scope(state_for("Проверить", manufacturer="aQsi", equipment="aQsi 5"), scope).mismatches
        assert "model" in assess_source_scope(state_for("Проверить", manufacturer="aQsi"), scope).missing
    assert not generic_physical_model("aQsi 5 (физическая ККТ)", "aQsi")
    assert not generic_physical_model("aQsi неизвестная серия", "aQsi")
    assert not matches_model_scope("Эвотор 7.3", "Эвотор 6", "Эвотор")
    assert not matches_model_scope("Эвотор 7.3", "Эвотор", "Эвотор")


def test_cloud_monitoring_uses_the_confirmed_cabinet_not_generic_equipment():
    state = state_for("Мониторинг накопителя в кабинете", intent="fiscal_drive",
                      service="АТОЛ Онлайн", equipment="наши кассы")
    scope = {"service": "АТОЛ Онлайн", "manufacturer": "АТОЛ",
             "model": "АТОЛ Онлайн — облачная ККТ", "task_category": "cash_list"}
    assert assess_source_scope(state, scope).missing == ()
    assert assess_source_scope(state, scope).mismatches == ()
    assert assess_source_scope(state_for("Проверить", manufacturer="АТОЛ"), scope).missing


def test_unresolved_fallback_uses_cloud_scope_even_with_generic_device_fact():
    from app.retrieval_pipeline import _unresolved_task_fallback
    q="В АТОЛ Онлайн хочу посмотреть сведения о накопителе наших касс"
    state=state_for(q,service="АТОЛ Онлайн",equipment="наши кассы")
    meta={"status":"approved","service":"АТОЛ Онлайн","manufacturer":"АТОЛ",
          "model":"АТОЛ Онлайн — облачная ККТ","task_category":"cash_list",
          "title":"Сведения о накопителе касс","operations":["inspect_fiscal_drive"]}
    hit=SearchResult("cloud.md","Откройте сведения о накопителе кассы в мониторинге.",.9,.8,5.,meta)
    inputs=dict(service_match=True,manufacturer_match=True,model_match=False,
                software_match=True,operation_status="unknown")
    assert _unresolved_task_fallback(state,q,hit,meta,**inputs)
    state.task_context.entities["service"]=[Fact.span("aQsi Online",1)]
    assert not _unresolved_task_fallback(state,q,hit,meta,**inputs)


def test_raw_retrieval_keeps_wide_source_but_blocks_draft_other_code_and_model():
    def point(key, model, code="246", status="approved"):
        return SimpleNamespace(id=key, score=.9, payload={"source":key+".md", "document_id":key,
            "status":status, "manufacturer":"Эвотор", "model":model,
            "title":"Эвотор: ошибка ФН " + code, "text":"Проверьте питание. ФН " + code})
    points=[point("wide",None),point("wrong-model","Эвотор 6"),point("known","Эвотор 7.3","999"),
            point("draft",None,status="draft"),point("wrong-code",None,"247")]
    store=SimpleNamespace(all_points=lambda:points, semantic=lambda *args:points)
    hits=Retriever(store).search("Эвотор 7.3 ошибка ФН 246",30)
    assert {hit.metadata["document_id"] for hit in hits} == {"wide"}


def test_explicit_reviewed_operation_can_bridge_category_but_conflict_cannot():
    query="В АТОЛ Онлайн хочу оценить работу ФН."
    state=state_for(query,intent="fiscal_drive",service="АТОЛ Онлайн")
    def hit(key,operations):
        return SearchResult(key,"Откройте мониторинг и проверьте состояние ФН.",.9,.85,5.,
            {"source":key,"document_id":key,"status":"approved","service":"АТОЛ Онлайн",
             "manufacturer":"АТОЛ","model":"АТОЛ Онлайн — облачная ККТ",
             "task_category":"cash_list","operations":operations,"title":"Мониторинг ФН"})
    result=RetrievalPipeline(SimpleNamespace(search=lambda *args,**kwargs:[hit("monitor",["inspect_fiscal_drive"]),hit("replace",["replace_fiscal_drive"])] )).search(state,query)
    assert any(item.document_id=="monitor" and item.selected for item in result.candidates)
    assert not any(item.document_id=="replace" and item.selected for item in result.candidates)
    assert any("reviewed_operation_bridges_category" in item.relevance.reasons for item in result.candidates if item.document_id=="monitor")


@pytest.mark.parametrize("code",["501","509"])
def test_control_code_namespace_precedes_incidental_receipt_delivery_context(code):
    q=f"ОФД показывает ФЛК {code} у чека. Что проверить?"
    r=resolve_task_operation(q,operation="diagnose",intent="receipt")
    assert r.task_category=="fiscal_document_control" and r.operation=="diagnose"
    assert resolve_task_operation("Чеки не передаются в ОФД",operation="diagnose",intent="receipt").task_category=="receipt_transmission"


def test_accounting_and_edo_domains_precede_generic_refund_and_integration():
    r=resolve_task_operation("В 1С банк списал возврат покупателю по эквайрингу. Что за операция?",operation="explain",intent="general")
    assert (r.task_category,r.operation)==("bank_statement","explain")
    assert resolve_task_operation("Нужно вернуть покупателю деньги за товар",operation="return",intent="receipt").task_category=="refund"
    assert resolve_task_operation("Подключить 1С-ЭДО для документов",operation="connect").task_category=="edo"


def test_receipt_subject_alone_does_not_imply_a_transmission_failure():
    state=state_for("Как настроить ежедневный отчёт по чекам на почту?",intent="receipt",operation="check")
    assert _state_task_category(state,state.task.value) != "receipt_transmission"


def test_simple_creation_goal_is_not_a_request_for_unverified_permissions():
    q="Создать сотруднику новую запись"
    state=state_for(q,intent="access",operation="add_employee",service="aQsi Online")
    state.task_context.goals=[Fact.span(q,1)]
    text="Откройте пользователей и создайте новую запись."
    doc=SearchResult("users.md",text,.9,metadata={"status":"approved","task_category":"access",
        "operations":["add_employee"],"evidence_coverage":{"add_employee":"full"},
        "source_url":"https://example.test/users","source_checked_at":"2026-11-04","section":"Создание"})
    level,missing,steps=_access_evidence(state,[doc],text)
    assert level=="full" and not missing and steps
    state.operation="change_permissions"
    assert "requested_role_or_permissions_unverified" in _access_evidence(state,[doc],text)[1]


def test_partial_password_workflow_can_return_verified_part_without_claiming_fullness(tmp_path, monkeypatch):
    from app.config import Settings
    from app.llm_client import Generation
    from app.retrieval_pipeline import RetrievalResult, EvaluatedDocument, Relevance
    from app.source_first_service import SourceFirstService, _sections
    root=Path(__file__).resolve().parents[1]
    source="aqsi_online/account/reset-password.md"
    body=(root/"data/knowledge"/source).read_text(encoding="utf-8").split("---",2)[2].strip()
    heading="Что можно объяснить и проверить"
    text=dict(_sections(body))[heading]
    meta={"source":source,"document_id":"aqsi-online-account-reset-password","status":"approved",
          "section":heading,"service":"aQsi Online","manufacturer":"aQsi",
          "model":"aQsi Online (облачная касса)","task_category":"access",
          "operations":["reset_password"]}
    hit=SearchResult(source,text,.9,.8,5.,meta)
    evaluated=EvaluatedDocument(source,meta["document_id"],"approved",meta,{},Relevance("match","match",.9),selected=True)
    result=RetrievalResult("password",[evaluated],[],[hit],False,"access_evidence_incomplete",text,
        "partial",["access_workflow_unverified"],[{"source":source,"text":text}])
    rag=SimpleNamespace(search_for_state=lambda *_args:result)
    question="Как восстановить забытый пароль в aQsi Online?"
    state=state_for(question,intent="credentials",operation="reset_password",service="aQsi Online")
    state.task_id="password-test"
    async def planner(messages,settings,**kwargs):
        payload=json.loads(messages[-1]["content"])
        assert payload["evidence_coverage"]["bounded_access_part_only"] is True
        selected=next(item for item in payload["candidate_sections"] if item["section"]==heading)
        return Generation(json.dumps({"mode":"select","section_id":selected["id"],
            "applicability_confirmed":True,"source_order_complete":True,"reason":"verified part only"}),"fixture")
    monkeypatch.setattr("app.source_first_service.generate",planner)
    settings=Settings(telegram_bot_token="",openrouter_api_key="",openrouter_model="model",
        app_name="test",app_url="http://localhost",show_sources=True,docs_dir=tmp_path,
        llm_provider="groq",groq_api_key="test",groq_model="openai/gpt-oss-20b",rag_engine="source_first")
    answer=asyncio.run(SourceFirstService(rag,settings,root).answer(question,state=state,
        coordinator_decision={"route":"technical_action"}))
    assert answer.scenario=="answer"
    assert "номер телефона либо email" in answer.text
    assert "Полнота операции по базе не подтверждена" in answer.text


def test_howto_keeps_the_complete_verified_sequence_and_duplicate_receipt_warning(tmp_path, monkeypatch):
    from app.config import Settings
    from app.llm_client import Generation
    from app.retrieval_pipeline import RetrievalResult, EvaluatedDocument, Relevance
    from app.source_first_service import SourceFirstService, _sections
    from app.knowledge import DocumentLoader
    from dataclasses import asdict
    root=Path(__file__).resolve().parents[1]
    source="aqsi_devices/errors/paper-print-retry.md"
    path=root/"data/knowledge"/source
    heading="Проверенная информация и первичная диагностика"
    text=dict(_sections(path.read_text(encoding="utf-8").split("---",2)[2].strip()))[heading]
    meta={**asdict(DocumentLoader(root/"data/knowledge").load(path)),"section":heading}
    hit=SearchResult(source,text,.9,.8,5.,meta)
    evaluated=EvaluatedDocument(source,meta["document_id"],"approved",meta,{},Relevance("match","match",.9),selected=True)
    result=RetrievalResult("print",[evaluated],[],[hit],True,None,text,"partial",
        ["procedure_completeness_unverified"],[{"source":source,"text":text}])
    state=state_for("Как допечатать документ после замены бумаги?",operation="unknown",manufacturer="aQsi",equipment="aQsi 5")
    state.task_id="print-test"
    async def planner(messages,settings,**kwargs):
        sections=json.loads(messages[-1]["content"])["candidate_sections"]
        selected=next(item for item in sections if item["section"]==heading)
        return Generation(json.dumps({"mode":"select","section_id":selected["id"],
            "applicability_confirmed":True,"source_order_complete":True,"reason":"whole ordered section"}),"fixture")
    monkeypatch.setattr("app.source_first_service.generate",planner)
    settings=Settings(telegram_bot_token="",openrouter_api_key="",openrouter_model="model",
        app_name="test",app_url="http://localhost",show_sources=True,docs_dir=tmp_path,
        llm_provider="groq",groq_api_key="test",groq_model="openai/gpt-oss-20b",rag_engine="source_first")
    answer=asyncio.run(SourceFirstService(SimpleNamespace(search_for_state=lambda *_:result),settings,root).answer(
        state.task.value,state=state,coordinator_decision={"route":"technical_action"}))
    assert answer.scenario=="answer"
    assert "«Оформить»" in answer.text
    assert "не создавайте повторный фискальный чек" in answer.text
    assert answer.text.index("Загрузите чековую ленту") < answer.text.index("«Оформить»")
