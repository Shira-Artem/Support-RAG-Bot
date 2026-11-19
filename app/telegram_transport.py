"""Telegram connection recovery without repeating ambiguously delivered requests."""
from telegram.request import HTTPXRequest

from app.network_transport import retry_connection


class ConnectionRetryHTTPXRequest(HTTPXRequest):
    async def do_request(self, *args, **kwargs):
        parent = super().do_request
        if str(kwargs.get("url", "")).rsplit("/", 1)[-1] == "sendChatAction":
            return await parent(*args, **kwargs)
        return await retry_connection(lambda: parent(*args, **kwargs), stage="telegram")
