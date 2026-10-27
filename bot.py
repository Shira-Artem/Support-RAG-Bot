from __future__ import annotations

import asyncio
import logging
import os

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.answer_service import Answer, AnswerService
from app.bot_runtime import write_runtime_receipt
from app.conversation_store import ConversationStore
from app.compat import build_answer_rag
from app.config import get_settings, should_use_ai_coordinator, should_use_source_first
from app.ai_coordinator import coordinate
from app.expert_store import ExpertStore
from app.expert_telegram import ExpertTelegram
from app.source_first_service import SourceFirstService
from app.dialogue_understanding import UnderstandingError, understand_message, understanding_to_dict
from app.handoff import HandoffService, HandoffSettings, TelegramBotApiTransport, specialist_request
from app.groq_rate_limit import allowlist_local_tpm_bypass
from qdrant_client import QdrantClient


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
# HTTP request URLs can contain the Telegram bot token; keep them out of logs.
for logger_name in ("httpx", "httpcore", "httpx2", "httpcore2"):
    logging.getLogger(logger_name).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

settings = get_settings()
if settings.rag_engine == "source_first":
    if os.getenv("RAG_BACKEND", "qdrant").strip().lower() != "qdrant":
        raise RuntimeError("Source-first requires the existing Qdrant backend")
    qdrant_check = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), timeout=15)
    selected_collection = os.getenv("QDRANT_COLLECTION", "knowledge_v1")
    if not qdrant_check.collection_exists(selected_collection):
        raise RuntimeError("Configured Qdrant collection does not exist; refusing to create it")
    if not (qdrant_check.get_collection(selected_collection).points_count or 0):
        raise RuntimeError("Configured Qdrant collection is empty; refusing Source-first startup")
rag = build_answer_rag(settings.docs_dir)
answer_service = AnswerService(rag, settings)
source_first_service = SourceFirstService(rag, settings, settings.docs_dir.parent.parent)
expert_store = ExpertStore()
expert = ExpertTelegram(settings, answer_service, expert_store)
conversations = ConversationStore()
handoff_settings = HandoffSettings.from_env()
handoff_service = HandoffService(handoff_settings,
    TelegramBotApiTransport(handoff_settings.bot_token) if handoff_settings.ready else None,
    progress_provider=conversations.progress_summary)
MENU = ReplyKeyboardMarkup([["Свободный диалог", "Экспертное тестирование"]], resize_keyboard=True)
FREE_MENU = ReplyKeyboardMarkup([["Новый диалог", "В меню"]], resize_keyboard=True)
EXPERT_MENU = ReplyKeyboardMarkup([["В меню"]], resize_keyboard=True)


def identity(update: Update) -> tuple[int, int]:
    return update.effective_user.id, update.effective_chat.id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conversations.clear_pending_feedback_comment(*identity(update))
    conversations.set_mode(*identity(update), "menu")
    await update.effective_message.reply_text("Выберите режим работы:", reply_markup=MENU)


async def expert_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if expert.allowed(update):
        conversations.clear_pending_feedback_comment(*identity(update))
        conversations.set_mode(*identity(update), "expert")
        await update.effective_message.reply_text("Экспертное тестирование", reply_markup=EXPERT_MENU)
    await expert.command(update, context)


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        f"Ваш Telegram ID: {update.effective_user.id}\n"
        "Передайте это число администратору для доступа к экспертному тестированию.")


async def expert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if conversations.state(*identity(update))["mode"] != "expert":
        await update.callback_query.answer("Сначала выберите «Экспертное тестирование».", show_alert=True)
        return
    await expert.callback(update, context)


def answer_buttons(answer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('👍 Помогло', callback_data=f'fb:helpful:{answer_id}'),
         InlineKeyboardButton('👎 Не помогло', callback_data=f'fb:unhelpful:{answer_id}')],
        [InlineKeyboardButton('👨‍💻 Позвать специалиста', callback_data=f'sp:ask:{answer_id}')],
    ])


