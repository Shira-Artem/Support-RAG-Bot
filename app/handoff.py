"""Opt-in specialist handoff with an isolated, idempotent delivery outbox."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Protocol


@dataclass(frozen=True)
class HandoffSettings:
    enabled: bool = False
    bot_token: str = ""
    specialist_chat_id: str = ""
    state_path: Path = Path(".local/handoff_outbox.json")
    approved_chat_id: str = ""

    @classmethod
    def from_env(cls) -> "HandoffSettings":
        # Disabled by default even when the bot token is already configured.
        return cls(
            enabled=os.getenv("HANDOFF_ENABLED", "").strip().lower() in {"1", "true", "yes"},
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            specialist_chat_id=os.getenv("TELEGRAM_SPECIALIST_CHAT_ID", "").strip(),
            state_path=Path(os.getenv("HANDOFF_STATE_PATH", ".local/handoff_outbox.json")),
            approved_chat_id=os.getenv("HANDOFF_APPROVED_CHAT_ID", "").strip(),
        )

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.bot_token and _valid_chat_id(self.specialist_chat_id)
                    and _valid_chat_id(self.approved_chat_id)
                    and self.specialist_chat_id == self.approved_chat_id)


class MessageTransport(Protocol):
    async def send_message(self, chat_id: str, text: str) -> object: ...


class TelegramBotApiTransport:
    """Thin Telegram Bot API adapter. No instance is created unless explicitly enabled."""

    def __init__(self, token: str):
        if not token.strip():
            raise ValueError("Telegram bot token is required")
        self._token = token

    async def send_message(self, chat_id: str, text: str) -> object:
        from telegram import Bot

        async with Bot(self._token) as bot:
            message = await bot.send_message(chat_id=chat_id, text=text)
        # python-telegram-bot returns a Message only after Telegram's ok=true response.
        if not getattr(message, "message_id", None) or str(message.chat_id) != str(chat_id):
            raise RuntimeError("Telegram response did not confirm the configured destination")
        return message


class JsonHandoffOutbox:
    """A worktree-local sidecar: delivery status is isolated from support SQLite."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = asyncio.Lock()

    def get(self, ticket_id: str) -> dict | None:
        return self._read().get(ticket_id)

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="handoff-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def update(self, ticket_id: str, record: dict) -> None:
        data = self._read()
        data[ticket_id] = record
        self._write(data)


