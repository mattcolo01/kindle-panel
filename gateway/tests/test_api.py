import io

import httpx
import pytest
from PIL import Image

from app.main import create_app
from conftest import HA_TOKEN, KINDLE_TOKEN


def test_healthz_is_public_and_says_only_ok(client, ha):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.text == "ok"
    assert not ha.calls


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": f"Bearer {KINDLE_TOKEN}x"},
        {"Authorization": f"Basic {KINDLE_TOKEN}"},
        {"Authorization": KINDLE_TOKEN},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer tökén".encode()},
    ],
)
def test_kindle_png_rejects_missing_or_wrong_token(client, ha, headers):
    response = client.get("/kindle.png", headers=headers)
    assert response.status_code == 401
    assert response.content == b""
    assert response.headers["www-authenticate"] == "Bearer"
    assert not ha.calls


def test_kindle_png_with_valid_token(client, ha, auth):
    response = client.get("/kindle.png", headers=auth)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_ha_is_called_with_ha_token_and_only_state_gets(client, ha, auth):
    client.get("/kindle.png", headers=auth)
    assert len(ha.calls) == 3
    for call in ha.calls:
        assert call.request.method == "GET"
        assert call.request.url.path.startswith("/api/states/")
        assert call.request.headers["authorization"] == f"Bearer {HA_TOKEN}"


def test_png_is_600x800_grayscale_without_alpha(client, auth):
    image = Image.open(io.BytesIO(client.get("/kindle.png", headers=auth).content))
    assert image.format == "PNG"
    assert image.size == (600, 800)
    assert image.mode == "L"
    assert "transparency" not in image.info


def test_same_data_gives_identical_bytes(client, auth):
    first = client.get("/kindle.png", headers=auth).content
    second = client.get("/kindle.png", headers=auth).content
    assert first == second


def test_changed_data_gives_different_bytes(client, ha, auth):
    first = client.get("/kindle.png", headers=auth).content
    ha.routes["sensor.umidita_soggiorno"].respond(
        json={"state": "46", "attributes": {}, "last_changed": "2026-10-12T15:43:00+00:00"}
    )
    assert client.get("/kindle.png", headers=auth).content != first


def test_battery_header_is_rounded_to_5_percent(client, auth):
    def png(battery):
        return client.get("/kindle.png", headers={**auth, "X-Kindle-Battery": battery}).content

    no_battery = client.get("/kindle.png", headers=auth).content
    assert png("84") == png("86") == png("85")
    assert png("84") != png("82")
    assert png("84") != no_battery
    # Invalid values are ignored
    assert png("abc") == png("101") == png("-5") == no_battery


def test_missing_entity_does_not_fail_the_image(client, ha, auth):
    ha.routes["weather.casa"].respond(404, json={"message": "Entity not found."})
    response = client.get("/kindle.png", headers=auth)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_entity_timeout_does_not_fail_the_image(client, ha, auth):
    ha.routes["weather.casa"].side_effect = httpx.ReadTimeout
    assert client.get("/kindle.png", headers=auth).status_code == 200


def test_ha_unreachable_returns_503(client, ha, auth):
    for route in ha.routes:
        route.side_effect = httpx.ConnectError
    response = client.get("/kindle.png", headers=auth)
    assert response.status_code == 503
    assert response.content == b""


def test_ha_rejecting_token_returns_503(client, ha, auth):
    for route in ha.routes:
        route.respond(401, text="401: Unauthorized")
    assert client.get("/kindle.png", headers=auth).status_code == 503


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
def test_no_docs_endpoints(client, path):
    assert client.get(path).status_code == 404


def test_missing_fonts_fail_at_startup(settings, monkeypatch):
    monkeypatch.setattr("app.render.FONT_BOLD", "/nonexistent/NoSuchFont.ttf")
    with pytest.raises(OSError):
        create_app(settings)
