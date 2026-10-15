"""Read-only Home Assistant WebSocket client.

The dashboard configuration (lovelace/config) and the Home Tasks lists are
exposed only over the WebSocket API, not over REST. This client sends the
auth message and the commands in ALLOWED_COMMANDS, nothing else.
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from .ha import HAUnavailable

log = logging.getLogger(__name__)

# Only reads: any other command (call_service, lovelace/config/save, ...) is
# refused before it reaches the socket.
ALLOWED_COMMANDS = frozenset({"lovelace/config", "home_tasks/get_lists", "home_tasks/get_tasks"})

TIMEOUT_SECONDS = 10.0
# A Home Tasks list carries the notes and the history of every task: leave
# room for it, but bound the memory a single answer can take.
MAX_MESSAGE_BYTES = 8 * 2**20
# HA sends nothing we did not ask for unless subscribed; still, never wait
# forever on a server that keeps talking about something else.
MAX_SKIPPED_MESSAGES = 100


class HACommandError(Exception):
    """HA answered a command with success: false."""

    def __init__(self, command: str, code: str, message: str) -> None:
        super().__init__(f"{command}: {code}: {message}")
        self.command = command
        self.code = code
        self.message = message


class _NoRedirects(connect):
    """websockets follows redirects, even to other hosts. The token goes in
    the first message after the handshake, so a redirect would hand it to
    whoever the Location points at: never follow one."""

    def process_redirect(self, exc: Exception) -> Exception:
        return exc


def websocket_url(ha_url: str) -> str:
    for http, ws in (("https://", "wss://"), ("http://", "ws://")):
        if ha_url.startswith(http):
            return ws + ha_url[len(http) :] + "/api/websocket"
    raise ValueError("ha_url must be an http:// or https:// URL")


class HAWebSocket:
    def __init__(self, connection: ClientConnection) -> None:
        self._connection = connection
        self._next_id = 1

    async def _receive(self) -> dict:
        try:
            message = json.loads(await self._connection.recv())
        except ValueError:
            message = None
        if not isinstance(message, dict):
            raise HAUnavailable("HA sent an invalid message")
        return message

    async def _authenticate(self, token: str) -> None:
        if (await self._receive()).get("type") != "auth_required":
            raise HAUnavailable("HA did not ask for authentication")
        await self._connection.send(json.dumps({"type": "auth", "access_token": token}))
        message = await self._receive()
        if message.get("type") == "auth_invalid":
            raise HAUnavailable("HA rejected the token")
        if message.get("type") != "auth_ok":
            raise HAUnavailable("HA did not confirm authentication")

    async def command(self, command: str, **fields: object) -> object:
        """Send one command and return its result."""
        if command not in ALLOWED_COMMANDS:
            raise ValueError(f"Command not allowed: {command}")
        message_id = self._next_id
        self._next_id += 1
        await self._connection.send(json.dumps({**fields, "id": message_id, "type": command}))
        for _ in range(MAX_SKIPPED_MESSAGES):
            message = await self._receive()
            if message.get("id") != message_id or message.get("type") != "result":
                continue
            if message.get("success") is True:
                return message.get("result")
            error = message.get("error")
            if not isinstance(error, dict):
                error = {}
            raise HACommandError(command, str(error.get("code", "")), str(error.get("message", ""))[:200])
        raise HAUnavailable(f"HA did not answer {command}")


@asynccontextmanager
async def ha_websocket(ha_url: str, token: str) -> AsyncIterator[HAWebSocket]:
    """Connect and authenticate; connection problems raise HAUnavailable."""
    try:
        async with _NoRedirects(
            websocket_url(ha_url),
            # HA lives on the LAN: never route the token through a proxy
            # picked up from the environment.
            proxy=None,
            max_size=MAX_MESSAGE_BYTES,
            open_timeout=TIMEOUT_SECONDS,
            close_timeout=1,
        ) as connection:
            client = HAWebSocket(connection)
            await client._authenticate(token)
            yield client
    except (OSError, WebSocketException) as e:
        raise HAUnavailable(type(e).__name__) from e
