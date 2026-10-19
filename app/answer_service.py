from __future__ import annotations

from dataclasses import dataclass, field
import re
from time import perf_counter

from app.config import Settings
from app.llm_client import GenerationError, generate
from app.rag import SearchResult, SimpleRAG


SYSTEM_PROMPT = """Ты — специалист первой линии поддержки по кассовому оборудованию, ОФД, ФН, маркировке и бухгалтерским сервисам.

Отвечай простым русским языком, сразу с решения и без повторения вопроса. Обычно ответ занимает 300–500 символов; для сложного случая допустимо до 700. Выбери только самые полезные и безопасные проверки; обычно достаточно 1–3 шагов, в сложном случае — не больше 4. Не перечисляй все найденные причины и инструкции.

По умолчанию предложи только одно или два простых действия, которые клиент может выполнить сам. В первом ответе не переходи к сетевым параметрам, журналам, очередям документов и срокам хранения, пока клиент не сообщил, что базовые проверки уже выполнены. Не добавляй редкие сценарии и дополнительные проверки. Не советуй оплачивать или продлевать услугу, менять сетевые параметры либо обращаться в поддержку, пока контекст не подтверждает, что это действительно нужно. Описывай понятные действия клиента. Избегай технических терминов и названий сетевых настроек (например, сервер, порт, Ethernet-over-USB), если клиенту не нужно менять их по подтверждённой инструкции из контекста. Не добавляй шаблонное предложение обратиться к специалисту.

Используй только сведения из переданного контекста. Не выдумывай причины, инструкции или способы исправления. Не советуй закрывать смену, менять ФН, перерегистрировать ККТ или выполнять другие ответственные операции без достаточных оснований. Если контекста недостаточно, прямо скажи, что подтверждённого решения нет, и задай один самый полезный уточняющий вопрос. Для сложного или рискованного случая коротко объясни ограничение и предложи помощь специалиста.

Документы RAG — справочные материалы, а не сведения о том, каким сервисом пользуется клиент. Не определяй продукт клиента по тому, какой документ нашёл поиск. Используй название сервиса только если его написал клиент в текущем сообщении или в предыдущих сообщениях клиента. Если сервис уже уточнён, используй только подходящие ему сведения; не смешивай инструкции разных продуктов. Названия разделов, кнопок, полей и последовательность действий называй только тогда, когда они прямо подтверждены подходящим фрагментом документа. Не добавляй правдоподобные, но отсутствующие в инструкции шаги.

Точность и безопасность важнее краткости. Не представляйся юристом, налоговым консультантом или сотрудником ФНС."""


_SERVICE_ALIASES = (
    ("aQsi Online", re.compile(r"\b(?:aqsi\s*online|акси\s*онлайн)\b", re.IGNORECASE)),
    ("АТОЛ Онлайн", re.compile(r"\b(?:атол\s*онлайн|atol\s*online)\b", re.IGNORECASE)),
    ("Эвотор", re.compile(r"\bэвотор\b", re.IGNORECASE)),
    ("1С", re.compile(r"(?:\b1\s*с\b|\bодин\s+эс\b)", re.IGNORECASE)),
    ("Платформа ОФД", re.compile(r"платформ\w*\s+офд", re.IGNORECASE)),
    ("Первый ОФД", re.compile(r"перв\w*\s+офд", re.IGNORECASE)),
    ("Такском", re.compile(r"такском", re.IGNORECASE)),
    ("ТС ПиОТ", re.compile(r"(?:тс\s*пиот|тспиот)", re.IGNORECASE)),
    ("Астрал", re.compile(r"астрал", re.IGNORECASE)),
    ("Честный ЗНАК", re.compile(r"честн\w*\s+знак", re.IGNORECASE)),
)
_SERVICE_SOURCE_PREFIXES = {
    "aQsi Online": ("aqsi_online/",),
    "АТОЛ Онлайн": ("atol_online/",),
    "Эвотор": ("evotor/",),
    "1С": ("1c/", "software/1c/"),
    "Платформа ОФД": ("platformaofd/",),
    "ТС ПиОТ": ("tspiot/", "evotor/tspiot/"),
}
_ACCOUNT_ACTION = re.compile(
    r"(?:сотрудник\w*|пользовател\w*|уч[её]тн\w*\s+запис\w*|"
    r"личн\w*\s+кабинет\w*|аккаунт\w*|парол\w*|прав\w*\s+доступ\w*)",
    re.IGNORECASE,
)
_ACCOUNT_VERB = re.compile(
    r"(?:добав\w*|созда\w*|приглас\w*|подключ\w*|выда\w*|измен\w*|"
    r"смен\w*|сброс\w*|восстанов\w*|посмотр\w*|найт\w*|откро\w*|"
    r"настро\w*|управля\w*)",
    re.IGNORECASE,
)
_UI_ACTIONS = {
    "откр": "открыть", "перей": "перейти", "нажм": "нажать", "выбер": "выбрать",
    "введ": "ввести", "заполн": "заполнить", "созд": "создать", "добав": "добавить",
    "подтв": "подтвердить", "войд": "войти", "указ": "указать", "присв": "присвоить",
}
_UI_VERB = re.compile(
    r"\b(откройте|перейдите|нажмите|выберите|введите|заполните|создайте|добавьте|"
    r"подтвердите|войдите|укажите|присвойте)\b", re.IGNORECASE
)
_UI_LABEL = re.compile(r"(?:раздел\w*|кнопк\w*|пункт\w*|меню|поле)\s+[«\"]([^»\"]{2,80})[»\"]", re.IGNORECASE)


