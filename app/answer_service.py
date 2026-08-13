from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings
from app.openrouter_client import OpenRouterError, ask_openrouter
from app.rag import SearchResult, SimpleRAG


SYSTEM_PROMPT = """Ты — вежливый Telegram-бот поддержки клиентов по кассовому оборудованию, ОФД, ФН, маркировке, ТС ПиОТ, ЕГАИС и бухгалтерским услугам.

Правила:
1. Отвечай на русском языке, коротко и по делу.
2. Используй только переданный контекст из базы знаний.
3. Если в контексте нет точного ответа — честно скажи, что нужно уточнение у специалиста.
4. Не выдумывай цены, сроки, законы, контакты и инструкции.
5. Для технических проблем давай безопасные первые шаги проверки.
6. Если проблема может привести к блокировке кассы, замене ФН, перерегистрации или работе с ФНС — рекомендуй обратиться к специалисту.
7. Не представляйся юристом, налоговым консультантом или сотрудником ФНС.
"""


@dataclass
class Answer:
    text: str
    results: list[SearchResult] = field(default_factory=list)
    used_model: bool = False


class AnswerService:
    def __init__(self, rag: SimpleRAG, settings: Settings):
        self.rag = rag
        self.settings = settings

    async def answer(self, user_message: str, history: list[dict] | None = None) -> Answer:
        results = self.rag.search(user_message, top_k=5)
        context = self.rag.build_context(results)

        if not results:
            return Answer(
                text=(
                    "Я пока не нашёл точной информации в базе знаний. "
                    "Лучше передать вопрос специалисту или добавить этот случай в FAQ."
                ),
                results=[],
                used_model=False,
            )

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Контекст из базы знаний:\n"
                    f"{context}\n\n"
                    "Вопрос клиента:\n"
                    f"{user_message}\n\n"
                    "Сформируй понятный ответ для Telegram. "
                    "Если есть несколько шагов, дай их списком. "
                    "В конце добавь мягкую рекомендацию обратиться к специалисту, если ситуация сложная."
                ),
            },
        ]

        if history:
            # Передаем только последние 4 сообщения, чтобы не раздувать запрос.
            compact_history = history[-4:]
            messages.insert(1, {"role": "system", "content": f"Краткая история диалога: {compact_history}"})

        if not self.settings.openrouter_api_key:
            return Answer(
                text=self._fallback_answer(user_message, results),
                results=results,
                used_model=False,
            )

        try:
            text = await ask_openrouter(
                api_key=self.settings.openrouter_api_key,
                model=self.settings.openrouter_model,
                app_name=self.settings.app_name,
                app_url=self.settings.app_url,
                messages=messages,
            )
            if self.settings.show_sources:
                text += "\n\n" + self._format_sources(results)
            return Answer(text=text, results=results, used_model=True)
        except OpenRouterError as exc:
            return Answer(
                text=(
                    "Модель сейчас не ответила, поэтому даю найденные фрагменты из базы знаний.\n\n"
                    f"{self._fallback_answer(user_message, results)}\n\n"
                    f"Техническая ошибка OpenRouter: {exc}"
                ),
                results=results,
                used_model=False,
            )

    def _fallback_answer(self, user_message: str, results: list[SearchResult]) -> str:
        top = results[:3]
        parts = [
            "Нашёл похожую информацию в базе знаний. Коротко:",
        ]
        for item in top:
            snippet = item.text.strip()
            if len(snippet) > 700:
                snippet = snippet[:700].rsplit(" ", 1)[0] + "..."
            parts.append(f"• {snippet}")
        parts.append("Если вопрос связан с заменой ФН, блокировкой кассы или ФНС, лучше подключить специалиста.")
        parts.append(self._format_sources(results))
        return "\n\n".join(parts)

    def _format_sources(self, results: list[SearchResult]) -> str:
        sources = []
        for item in results:
            if item.source not in sources:
                sources.append(item.source)
        return "Локальные источники: " + ", ".join(sources[:5])