async def free_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        family, action, raw_id = query.data.split(':', 2)
        answer_id = int(raw_id)
        if answer_id < 1:
            raise ValueError('Invalid answer')
        user_id, chat_id = identity(update)
        if family == 'fb':
            if action == 'comment':
                if conversations.request_feedback_comment(answer_id, user_id, chat_id):
                    await query.answer('Напишите комментарий следующим сообщением.')
                    await query.message.reply_text('Напишите комментарий к этому ответу одним сообщением. '
                                                   'Он сохранится без повторного запроса к модели.')
                else:
                    await query.answer('Сначала нажмите «👎 Не помогло».', show_alert=True)
                return
            changed = conversations.record_feedback(answer_id, user_id, chat_id, action, query.id)
            await query.answer('Спасибо, оценка сохранена.')
            if action == 'unhelpful' and changed:
                await query.message.reply_text(
                    'Что осталось непонятным? Можете продолжить диалог вопросом, '
                    'оставить комментарий к ответу или запросить специалиста.',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton('Оставить комментарий', callback_data=f'fb:comment:{answer_id}')], [
                        InlineKeyboardButton('👨‍💻 Позвать специалиста', callback_data=f'sp:ask:{answer_id}')]]))
            return
        if family != 'sp':
            raise ValueError('Unknown action')
        if action == 'retry':
            bundle = conversations.handoff_bundle(answer_id, user_id, chat_id)
            delivery = await handoff_service.deliver(bundle, retry=True)
            await query.answer()
            await query.message.reply_text(_handoff_user_message(delivery),
                reply_markup=(InlineKeyboardMarkup([[InlineKeyboardButton(
                    'Повторить отправку', callback_data=f'sp:retry:{answer_id}')]])
                    if delivery['status'] == 'failed' and handoff_settings.ready else None))
            return
        status = conversations.support_request(answer_id, user_id, chat_id, action)
        await query.answer()
        if action == 'ask':
            if status == 'pending_confirmation':
                await query.message.reply_text(
                    'Сохранить заявку специалисту по этому вопросу и ответу? '
                    'Уведомление об отправке появится только после подтверждения Telegram.',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton('Подтвердить', callback_data=f'sp:confirm:{answer_id}'),
                        InlineKeyboardButton('Отмена', callback_data=f'sp:cancel:{answer_id}')]]))
            else:
                bundle = conversations.handoff_bundle(answer_id, user_id, chat_id)
                delivery = handoff_service.outbox.get(bundle['ticket_id'])
                if delivery:
                    await query.message.reply_text(_handoff_user_message(
                        {'ticket_id': bundle['ticket_id'], **delivery}),
                        reply_markup=(InlineKeyboardMarkup([[InlineKeyboardButton(
                            'Повторить отправку', callback_data=f'sp:retry:{answer_id}')]])
                            if delivery.get('status') == 'failed' and handoff_settings.ready else None))
                else:
                    await query.message.reply_text(
                        f"Заявка {bundle['ticket_id']} уже сохранена. Подтвердите отправку, чтобы передать её.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                            'Подтвердить отправку', callback_data=f'sp:confirm:{answer_id}')]]))
        elif action == 'confirm':
            if status in {'saved', 'delivered'}:
                bundle = conversations.handoff_bundle(answer_id, user_id, chat_id)
                delivery = await handoff_service.deliver(bundle)
                await query.message.reply_text(_handoff_user_message(delivery),
                    reply_markup=(InlineKeyboardMarkup([[InlineKeyboardButton(
                        'Повторить отправку', callback_data=f'sp:retry:{answer_id}')]])
                        if delivery['status'] == 'failed' and handoff_settings.ready else None))
        else:
            await query.message.reply_text(
                'Заявка уже сохранена. Отмена не меняет подтверждённую заявку.'
                if status in {'saved', 'delivered'} else
                'Передача не подтверждена. Можете продолжить диалог.')
    except (ValueError, TypeError):
        await query.answer('Не удалось связать действие с ответом.', show_alert=True)


def _handoff_user_message(delivery: dict) -> str:
    ticket_id = delivery.get('ticket_id', 'заявка')
    if delivery.get('status') == 'delivered':
        return f"Заявка {ticket_id}: Telegram подтвердил отправку специалистам."
    if delivery.get('status') == 'pending':
        return f"Заявка {ticket_id} готовится к отправке. Уведомление ещё не подтверждено."
    if delivery.get('error') == 'handoff_disabled':
        return f"Заявка {ticket_id} сохранена. Специалист не уведомлён: передача пока отключена."
    if delivery.get('error') == 'specialist_chat_not_configured':
        return f"Заявка {ticket_id} сохранена. Специалист не уведомлён: чат специалистов не настроен."
    if delivery.get('error') == 'specialist_chat_not_approved':
        return f"Заявка {ticket_id} сохранена. Специалист не уведомлён: получатель не совпадает с одобренным чатом."
    return (f"Заявка {ticket_id} сохранена, но Telegram не подтвердил отправку. "
            "Специалист пока не уведомлён.")


async def sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    source_list = rag.list_sources()
    if not source_list:
        await update.message.reply_text("Пока нет файлов в data/docs.")
        return

    text = "Локальная база знаний:\n" + "\n".join(f"• {src}" for src in source_list)
    await update.message.reply_text(text[:4000])


async def reload_docs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rag.reload()
    await update.message.reply_text(f"Поисковый индекс доступен. Фрагментов: {len(rag.chunks)}. Для Qdrant индексацию запускает оператор.")


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conversations.clear_pending_feedback_comment(*identity(update))
    conversations.new(*identity(update))
    await update.effective_message.reply_text("Начат новый диалог. Предыдущая переписка сохранена.", reply_markup=FREE_MENU)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user_id, chat_id = identity(update)
    user_text = update.message.text.strip()

    if not user_text:
        return

    if user_text == "В меню":
        await start(update, context)
        return
    if user_text == "Экспертное тестирование":
        await expert_mode(update, context)
        return
    if user_text == "Новый диалог":
        await clear(update, context)
        return
    state = conversations.state(user_id, chat_id)
    if user_text == "Свободный диалог":
        if not state["conversation_id"]:
            conversations.new(user_id, chat_id)
        else:
            conversations.set_mode(user_id, chat_id, "free")
        await update.message.reply_text("Напишите вопрос. Для чистого контекста нажмите «Новый диалог».", reply_markup=FREE_MENU)
        return
    if state["mode"] == "menu":
        await start(update, context)
        return
    if state["mode"] == "expert":
        if not await expert.comment_message(update):
            await expert.command(update, context)
        return

    if conversations.save_feedback_comment(user_id, chat_id, user_text):
        await update.message.reply_text('Комментарий к ответу сохранён.', reply_markup=FREE_MENU)
        return

    if specialist_request(user_text):
        conversation_id = state['conversation_id']
        recent = conversations.history(conversation_id) if conversation_id else []
        previous_answer = next((item for item in reversed(recent) if item['role'] == 'assistant'), None)
        if previous_answer is None:
            await update.message.reply_text(
                'Чтобы оформить заявку, сначала напишите вопрос в этом диалоге.', reply_markup=FREE_MENU)
            return
        status = conversations.support_request(previous_answer['message_id'], user_id, chat_id, 'ask')
        if status == 'pending_confirmation':
            await update.message.reply_text(
                'Сохранить заявку специалисту по последнему вопросу и ответу?',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton('Подтвердить', callback_data=f"sp:confirm:{previous_answer['message_id']}"),
                    InlineKeyboardButton('Отмена', callback_data=f"sp:cancel:{previous_answer['message_id']}")]]))
        else:
            bundle = conversations.handoff_bundle(previous_answer['message_id'], user_id, chat_id)
            delivery = handoff_service.outbox.get(bundle['ticket_id'])
            if delivery:
                await update.message.reply_text(_handoff_user_message(
                    {'ticket_id': bundle['ticket_id'], **delivery}), reply_markup=FREE_MENU)
            else:
                await update.message.reply_text(
                    f"Заявка {bundle['ticket_id']} уже сохранена. Она ещё не отправлялась.", reply_markup=FREE_MENU)
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    conversation_id = state["conversation_id"] or conversations.new(user_id, chat_id)
    use_source_first = should_use_source_first(settings, user_id)
    use_ai_coordinator = should_use_ai_coordinator(settings, user_id)
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
    quota_deferred = bool(understanding_error and (
        understanding_error.get("http_status") == 429 or
        understanding_error.get("error_code") == "groq_quota_deferred"))
    if use_ai_coordinator and not quota_deferred:
        current_event = next((item for item in reversed(conversations.history(conversation_id))
                              if item.get("role") == "user" and item.get("content") == user_text), {})
        coordinator_decision = coordinate(current_event.get("understanding"), dialogue_state)
    try:
        if quota_deferred:
            answer = Answer(
                "Сейчас достигнут лимит запросов к модели. Переписка сохранена; "
                "повторите вопрос немного позже.", rag_engine="source_first",
                generation_status="error", generation_reason="groq_quota_deferred",
                scenario="clarify", scenario_reason="groq_quota_deferred",
                provider="groq", model=settings.groq_model,
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
                        model=settings.groq_model if settings.llm_provider == "groq" else settings.openrouter_model)
    if answer.generation_status == 'no_context' and conversations.previous_unresolved(
            conversation_id, message_id, dialogue_state):
        answer.text = ('Вижу, что переформулировка не помогла. Подтверждённой инструкции '
                       'для этой задачи пока не нашёл. Напишите новую важную деталь или '
                       'запросите специалиста кнопкой ниже.')
        answer.scenario_reason = 'repeated_unresolved_request'
    conversations.complete(message_id, answer)

    # Telegram limit is 4096 symbols.
    parts = split_for_telegram(answer.text)
    for index, part in enumerate(parts):
        await update.message.reply_text(part,
            reply_markup=answer_buttons(message_id) if index == len(parts) - 1 else None)


