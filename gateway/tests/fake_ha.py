"""A Home Assistant WebSocket API stand-in, run in a thread.

Messages follow homeassistant/components/websocket_api (2026.6.0):
auth_required -> auth -> auth_ok / auth_invalid, then
{"id", "type": "result", "success", "result" | "error": {code, message}}.
"""

import json
import threading
from contextlib import contextmanager

from websockets.sync.server import ServerConnection, serve


class FakeHA:
    def __init__(self, token: str) -> None:
        self.token = token
        self.dashboards: dict[str, dict] = {}
        self.lists: list[dict] = []
        self.tasks: dict[str, dict] = {}
        self.received: list[dict] = []  # every message the client sent
        self.connections = 0
        self.extra_messages: list[dict] = []  # sent before each result
        self.port = 0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def commands(self) -> list[str]:
        return [m.get("type") for m in self.received]

    def result(self, message: dict) -> dict:
        command = message.get("type")
        if command == "lovelace/config":
            url_path = message.get("url_path")
            if url_path not in self.dashboards:
                return {"success": False, "error": {"code": "config_not_found",
                                                    "message": f"Unknown config specified: {url_path}"}}
            return {"success": True, "result": self.dashboards[url_path]}
        if command == "home_tasks/get_lists":
            return {"success": True, "result": {"lists": self.lists}}
        if command == "home_tasks/get_tasks":
            if message.get("list_id") not in self.tasks:
                return {"success": False, "error": {"code": "invalid_request", "message": "List not found"}}
            return {"success": True, "result": self.tasks[message["list_id"]]}
        return {"success": False, "error": {"code": "unknown_command", "message": "Unknown command."}}

    def handler(self, ws: ServerConnection) -> None:
        self.connections += 1
        ws.send(json.dumps({"type": "auth_required", "ha_version": "2026.6.0"}))
        auth = json.loads(ws.recv())
        self.received.append(auth)
        if auth.get("type") != "auth" or auth.get("access_token") != self.token:
            ws.send(json.dumps({"type": "auth_invalid", "message": "Invalid access token or password"}))
            return
        ws.send(json.dumps({"type": "auth_ok", "ha_version": "2026.6.0"}))
        for raw in ws:
            message = json.loads(raw)
            self.received.append(message)
            for extra in self.extra_messages:
                ws.send(json.dumps(extra))
            ws.send(json.dumps({"id": message.get("id"), "type": "result", **self.result(message)}))


@contextmanager
def running(handler, **kwargs):
    """Serve handler on 127.0.0.1 (random port) in a thread; yield the port."""
    with serve(handler, "127.0.0.1", 0, **kwargs) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.socket.getsockname()[1]
        finally:
            server.shutdown()
            thread.join(5)


@contextmanager
def fake_ha(token: str):
    ha = FakeHA(token)
    with running(ha.handler) as port:
        ha.port = port
        yield ha
