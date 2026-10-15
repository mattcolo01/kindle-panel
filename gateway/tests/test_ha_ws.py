import asyncio
import json

import pytest

from app.ha import HAUnavailable
from app.ha_ws import HACommandError, ha_websocket, websocket_url
from conftest import HA_TOKEN
from fake_ha import fake_ha, running


def run(coro):
    return asyncio.run(coro)


async def get_config(url: str, token: str = HA_TOKEN, url_path: str = "dashboard-kindle"):
    async with ha_websocket(url, token) as ws:
        return await ws.command("lovelace/config", url_path=url_path)


def test_websocket_url():
    assert websocket_url("http://ha:8123") == "ws://ha:8123/api/websocket"
    assert websocket_url("https://ha.lan") == "wss://ha.lan/api/websocket"
    with pytest.raises(ValueError):
        websocket_url("ftp://ha")


def test_authenticates_with_the_ha_token_then_sends_the_command():
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = {"views": []}
        assert run(get_config(ha.url)) == {"views": []}
    assert ha.received == [
        {"type": "auth", "access_token": HA_TOKEN},
        {"id": 1, "type": "lovelace/config", "url_path": "dashboard-kindle"},
    ]


def test_rejected_token_is_unavailable():
    with fake_ha(HA_TOKEN) as ha:
        with pytest.raises(HAUnavailable):
            run(get_config(ha.url, token="wrong"))
    assert ha.commands == ["auth"]


def test_error_result_raises_command_error():
    with fake_ha(HA_TOKEN) as ha:
        with pytest.raises(HACommandError) as e:
            run(get_config(ha.url, url_path="missing"))
    assert (e.value.command, e.value.code) == ("lovelace/config", "config_not_found")


def test_unrelated_messages_are_skipped():
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = {"views": [1]}
        ha.extra_messages = [{"id": 99, "type": "event", "event": {}}, {"id": 1, "type": "pong"}]
        assert run(get_config(ha.url)) == {"views": [1]}


@pytest.mark.parametrize("command", ["call_service", "lovelace/config/save", "home_tasks/add_task", "get_states"])
def test_only_read_commands_are_sent(command):
    async def send():
        async with ha_websocket(ha.url, HA_TOKEN) as ws:
            await ws.command(command)

    with fake_ha(HA_TOKEN) as ha:
        with pytest.raises(ValueError):
            run(send())
    assert ha.commands == ["auth"]


def test_unreachable_is_unavailable():
    with fake_ha(HA_TOKEN) as ha:
        url = ha.url
    with pytest.raises(HAUnavailable):
        run(get_config(url))


def test_redirect_is_not_followed(monkeypatch):
    """A redirect must not take the token to another server."""
    with fake_ha(HA_TOKEN) as other:
        def redirect(connection, request):
            response = connection.respond(302, "")
            response.headers["Location"] = f"ws://127.0.0.1:{other.port}/api/websocket"
            return response

        with running(lambda ws: None, process_request=redirect) as port:
            with pytest.raises(HAUnavailable):
                run(get_config(f"http://127.0.0.1:{port}"))
    assert other.connections == 0
    assert other.received == []


def test_proxy_from_environment_is_ignored(monkeypatch):
    # Port 9 (discard) on localhost: nothing listens there
    for name in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = {"views": []}
        assert run(get_config(ha.url)) == {"views": []}


def test_oversized_message_is_unavailable(monkeypatch):
    monkeypatch.setattr("app.ha_ws.MAX_MESSAGE_BYTES", 1000)
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = {"views": [], "title": "x" * 2000}
        with pytest.raises(HAUnavailable):
            run(get_config(ha.url))


def test_server_that_never_answers_stops(monkeypatch):
    def chatty(ws):
        ws.send(json.dumps({"type": "auth_required"}))
        ws.recv()
        ws.send(json.dumps({"type": "auth_ok"}))
        ws.recv()
        for _ in range(200):
            ws.send(json.dumps({"id": 0, "type": "event"}))

    with running(chatty) as port:
        with pytest.raises(HAUnavailable):
            run(get_config(f"http://127.0.0.1:{port}"))
