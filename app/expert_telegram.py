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

ERROR_TAGS = {
    "wrong": "Неверный ответ", "invented": "Выдуманные детали",
    "incomplete": "Не хватает шагов", "service": "Перепутан сервис",
    "refusal": "Лишний отказ", "unclear": "Непонятно / много текста",
    "unsafe": "Опасный совет", "retrieval": "Не те источники",
}


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
            progress = f"{item['ordinal'] + 1}/{item['total']}" if item else "продолжить"
            await send(update, f"Есть незавершённое тестирование ({progress}). Все ответы и оценки уже сохранены.", [
                [("Продолжить тестирование", "ex:continue")],
                [("Начать новую сессию", "ex:new")],
            ])
        else:
            await send(update, "Проверьте, насколько ответ помогает клиенту: 1 — совсем не помогает, "
                       "5 — нужно существенно исправить, 10 — корректно и полезно. "
                       "После оценки можно отметить ошибки и добавить комментарий. "
                       "Каждое действие сохраняется сразу; можно пропускать вопросы и возвращаться позже.",
                       [[("Начать тестирование", "ex:new")]])

    def navigation(self, session_id: str) -> list:
        return [[("← Назад", f"ex:prev:{session_id}"), ("Пропустить →", f"ex:skip:{session_id}")],
                [("Выбрать вопрос", f"ex:list:{session_id}:0"), ("Закончить сейчас", f"ex:finish:{session_id}")]]

    async def question(self, update: Update, session_id: str) -> None:
        item = self.store.current(session_id, update.effective_user.id)
        if not item or item["finished_at"]:
            await send(update, "Тестирование завершено.", [[("Начать новую сессию", "ex:new")]])
            return
        attempt = self.store.latest(session_id, item["question_id"])
        if attempt and attempt["generation_status"] != "pending":
            await self.show_answer(update, session_id, item["question_id"])
            return
        await send(update, f"Вопрос {item['ordinal'] + 1}/{item['total']} · {item['category']}\n\n{item['query']}", [
            [("Получить ответ", f"ex:answer:{session_id}:{item['question_id']}")],
        ] + self.navigation(session_id))

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
        answer = attempt["answer_text"] or "Не удалось получить ответ. Попробуйте ещё раз позже."
        if status in {"error", "unavailable", "truncated"}:
            answer += "\n\nТехнический сбой. Можно оценить опыт клиента; эта оценка сохраняется отдельно от статуса генерации."
        rows = []
        if status == "pending":
            answer = "Ответ формируется. Подождите немного."
        elif attempt["score"] is None:
            rows = [[(str(n), f"ex:rate:{session_id}:{attempt['id']}:{n}") for n in range(1, 6)],
                    [(str(n), f"ex:rate:{session_id}:{attempt['id']}:{n}") for n in range(6, 11)]]
        else:
            answer += f"\n\nВаша оценка: {attempt['score']}/10"
            rows = [[("Ошибки / комментарий", f"ex:feedback:{session_id}:{attempt['id']}")],
                    [("Следующий вопрос", f"ex:next:{session_id}")],
                    [("Изменить оценку", f"ex:rerate:{session_id}:{attempt['id']}")]]
        if status in {"error", "unavailable", "truncated"}:
            rows.append([("Повторить запрос", f"ex:answer:{session_id}:{question_id}")])
        rows.append([("Источники RAG", f"ex:sources:{session_id}:{question_id}")])
        rows += self.navigation(session_id)
        items = self.store.questions(session_id, expert_id)
        item = next((item for item in items if item["question_id"] == question_id), None)
        if item:
            answer = f"Вопрос {item['ordinal'] + 1}/{len(items)} · {item['category']}\n{item['query']}\n\nОтвет бота:\n{answer}"
        await send(update, answer, rows)

    async def feedback(self, update: Update, sid: str, aid: int, *, edit: bool = False) -> None:
        if not self.store.session(sid, update.effective_user.id):
            return
        attempt = self.store.review(sid, update.effective_user.id, aid)
        if not attempt or attempt["score"] is None:
            await send(update, "Сначала поставьте оценку ответу.")
            return
        tags = self.store.tags(aid)
        choices = [(("✓ " if key in tags else "") + label, f"ex:tag:{sid}:{aid}:{key}")
                   for key, label in ERROR_TAGS.items()]
        rows = [choices[index:index + 2] for index in range(0, len(choices), 2)]
        rows += [[("Написать комментарий", f"ex:comment:{sid}:{aid}")],
                 [("Изменить оценку", f"ex:rerate:{sid}:{aid}")],
                 [("Следующий вопрос", f"ex:next:{sid}")]] + self.navigation(sid)
        text = f"Оценка {attempt['score']}/10 сохранена. Отметьте одну или несколько ошибок (повторное нажатие снимает отметку)."
        if attempt["comment"]:
            text += "\n\nВаш комментарий: " + attempt["comment"]
        if edit and hasattr(update.callback_query, "edit_message_text"):
            await update.callback_query.edit_message_text(text, reply_markup=keyboard(rows))
        else:
            await send(update, text, rows)

    async def question_list(self, update: Update, sid: str, page: int) -> None:
        items = self.store.questions(sid, update.effective_user.id)
        if not items:
            return
        page = max(0, min(page, (len(items) - 1) // 8))
        rows = []
        for item in items[page * 8:(page + 1) * 8]:
            mark = f"✓ {item['score']}/10" if item["score"] is not None else ("↷" if item["skipped_at"] else "○")
            label = f"{item['ordinal'] + 1}. {mark} {item['query']}"[:80]
            rows.append([(label, f"ex:select:{sid}:{item['ordinal']}")])
        pages = []
        if page:
            pages.append(("← Ещё", f"ex:list:{sid}:{page - 1}"))
        if (page + 1) * 8 < len(items):
            pages.append(("Ещё →", f"ex:list:{sid}:{page + 1}"))
        if pages:
            rows.append(pages)
        rows.append([("Текущий вопрос", "ex:continue")])
        reviewed, total = self.store.progress(sid, update.effective_user.id)
        await send(update, f"Выберите вопрос · оценено {reviewed}/{total}. Пропущенные можно открыть в любой момент.", rows)

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
                session_id = self.store.start(expert_id, load_questions(), shuffle=True)
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
                if self.store.rate(sid, expert_id, aid, score):
                    if hasattr(query, "edit_message_reply_markup"):
                        await query.edit_message_reply_markup(reply_markup=None)
                    await self.feedback(update, sid, aid)
                else:
                    await send(update, "Оценка недоступна для этого ответа.")
            elif action == "feedback" and len(parts) == 4:
                await self.feedback(update, parts[2], int(parts[3]))
            elif action == "tag" and len(parts) == 5:
                sid, aid, tag = parts[2], int(parts[3]), parts[4]
                if tag in ERROR_TAGS and self.store.toggle_tag(sid, expert_id, aid, tag):
                    await self.feedback(update, sid, aid, edit=True)
            elif action == "comment" and len(parts) == 4:
                sid, aid = parts[2], int(parts[3])
                if self.store.request_comment(sid, expert_id, aid):
                    await send(update, "Напишите короткий комментарий: что неверно и как ответить лучше. "
                               "Он сохранится сразу (до 2000 символов).", [
                                   [("Отменить комментарий", f"ex:cancel:{sid}")]])
            elif action == "cancel" and len(parts) == 3:
                self.store.cancel_comment(parts[2], expert_id)
                await self.question(update, parts[2])
            elif action == "rerate" and len(parts) == 4:
                sid, aid = parts[2], int(parts[3])
                if self.store.session(sid, expert_id):
                    await send(update, "Выберите новую оценку:", [
                        [(str(n), f"ex:rate:{sid}:{aid}:{n}") for n in range(1, 6)],
                        [(str(n), f"ex:rate:{sid}:{aid}:{n}") for n in range(6, 11)]])
            elif action == "list" and len(parts) == 4:
                await self.question_list(update, parts[2], int(parts[3]))
            elif action == "select" and len(parts) == 4:
                if self.store.select(parts[2], expert_id, int(parts[3])):
                    await self.question(update, parts[2])
            elif action in {"prev", "skip"} and len(parts) == 3:
                sid = parts[2]
                if self.store.move(sid, expert_id, -1 if action == "prev" else 1, skip=action == "skip"):
                    await self.question(update, sid)
            elif action == "finish" and len(parts) == 3:
                sid = parts[2]
                if self.store.session(sid, expert_id):
                    reviewed, total = self.store.progress(sid, expert_id)
                    self.store.finish(sid, expert_id)
                    await send(update, f"Сессия завершена: оценено {reviewed}/{total}. "
                               "Все полученные ответы, оценки и комментарии сохранены.",
                               [[("Начать новую сессию", "ex:new")]])
            elif action == "next" and len(parts) == 3:
                sid = parts[2]
                item = self.store.current(sid, expert_id)
                if item and item["ordinal"] + 1 >= item["total"]:
                    reviewed, total = self.store.progress(sid, expert_id)
                    await send(update, f"Это последний вопрос. Оценено {reviewed}/{total}; все результаты уже сохранены.", [
                        [("Выбрать вопрос", f"ex:list:{sid}:0"), ("Закончить сейчас", f"ex:finish:{sid}")]])
                elif self.store.move(sid, expert_id, 1):
                    await self.question(update, sid)
            else:
                await send(update, "Откройте тестирование командой /expert.")
        except (ValueError, TypeError, KeyError):
            await send(update, "Не удалось выполнить действие. Откройте /expert и продолжите.")

    async def comment_message(self, update: Update) -> bool:
        if not self.allowed(update) or not update.message or not update.message.text:
            return False
        session = self.store.active(update.effective_user.id)
        aid = session["comment_target"] if session else None
        if aid and self.store.save_comment(update.effective_user.id, update.message.text.strip()):
            await send(update, "Комментарий сохранён.")
            await self.feedback(update, session["id"], aid)
            return True
        return False