def split_for_telegram(text: str, max_len: int = 3900) -> list[str]:
    if len(text) <= max_len:
        return [text]

    parts = []
    current = text
    while len(current) > max_len:
        split_at = current.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = current.rfind(" ", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(current[:split_at].strip())
        current = current[split_at:].strip()
    if current:
        parts.append(current)
    return parts


def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is empty. Fill .env first.")

    # Sequential updates prevent resets/mode changes racing an in-flight answer.
    app = Application.builder().token(settings.telegram_bot_token).concurrent_updates(False).build()
    expert_store.recover_pending()
    conversations.recover_pending()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("sources", sources))
    app.add_handler(CommandHandler("reload", reload_docs))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("expert", expert_mode))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CallbackQueryHandler(expert_callback, pattern=r"^ex:"))
    app.add_handler(CallbackQueryHandler(free_callback, pattern=r"^(fb|sp):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started. Docs: %s, chunks: %s", settings.docs_dir, len(rag.chunks))
    runtime = write_runtime_receipt(settings, rag)
    logger.info("Bot runtime: pid=%s engine=%s collection=%s provider=%s model=%s reasoning=%s source_first_users=%s",
                runtime['pid'], runtime['rag_engine'], runtime['collection'], runtime['provider'], runtime['model'], runtime['reasoning_effort'], runtime['source_first_user_count'])

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    from app.instance_lock import single_instance
    with single_instance():
        main()
