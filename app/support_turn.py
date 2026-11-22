"""Shared full conversation turn; Telegram and authenticated CRM use identical stages."""
from app.answer_service import Answer
from app.config import should_use_ai_coordinator, should_use_source_first
from app.ai_coordinator import coordinate
from app.dialogue_understanding import UnderstandingError, understand_message, understanding_to_dict
from app.groq_rate_limit import allowlist_local_tpm_bypass
from app.secret_safety import with_secret_warning


async def run_turn(runtime, conversation_id, user_text, user_id, *, source_first=None):
    settings = runtime.settings
    conversations = runtime.conversations
    answer_service = runtime.answer_service
    source_first_service = runtime.source_first_service
    logger = runtime.logger
    understand_message = getattr(runtime, "understand_message", globals()["understand_message"])
    use_source_first = should_use_source_first(settings, user_id) if source_first is None else source_first
    use_ai_coordinator = (should_use_ai_coordinator(settings, user_id) if source_first is None
                          else bool(source_first and settings.ai_coordinator_enabled))
    understanding_error = None
    if use_source_first:
        previous_state = conversations.dialogue_state(conversation_id)
        previous_history = conversations.history(conversation_id)
        understanding = None
        understanding_error = None
        try:
            with allowlist_local_tpm_bypass(use_source_first):
                understanding = await understand_message(user_text, "current", previous_history,
                                                         previous_state, settings)
        except UnderstandingError as exc:
            understanding_error = {"type": type(exc).__name__, "message": str(exc),
                "http_status": exc.http_status, "tokens": exc.tokens,
                "duration_ms": exc.duration_ms, "model": exc.model,
                "phase": exc.phase, "error_code": exc.code,
                "retry_after_seconds": exc.retry_after_seconds,
                "rate_limit_headers": exc.rate_limit_headers,
                "structured_response": exc.structured_response,
                "field_diagnostics": exc.field_diagnostics,
                "provider_error": exc.provider_error}
        # Persist the typed result on the user event before state replay. This
        # makes reducer updates idempotent across restarts and prevents a
        # second lexical interpretation of the current Source-first turn.
        message_id = conversations.begin(conversation_id, user_text, semantic_mode=True,
            understanding=understanding_to_dict(understanding) if understanding else None,
            understanding_error=understanding_error)
    else:
        message_id = conversations.begin(conversation_id, user_text)
    dialogue_state = conversations.dialogue_state(conversation_id)
    coordinator_decision = None
    understanding_failed = bool(understanding_error)
    quota_deferred = bool(understanding_error and (
        understanding_error.get("http_status") == 429 or
        understanding_error.get("error_code") == "groq_quota_deferred"))
    if use_ai_coordinator and not understanding_failed:
        current_event = next((item for item in reversed(conversations.history(conversation_id))
                              if item.get("role") == "user" and item.get("content") == user_text), {})
        coordinator_decision = coordinate(current_event.get("understanding"), dialogue_state)
    try:
        if understanding_failed:
            user_message = (
                "Сейчас достигнут лимит запросов к модели, поэтому не удалось разобрать новое сообщение. "
                "Переписка, ранее известные факты и результаты проверок сохранены. "
                "Можно продолжить позже или нажать «Позвать специалиста»: заявка сохранится, "
                "но уведомление сотруднику пока не настроено."
                if quota_deferred else
                "Временно не удалось разобрать сообщение. Оно сохранено; "
                "пожалуйста, повторите вопрос немного позже."
            )
            answer = Answer(
                user_message, rag_engine="source_first",
                generation_status="error",
                generation_reason="groq_quota_deferred" if quota_deferred else "understanding_failed",
                scenario="clarify",
                scenario_reason="groq_quota_deferred" if quota_deferred else "understanding_failed",
                provider=settings.llm_provider,
                model=(settings.hubris_model if settings.llm_provider == "hubris" else
                       settings.groq_model if settings.llm_provider == "groq" else settings.openrouter_model),
                dialogue_state=dialogue_state.to_dict(),
                generation_error={"stage": "understanding",
                    "http_status": understanding_error.get("http_status"),
                    "retry_after_seconds": understanding_error.get("retry_after_seconds"),
                    "rate_limit_headers": understanding_error.get("rate_limit_headers")})
        elif use_source_first:
            with allowlist_local_tpm_bypass(use_source_first):
                answer = await source_first_service.answer(
                    user_text, state=dialogue_state, history=conversations.history(conversation_id),
                    coordinator_decision=coordinator_decision)
        else:
            answer = await answer_service.answer(user_text, state=dialogue_state)
    except Exception as exc:
        logger.error("Free generation failed: %s", type(exc).__name__)
        answer = Answer("Не удалось обработать вопрос. Повторите попытку позже.",
                        rag_engine="source_first" if use_source_first else "legacy",
                        generation_status="error", generation_reason=f"unexpected_exception:{type(exc).__name__}",
                        scenario="escalate", scenario_reason="unexpected_exception",
                        provider=settings.llm_provider,
                        model=(settings.hubris_model if settings.llm_provider == "hubris" else
                               settings.groq_model if settings.llm_provider == "groq" else settings.openrouter_model))
    if answer.generation_status == 'no_context' and conversations.previous_unresolved(
            conversation_id, message_id, dialogue_state):
        answer.text = ('Вижу, что переформулировка не помогла. Подтверждённой инструкции '
                       'для этой задачи пока не нашёл. Напишите новую важную деталь или '
                       'запросите специалиста кнопкой ниже.')
        answer.scenario_reason = 'repeated_unresolved_request'
    answer.text = with_secret_warning(answer.text, user_text)
    return message_id, answer