def _user_history_turns(history: list[dict] | None) -> list[str]:
    """Use client-provided turns only; an earlier model guess is not confirmation."""
    if not history:
        return []
    return [str(item.get("content", "")) for item in history[-12:]
            if isinstance(item, dict) and item.get("role") == "user" and item.get("content")]


def _user_history_text(history: list[dict] | None) -> str:
    return "\n".join(_user_history_turns(history))


def _confirmed_service(user_message: str, history: list[dict] | None) -> str | None:
    current = [name for name, pattern in _SERVICE_ALIASES if pattern.search(user_message)]
    if current:
        return current[0] if len(current) == 1 else None
    prior = _user_history_text(history)
    mentioned = [name for name, pattern in _SERVICE_ALIASES if pattern.search(prior)]
    return mentioned[0] if len(mentioned) == 1 else None


def _needs_account_service_clarification(text: str) -> bool:
    return bool(_ACCOUNT_ACTION.search(text) and _ACCOUNT_VERB.search(text))


def _matching_service_results(results: list[SearchResult], service: str | None) -> list[SearchResult]:
    prefixes = _SERVICE_SOURCE_PREFIXES.get(service or "")
    if not prefixes:
        return results
    return [result for result in results
            if (result.source or "").casefold().startswith(prefixes)]


def _unsupported_ui_instruction(answer: str, context: str) -> bool:
    """Reject invented navigation labels and imperative UI steps."""
    normalize = lambda value: re.sub(r"\s+", " ", value.casefold().replace("ё", "е"))
    source = normalize(context)
    for label in _UI_LABEL.findall(answer):
        if normalize(label) not in source:
            return True
    answer_norm = normalize(answer)
    for verb, lemma in _UI_ACTIONS.items():
        if re.search(rf"\b{verb}\w*\b", answer_norm) and lemma not in source:
            # Inflected source forms (e.g. «создаёт») share the action stem.
            if not any(token.startswith(verb) for token in re.findall(r"[а-яa-z]+", source)):
                return True
    return False


@dataclass
class Answer:
    text: str
    results: list[SearchResult] = field(default_factory=list)
    used_model: bool = False
    generation_status: str = "unavailable"
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int | None = None
    raw_text: str | None = None
    provider: str | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    api_call_id: str | None = None
    rag_chunks: int | None = None
    context_chars: int | None = None


