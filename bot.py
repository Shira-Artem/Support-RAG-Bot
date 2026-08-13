from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.answer_service import AnswerService
from app.config import get_settings
from app.rag import SimpleRAG


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

settings = get_settings()
rag = SimpleRAG(settings.docs_dir)
answer_service = AnswerService(rag, settings)

# Простая память диалога в RAM. Для курсовой достаточно.
# Для продакшена лучше Redis/БД.
USER_HISTORY: dict[int, list[dict]] = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет! Я бот поддержки по кассам, ОФД, ФН, маркировке и бухгалтерии.\n\n"
        "Можешь спросить, например:\n"
        "• не уходят чеки в ОФД\n"
        "• ошибка ФН 234\n"
        "• как заменить фискальный накопитель\n"
        "• что такое маркировка\n"
        "• нужна бухгалтерия для ИП\n\n"
        "Команды: /sources, /reload, /clear"
    )
    await update.message.reply_text(text)


async def sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    source_list = rag.list_sources()
    if not source_list:
        await update.message.reply_text("Пока нет файлов в data/docs.")
        return

    text = "Локальная база знаний:\n" + "\n".join(f"• {src}" for src in source_list)
    await update.message.reply_text(text[:4000])


async def reload_docs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rag.reload()
    await update.message.reply_text(f"База знаний обновлена. Фрагментов: {len(rag.chunks)}")


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user:
        USER_HISTORY.pop(update.effective_user.id, None)
    await update.message.reply_text("История диалога очищена.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id if update.effective_user else 0
    user_text = update.message.text.strip()

    if not user_text:
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    history = USER_HISTORY.get(user_id, [])
    answer = await answer_service.answer(user_text, history=history)

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": answer.text[:1200]})
    USER_HISTORY[user_id] = history[-8:]

    # Telegram limit is 4096 symbols.
    for part in split_for_telegram(answer.text):
        await update.message.reply_text(part)


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

    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sources", sources))
    app.add_handler(CommandHandler("reload", reload_docs))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started. Docs: %s, chunks: %s", settings.docs_dir, len(rag.chunks))

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
