from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.error import NetworkError
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
from app.secret_safety import redact_client_secrets, with_secret_warning
from app.telegram_transport import ConnectionRetryHTTPXRequest
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
expert_db_path = os.getenv("EXPERT_DB_PATH")
expert_store = ExpertStore(Path(expert_db_path)) if expert_db_path else ExpertStore()
expert = ExpertTelegram(settings, answer_service, expert_store)
conversation_db_path = os.getenv("CONVERSATION_DB_PATH")
conversations = ConversationStore(Path(conversation_db_path)) if conversation_db_path else ConversationStore()
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
    user_text = redact_client_secrets(update.message.text.strip())

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

    try:
        await update.message.chat.send_action(ChatAction.TYPING, connect_timeout=1,
            read_timeout=1, write_timeout=1, pool_timeout=1)
    except NetworkError as exc:
        # Typing is cosmetic: its failure must not discard the user's question.
        logger.warning("Telegram typing unavailable: %s", type(exc).__name__)

    conversation_id = state["conversation_id"] or conversations.new(user_id, chat_id)
    from app.support_turn import run_turn
    import sys
    message_id, answer = await run_turn(sys.modules[__name__], conversation_id, user_text, user_id)
    # Telegram limit is 4096 symbols.
    parts = split_for_telegram(answer.text)
    try:
        for index, part in enumerate(parts):
            await update.message.reply_text(part,
                reply_markup=answer_buttons(message_id) if index == len(parts) - 1 else None)
    except Exception:
        # A generated answer is not a shown check until Telegram accepts it.
        # Preserve the user turn and let the next message proceed normally.
        conversations.fail_delivery(message_id, answer)
        raise
    conversations.complete(message_id, answer)


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
    app = (Application.builder().token(settings.telegram_bot_token)
           .request(ConnectionRetryHTTPXRequest())
           .get_updates_request(ConnectionRetryHTTPXRequest())
           .concurrent_updates(False).build())
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
    runtime = write_runtime_receipt(
        settings, rag, Path(os.getenv("BOT_RUNTIME_RECEIPT_PATH", ".local/bot-runtime.json")))
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
