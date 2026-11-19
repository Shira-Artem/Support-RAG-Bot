"""Bounded retries only when no HTTP request reached an established connection."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

T = TypeVar("T")
logger = logging.getLogger(__name__)


def connection_failed_before_request(error: Exception) -> bool:
    """Recognize HTTPX errors, including PTB's explicit exception chaining.

    Read/write timeouts and disconnects after sending are deliberately excluded:
    retrying those could duplicate a Telegram message or a billed completion.
    """
    seen = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (httpx.ConnectError, httpx.ConnectTimeout)):
            return True
        current = current.__cause__
    return False


async def retry_connection(operation: Callable[[], Awaitable[T]], *, stage: str) -> T:
    for attempt in range(3):
        try:
            return await operation()
        except Exception as error:
            if attempt == 2 or not connection_failed_before_request(error):
                raise
            # Never log exception text, URL, credentials, payload or identity.
            logger.warning("Connection retry stage=%s attempt=%d/3 error=%s",
                           stage, attempt + 2, type(error).__name__)
            await asyncio.sleep(attempt + 1)
    raise AssertionError("unreachable")
