"""kindle-gateway: serves the dashboard PNG to the Kindle.

Endpoints:
  GET /kindle.png  Bearer KINDLE_TOKEN required; optional X-Kindle-Battery.
  GET /healthz     unauthenticated, returns "ok" and nothing else.

The image shows either the entities listed in config.yaml (rows) or an HA
dashboard (dashboard: <url_path>), read over the WebSocket API.

Run with: uvicorn --factory app.main:create_app
"""

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from starlette.concurrency import run_in_threadpool

from .config import Settings, load_settings
from .dashboard import DashboardError, assigned_persons, fetch_dashboard, person_names
from .dashboard import build_view as build_dashboard_view
from .ha import HAClient, HAUnavailable
from .ha_ws import TIMEOUT_SECONDS, HACommandError, ha_websocket
from .render import build_view, check_fonts, parse_battery, render
from .render_dashboard import render_dashboard

log = logging.getLogger(__name__)


def is_authorized(request: Request, token: str) -> bool:
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(credentials.strip().encode(), token.encode())


async def dashboard_png(settings: Settings, ha: HAClient, battery: int | None) -> bytes | None:
    """The dashboard image, or None (logged) when it cannot be drawn."""
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            async with ha_websocket(settings.ha_url, settings.ha_token) as ws:
                data = await fetch_dashboard(ws, settings.dashboard)
    except HACommandError as e:
        if e.command == "lovelace/config" and e.code == "config_not_found":
            log.error("Dashboard %r not found, or never edited (auto-generated): %s", settings.dashboard, e.message)
        else:
            log.error("Home Assistant refused %s: %s %s", e.command, e.code, e.message)
        return None
    except DashboardError as e:
        log.error("Dashboard %r cannot be drawn: %s", settings.dashboard, e)
        return None
    except (HAUnavailable, TimeoutError) as e:
        log.error("Home Assistant WebSocket unavailable: %s", str(e) or type(e).__name__)
        return None

    persons = assigned_persons(data)
    names: dict[str, str] = {}
    if persons:
        try:
            names = person_names(await ha.get_states(persons))
        except HAUnavailable:
            log.warning("Could not read the names of assigned persons")
    view = build_dashboard_view(data, names, settings.language, datetime.now(settings.timezone).date(), battery)
    return await run_in_threadpool(render_dashboard, view)


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = load_settings()
    check_fonts()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ha = HAClient(settings.ha_url, settings.ha_token)
        try:
            yield
        finally:
            await app.state.ha.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    async def healthz() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.get("/kindle.png")
    async def kindle_png(request: Request) -> Response:
        if not is_authorized(request, settings.kindle_token):
            return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})

        battery = parse_battery(request.headers.get("x-kindle-battery"))
        if settings.dashboard is not None:
            png = await dashboard_png(settings, request.app.state.ha, battery)
            if png is None:
                return Response(status_code=503)
            return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})

        try:
            states = await request.app.state.ha.get_states(row.entity for row in settings.rows)
        except HAUnavailable:
            log.error("Home Assistant unreachable, answering 503")
            return Response(status_code=503)

        view = build_view(
            settings.title,
            settings.rows,
            states,
            settings.timezone,
            battery,
        )
        png = await run_in_threadpool(render, view)
        return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})

    return app