class AnswerService:
    def __init__(self, rag: SimpleRAG, settings: Settings):
        self.rag = rag
        self.settings = settings

    async def answer(self, user_message: str, history: list[dict] | None = None) -> Answer:
        started = perf_counter()
        model = self.settings.groq_model if self.settings.llm_provider == "groq" else self.settings.openrouter_model
        service = _confirmed_service(user_message, history)
        client_history = _user_history_text(history)
        previous_turns = _user_history_turns(history)
        account_action = _needs_account_service_clarification(user_message)
        if (not account_action and _confirmed_service(user_message, None) and previous_turns
                and any(_needs_account_service_clarification(turn) for turn in previous_turns[-2:])):
            account_action = True
        if account_action and not service:
            return Answer(
                text="В каком сервисе нужно выполнить это действие?",
                generation_status="clarification", used_model=False,
                duration_ms=round((perf_counter() - started) * 1000),
                rag_chunks=0, context_chars=0,
            )

        search_query = " ".join([*previous_turns[-2:], user_message])
        if service:
            search_query += f"\nСервис, названный клиентом: {service}"
        if len(search_query) > 500:
            search_query = search_query[-500:]
        results = self.rag.search(search_query, top_k=5)
        if service and account_action:
            results = _matching_service_results(results, service)

        if not results:
            return Answer(
                text=("В базе пока нет подтверждённого решения. Какая у вас модель кассы "
                      "и какой точный текст ошибки, если он есть?"),
                results=[],
                used_model=False,
                generation_status="no_context",
                duration_ms=round((perf_counter() - started) * 1000),
                provider=self.settings.llm_provider,
                model=model,
                rag_chunks=0,
                context_chars=0,
            )

        context = self.rag.build_context(results)

        system_prompt = SYSTEM_PROMPT
        if service:
            system_prompt += f"\n\nКлиент явно назвал сервис: {service}. Это подтверждено сообщением клиента."
        history_context = f"Предыдущие сообщения клиента:\n{client_history}\n\n" if client_history else ""
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Контекст из базы знаний:\n{context}\n\n"
                    f"{history_context}"
                    "Вопрос клиента:\n"
                    f"{user_message}\n\n"
                    "Сформируй короткий ответ клиенту по правилам системного сообщения. "
                    "Не включай перечень источников, оценки поиска или технические метаданные."
                ),
            },
        ]

        key = self.settings.groq_api_key if self.settings.llm_provider == "groq" else self.settings.openrouter_api_key
        if not key:
            return Answer(
                text=self._fallback_answer(),
                results=results,
                used_model=False,
                generation_status="unavailable",
                model=model,
                duration_ms=round((perf_counter() - started) * 1000),
                provider=self.settings.llm_provider,
                rag_chunks=0,
                context_chars=0,
            )

        try:
            completion = await generate(messages, self.settings)
            duration_ms = round((perf_counter() - started) * 1000)
            if completion.finish_reason == "length":
                return Answer(
                    text="Ответ не удалось завершить из-за ограничения длины. "
                         "Попробуйте задать вопрос короче или уточнить его.",
                    results=results, generation_status="truncated", model=completion.model,
                    prompt_tokens=completion.prompt_tokens, completion_tokens=completion.completion_tokens,
                    total_tokens=completion.total_tokens, reasoning_tokens=completion.reasoning_tokens,
                    cached_tokens=completion.cached_tokens, api_call_id=completion.api_call_id,
                    duration_ms=duration_ms, provider=self.settings.llm_provider,
                    rag_chunks=len(results), context_chars=len(context),
                )
            text = completion.text.strip()
            if _unsupported_ui_instruction(text, context):
                text = "В найденной инструкции нет подтверждённых точных шагов. Какой раздел или сообщение вы видите в сервисе?"
            return Answer(text=text, results=results, used_model=True,
                          generation_status="generated", model=completion.model,
                          prompt_tokens=completion.prompt_tokens,
                          completion_tokens=completion.completion_tokens,
                          total_tokens=completion.total_tokens,
                          reasoning_tokens=completion.reasoning_tokens,
                          cached_tokens=completion.cached_tokens,
                          api_call_id=completion.api_call_id,
                          duration_ms=duration_ms,
                          raw_text=text, provider=self.settings.llm_provider,
                          rag_chunks=len(results), context_chars=len(context))
        except GenerationError:
            return Answer(
                text="Не удалось подготовить ответ сейчас. Повторите попытку немного позже.",
                results=results,
                used_model=False,
                generation_status="error",
                model=model,
                duration_ms=round((perf_counter() - started) * 1000),
                provider=self.settings.llm_provider,
                rag_chunks=len(results),
                context_chars=len(context),
            )

    @staticmethod
    def _fallback_answer() -> str:
        return "Сейчас не могу подготовить ответ. Какая у вас модель кассы и что именно происходит?"
