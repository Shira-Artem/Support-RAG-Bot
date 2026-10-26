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

    @classmethod
    def from_env(cls) -> "HandoffSettings":
        # Disabled by default even when the bot token is already configured.
        return cls(
            enabled=os.getenv("HANDOFF_ENABLED", "").strip().lower() in {"1", "true", "yes"},
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            specialist_chat_id=os.getenv("TELEGRAM_SPECIALIST_CHAT_ID", "").strip(),
            state_path=Path(os.getenv("HANDOFF_STATE_PATH", ".local/handoff_outbox.json")),
        )

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.bot_token and _valid_chat_id(self.specialist_chat_id))


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
        lines += [f"Задача: {task.get('task') or task.get('operation') or 'не определена'}",
                  f"Факты клиента (с цитатами): {_json_compact(bundle.get('confirmed_facts') or [])}"]
        if progress is not None:
            lines.append(f"Результаты проверок: {_json_compact(progress)}")
        messages = bundle.get('messages') or []
        if messages:
            lines.append("Последние значимые сообщения:")
            for item in messages[-8:]:
                role = 'Клиент' if item.get('role') == 'user' else 'Бот'
                lines.append(f"{role}: {item.get('text', '')}")
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