class HandoffService:
    def __init__(self, settings: HandoffSettings, transport: MessageTransport | None = None,
                 *, progress_provider=None):
        self.settings = settings
        self.transport = transport
        self.outbox = JsonHandoffOutbox(settings.state_path)
        self.progress_provider = progress_provider
        self._lock = asyncio.Lock()

    def prepare(self, bundle: dict) -> str:
        progress = None
        if self.progress_provider:
            progress = self.progress_provider(bundle.get('conversation_id'),
                                              (bundle.get('task') or {}).get('task_id'))
        lines = [f"Заявка {bundle['ticket_id']}",
                 f"Причина эскалации: {bundle.get('escalation_reason') or 'не указана'}"]
        task = bundle.get('task') or {}
        facts = bundle.get('confirmed_facts') or []
        values_by_slot: dict[str, list[tuple[str, str]]] = {}
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            slot = str(fact.get('slot') or '')
            value = fact.get('value')
            quote = fact.get('quote')
            rendered = str(value or quote or '').strip()
            if rendered:
                values_by_slot.setdefault(slot, []).append((str(value or '').strip(), str(quote or '').strip()))

        def values(*slots: str, quote_first: bool = False) -> str:
            result = []
            for slot in slots:
                for fact_value, quote in values_by_slot.get(slot, []):
                    value = quote if quote_first and quote else fact_value or quote
                    if value not in result:
                        result.append(value)
            return ', '.join(_redact_personal_data(value) for value in result) or 'не указано'

        objective = task.get('task') or task.get('operation') or task.get('object') or 'не определена'
        lines += [
            f"Задача: {_redact_personal_data(objective)}",
            f"Сервис: {values('service', 'ofd', 'integration')}",
            f"Оборудование: {values('equipment', 'manufacturer', 'model', 'component')}",
            f"Симптомы: {values('task_fact', 'symptom', 'details', quote_first=True)}",
            f"Код ошибки: {values('error')}",
            f"Известные факты: {_json_compact(_redact_value(facts))}",
            f"Результаты проверок: {_json_compact(_redact_value(progress)) if progress is not None else 'не зафиксированы'}",
        ]
        messages = bundle.get('messages') or []
        if messages:
            lines.append("Последние значимые сообщения:")
            for item in messages[-8:]:
                role = 'Клиент' if item.get('role') == 'user' else 'Бот'
                lines.append(f"{role}: {_redact_personal_data(item.get('text', ''))}")
        unresolved = list(dict.fromkeys(str(item).strip() for item in bundle.get('open_questions', [])
                                       if str(item).strip()))
        unanswered = _last_unanswered_question(messages)
        if unanswered and unanswered not in unresolved:
            unresolved.append(unanswered)
        unresolved_text = '; '.join(_redact_personal_data(item) for item in unresolved) or 'не указаны'
        lines.append(f"Нерешённые вопросы: {unresolved_text}")
        text = "\n".join(lines)
        return text[:3900]

    async def deliver(self, bundle: dict, *, retry: bool = False) -> dict:
        ticket_id = bundle['ticket_id']
        async with self._lock:
            existing = self.outbox.get(ticket_id)
            if existing and existing['status'] == 'delivered':
                return {'ticket_id': ticket_id, **existing}
            if existing and existing['status'] == 'pending' and not retry:
                return {'ticket_id': ticket_id, **existing}
            if existing and existing['status'] == 'failed' and not retry:
                return {'ticket_id': ticket_id, **existing}
            if not self.settings.enabled:
                return self._record_failed(ticket_id, 'handoff_disabled')
            if not self.settings.specialist_chat_id or not _valid_chat_id(self.settings.specialist_chat_id):
                return self._record_failed(ticket_id, 'specialist_chat_not_configured')
            if (not _valid_chat_id(self.settings.approved_chat_id)
                    or self.settings.specialist_chat_id != self.settings.approved_chat_id):
                return self._record_failed(ticket_id, 'specialist_chat_not_approved')
            if self.transport is None:
                return self._record_failed(ticket_id, 'transport_not_configured')
            payload = self.prepare(bundle)
            self.outbox.update(ticket_id, {'status': 'pending', 'payload': payload})
            try:
                receipt = await self.transport.send_message(self.settings.specialist_chat_id, payload)
                confirmed = bool(receipt) and _receipt_matches(receipt, self.settings.specialist_chat_id)
                if not confirmed:
                    raise RuntimeError('transport_did_not_confirm_destination')
            except Exception as exc:
                # Do not silently retry: a timeout can happen after Telegram accepted the message.
                return self._record_failed(ticket_id, type(exc).__name__)
            record = {'status': 'delivered', 'payload': payload,
                      'telegram_message_id': _receipt_message_id(receipt)}
            self.outbox.update(ticket_id, record)
            return {'ticket_id': ticket_id, **record}

    def _record_failed(self, ticket_id: str, code: str) -> dict:
        record = {'status': 'failed', 'error': code}
        self.outbox.update(ticket_id, record)
        return {'ticket_id': ticket_id, **record}


def _valid_chat_id(value: str) -> bool:
    return bool(re.fullmatch(r"-?\d{1,20}", str(value).strip()) and int(value) != 0)


def _last_unanswered_question(messages: list[dict]) -> str | None:
    """Return a bot clarification only when it is the last task-bound message."""
    if not messages or messages[-1].get('role') != 'assistant':
        return None
    text = str(messages[-1].get('text') or '').strip()
    if '?' not in text:
        return None
    return text[-1000:]


def specialist_request(text: str) -> bool:
    """Bounded, model-free route for direct user requests to speak to a person."""
    normalized = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
    if re.search(r"\b(?:не|без)\s+(?:нужен|нужна|нужно|надо)?\s*специалист", normalized):
        return False
    if re.search(r"\bне\s+(?:позови|позовите|вызови|вызовите|позвать)\b", normalized):
        return False
    return bool(re.search(
        r"\b(?:позови|позовите|вызови|вызовите|нужен|нужна|хочу|позвать)\b.{0,48}\bспециалист\w*\b",
        normalized))


def _receipt_matches(receipt: object, chat_id: str) -> bool:
    if isinstance(receipt, dict):
        return bool(receipt.get('ok') is True and receipt.get('result', {}).get('message_id')
                    and str(receipt.get('result', {}).get('chat', {}).get('id')) == str(chat_id))
    return bool(getattr(receipt, 'message_id', None)
                and str(getattr(receipt, 'chat_id', '')) == str(chat_id))


def _receipt_message_id(receipt: object):
    if isinstance(receipt, dict):
        return receipt.get('result', {}).get('message_id')
    return getattr(receipt, 'message_id', None)


def _json_compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _redact_value(value):
    if isinstance(value, str):
        return _redact_personal_data(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    return value


def _redact_personal_data(value: object) -> str:
    """Remove common contact identifiers before composing a staff payload."""
    text = str(value or '')
    text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[email скрыт]", text)
    return re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)", "[телефон скрыт]", text)
