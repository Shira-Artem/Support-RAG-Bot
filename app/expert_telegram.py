"""Compact Telegram workflow for authorized expert reviewers."""
from __future__ import annotations

import json
import logging
from time import perf_counter

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup, Update
from telegram.ext import ContextTypes

from app.answer_service import AnswerService
from app.config import Settings
from app.expert_store import ExpertStore, load_questions

logger = logging.getLogger(__name__)


def keyboard(rows: list[list[tuple[str, str]]]) -> Markup:
    return Markup([[Button(label, callback_data=data) for label, data in row] for row in rows])


async def send(update: Update, text: str, rows=None) -> None:
    parts = [text[i:i + 3500] for i in range(0, len(text), 3500)] or [""]
    for part in parts[:-1]:
        await update.effective_message.reply_text(part)
    await update.effective_message.reply_text(parts[-1], reply_markup=keyboard(rows) if rows else None)


class ExpertTelegram:
    def __init__(self, settings: Settings, service: AnswerService, store: ExpertStore):
        self.settings, self.service, self.store = settings, service, store

    def allowed(self, update: Update) -> bool:
        return bool(update.effective_user and update.effective_user.id in self.settings.expert_telegram_ids)

    async def command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            await send(update, "Тестирование доступно только приглашённым экспертам.")
            return
        active = self.store.active(update.effective_user.id)
        if active:
            item = self.store.current(active["id"], update.effective_user.id)
            progress = f"{item['ordinal'] + 1}/30" if item else "продолжить"
            await send(update, f"Есть незавершённое тестирование ({progress}).", [
                [("Продолжить тестирование", "ex:continue")],
                [("Начать новую сессию", "ex:new")],
            ])
        else:
            await send(update, "Готовы проверить ответы бота?", [[("Начать тестирование", "ex:new")]])

    async def question(self, update: Update, session_id: str) -> None:
        item = self.store.current(session_id, update.effective_user.id)
        if not item or item["finished_at"]:
            await send(update, "Тестирование завершено.", [[("Начать новую сессию", "ex:new")]])
            return
        attempt = self.store.latest(session_id, item["question_id"])
        if attempt and attempt["generation_status"] == "generated":
            await self.show_answer(update, session_id, item["question_id"])
            return
        await send(update, f"Вопрос {item['ordinal'] + 1}/30\n\n{item['query']}", [
            [("Получить ответ", f"ex:answer:{session_id}:{item['question_id']}")],
        ])

    async def answer(self, update: Update, session_id: str, question_id: str) -> None:
        expert_id = update.effective_user.id
        item = self.store.current(session_id, expert_id)
        if not item or item["question_id"] != question_id or item["finished_at"]:
            await send(update, "Откройте текущий вопрос через /expert.")
            return
        model = self.settings.groq_model if self.settings.llm_provider == "groq" else self.settings.openrouter_model
        attempt_id = self.store.claim(session_id, expert_id, question_id,
                                      provider=self.settings.llm_provider, model=model)
        if attempt_id is None:
            attempt = self.store.latest(session_id, question_id)
            if attempt and attempt["generation_status"] == "pending":
                await send(update, "Ответ формируется. Подождите немного.")
                return
        else:
            await send(update, "Готовлю ответ…")
            started = perf_counter()
            try:
                answer = await self.service.answer(item["query"], history=None)
                self.store.save_answer(attempt_id, answer)
            except Exception:
                logger.exception("Expert generation failed for attempt %s", attempt_id)
                self.store.save_error(attempt_id, round((perf_counter() - started) * 1000))
        await self.show_answer(update, session_id, question_id)

    async def show_answer(self, update: Update, session_id: str, question_id: str) -> None:
        expert_id = update.effective_user.id
        if not self.store.session(session_id, expert_id):
            await send(update, "Тестирование недоступно.")
            return
        attempt = self.store.latest(session_id, question_id)
        if not attempt:
            await send(update, "Ответа пока нет.")
            return
        status = attempt["generation_status"]
        if status in {"generated", "clarification"}:
            answer = attempt["answer_text"] or "Ответ отсутствует."
            if attempt["score"] is None:
                rows = [[(str(n), f"ex:rate:{session_id}:{attempt['id']}:{n}") for n in range(1, 6)],
                        [(str(n), f"ex:rate:{session_id}:{attempt['id']}:{n}") for n in range(6, 11)]]
                if status == "generated":
                    rows.append([("Источники RAG", f"ex:sources:{session_id}:{question_id}")])
            else:
                answer += f"\n\nВаша оценка: {attempt['score']}/10"
                rows = [[("Следующий вопрос", f"ex:next:{session_id}")]]
                if status == "generated":
                    rows.append([("Источники RAG", f"ex:sources:{session_id}:{question_id}")])
        else:
            answer = attempt["answer_text"] or "Не удалось получить ответ. Попробуйте ещё раз позже."
            if status == "rejected":
                answer = ("Ответ модели изменён автоматической проверкой и не предлагается к оценке.\n\n"
                          + answer)
            if status == "no_context":
                answer = attempt["answer_text"] or "В базе знаний нет подтверждённого ответа. Какая модель кассы и что именно происходит?"
                answer += "\n\nДиагностика: поиск не вернул фрагменты; LLM не вызывалась."
            elif status == "unavailable":
                reason = attempt["generation_reason"]
                if reason == "api_key_missing":
                    answer += "\n\nДиагностика: ключ провайдера не настроен; LLM не вызывалась."
                else:
                    answer += "\n\nДиагностика: генерация недоступна; LLM не вызывалась."
            elif status == "error":
                answer += "\n\nДиагностика: запрос к API завершился технической ошибкой."
            elif status == "truncated":
                answer = "Ответ не удалось завершить. Попробуйте ещё раз или сократите вопрос."
                answer += "\n\nДиагностика: модель завершила генерацию по лимиту токенов; ответ не предлагался к оценке."
            rows = [[("Повторить", f"ex:answer:{session_id}:{question_id}")],
                    [("Источники RAG", f"ex:sources:{session_id}:{question_id}")]]
        await send(update, answer, rows)

    async def show_sources(self, update: Update, session_id: str, question_id: str) -> None:
        expert_id = update.effective_user.id
        if not self.store.session(session_id, expert_id):
            await send(update, "Тестирование недоступно.")
            return
        attempt = self.store.latest(session_id, question_id)
        if not attempt:
            await send(update, "Для вопроса ещё нет сохранённых источников.")
            return
        sources = json.loads(attempt["results_json"] or "[]")
        if not sources:
            await send(update, "Источники RAG не найдены.", [
                [("Назад к ответу", f"ex:answer_view:{session_id}:{question_id}")]])
            return
        details = []
        for index, source in enumerate(sources, 1):
            metadata = source.get("metadata") or {}
            lines = [f"{index}. {source.get('source', 'Источник не указан')}"]
            if metadata.get("source_url"):
                lines.append(f"Ссылка: {metadata['source_url']}")
            for label, key in (("Раздел", "section"), ("Страница", "page"), ("Статус", "status")):
                if metadata.get(key) is not None:
                    lines.append(f"{label}: {metadata[key]}")
            lines.append(f"Оценка поиска: {source.get('score')} · semantic: {source.get('semantic_score')} · lexical: {source.get('lexical_score')}")
            lines.append("Фрагмент:\n" + source.get("text", ""))
            details.append("\n".join(lines))
        await send(update, "Источники RAG\n\n" + "\n\n".join(details), [
            [("Назад к ответу", f"ex:answer_view:{session_id}:{question_id}")]])

    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self.allowed(update):
            await query.answer("Доступ запрещён", show_alert=True)
            return
        await query.answer()
        parts = (query.data or "").split(":")
        if len(parts) < 2 or parts[0] != "ex":
            return
        action = parts[1]
        expert_id = update.effective_user.id
        try:
            if action == "new":
                session_id = self.store.start(expert_id, load_questions())
                await self.question(update, session_id)
            elif action == "continue":
                session = self.store.active(expert_id)
                if session:
                    await self.question(update, session["id"])
                else:
                    await self.command(update, context)
            elif action == "answer" and len(parts) == 4:
                await self.answer(update, parts[2], parts[3])
            elif action == "sources" and len(parts) == 4:
                await self.show_sources(update, parts[2], parts[3])
            elif action == "answer_view" and len(parts) == 4:
                await self.show_answer(update, parts[2], parts[3])
            elif action == "rate" and len(parts) == 5:
                sid, aid, score = parts[2], int(parts[3]), int(parts[4])
                item = self.store.current(sid, expert_id)
                attempt = self.store.latest(sid, item["question_id"]) if item else None
                if (item and attempt and int(attempt["id"]) == aid
                        and self.store.rate(sid, expert_id, aid, score)):
                    if hasattr(query, "edit_message_reply_markup"):
                        await query.edit_message_reply_markup(reply_markup=None)
                    await send(update, f"Оценка {score}/10 сохранена.", [
                        [("Следующий вопрос", f"ex:next:{sid}")]])
                else:
                    await send(update, "Оценка недоступна для этого ответа.")
            elif action == "next" and len(parts) == 3:
                sid = parts[2]
                item = self.store.current(sid, expert_id)
                attempt = self.store.latest(sid, item["question_id"]) if item else None
                if not item or not attempt or attempt["score"] is None:
                    await send(update, "Сначала оцените ответ от 1 до 10.")
                elif item["ordinal"] + 1 >= item["total"]:
                    self.store.finish(sid, expert_id)
                    await send(update, "Тестирование завершено. Все результаты сохранены.", [
                        [("Начать новую сессию", "ex:new")]])
                elif self.store.move(sid, expert_id, 1):
                    await self.question(update, sid)
            else:
                await send(update, "Откройте тестирование командой /expert.")
        except (ValueError, TypeError, KeyError):
            await send(update, "Не удалось выполнить действие. Откройте /expert и продолжите.")

    async def comment_message(self, update: Update) -> bool:
        # Retained for compatibility with the existing message handler; this flow has no comments.
        return False
