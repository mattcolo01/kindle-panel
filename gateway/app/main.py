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
from .arp import HAEndpointResolver
from .dashboard import DashboardError, assigned_persons, fetch_dashboard, person_names
from .dashboard import build_view as build_dashboard_view
from .ha import HAClient, HAUnavailable
from .ha_ws import TIMEOUT_SECONDS, HACommandError, ha_websocket
from .render import build_view, check_fonts, parse_battery, render
from .render_dashboard import render_dashboard

log = logging.getLogger(__name__)
APP_LOGGER = "app"


def setup_logging() -> None:
    """uvicorn configures only its own loggers: without a handler here the
    app's INFO messages (e.g. skipped cards) would never reach the log."""
    logger = logging.getLogger(APP_LOGGER)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def is_authorized(request: Request, token: str) -> bool:
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(credentials.strip().encode(), token.encode())


async def dashboard_png(settings: Settings, ha: HAClient, ha_url: str, battery: int | None) -> bytes:
    """Render a dashboard, raising the HA error to let the caller recover."""
    async with asyncio.timeout(TIMEOUT_SECONDS):
        async with ha_websocket(ha_url, settings.ha_token) as ws:
            data = await fetch_dashboard(ws, settings.dashboard)

    persons = assigned_persons(data)
    names: dict[str, str] = {}
    if persons:
        try:
            names = person_names(await ha.get_states(persons))
        except HAUnavailable:
            log.warning("Could not read the names of assigned persons")
    view = build_dashboard_view(data, names, settings.language, datetime.now(settings.timezone).date(), battery)
    return await run_in_threadpool(render_dashboard, view)


async def recover_ha(request: Request, settings: Settings) -> bool:
    """ARP-rescan HA once after an unavailable error and replace its client."""
    url = await request.app.state.ha_resolver.recover()
    if url is None:
        return False
    old_ha = request.app.state.ha
    request.app.state.ha = HAClient(url, settings.ha_token)
    await old_ha.aclose()
    return True


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = load_settings()
    setup_logging()
    check_fonts()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ha = HAClient(settings.ha_url, settings.ha_token)
        app.state.ha_resolver = HAEndpointResolver(settings.ha_url, settings.ha_mac, settings.ha_arp_interface)
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
            try:
                png = await dashboard_png(settings, request.app.state.ha, request.app.state.ha_resolver.url, battery)
            except HACommandError as e:
                if e.command == "lovelace/config" and e.code == "config_not_found":
                    log.error("Dashboard %r not found, or never edited (auto-generated): %s", settings.dashboard, e.message)
                else:
                    log.error("Home Assistant refused %s: %s %s", e.command, e.code, e.message)
                return Response(status_code=503)
            except DashboardError as e:
                log.error("Dashboard %r cannot be drawn: %s", settings.dashboard, e)
                return Response(status_code=503)
            except (HAUnavailable, TimeoutError) as e:
                if not await recover_ha(request, settings):
                    log.error("Home Assistant WebSocket unavailable: %s", str(e) or type(e).__name__)
                    return Response(status_code=503)
                try:
                    png = await dashboard_png(settings, request.app.state.ha, request.app.state.ha_resolver.url, battery)
                except (HACommandError, DashboardError, HAUnavailable, TimeoutError) as retry_error:
                    log.error("Home Assistant is still unavailable after ARP recovery: %s", retry_error)
                    return Response(status_code=503)
            return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})

        try:
            states = await request.app.state.ha.get_states(row.entity for row in settings.rows)
        except HAUnavailable:
            if not await recover_ha(request, settings):
                log.error("Home Assistant unreachable, answering 503")
                return Response(status_code=503)
            try:
                states = await request.app.state.ha.get_states(row.entity for row in settings.rows)
            except HAUnavailable:
                log.error("Home Assistant is still unreachable after ARP recovery")
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
