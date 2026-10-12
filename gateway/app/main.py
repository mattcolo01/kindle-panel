"""kindle-gateway: serves the dashboard PNG to the Kindle.

Endpoints:
  GET /kindle.png  Bearer KINDLE_TOKEN required; optional X-Kindle-Battery.
  GET /healthz     unauthenticated, returns "ok" and nothing else.

Run with: uvicorn --factory app.main:create_app
"""

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from starlette.concurrency import run_in_threadpool

from .config import Settings, load_settings
from .ha import HAClient, HAUnavailable
from .render import build_view, check_fonts, parse_battery, render

log = logging.getLogger(__name__)


def is_authorized(request: Request, token: str) -> bool:
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(credentials.strip().encode(), token.encode())


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
            parse_battery(request.headers.get("x-kindle-battery")),
        )
        png = await run_in_threadpool(render, view)
        return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})

    return app
