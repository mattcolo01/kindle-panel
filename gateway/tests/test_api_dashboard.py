import dataclasses
import io

import pytest
import respx
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from conftest import HA_TOKEN
from fake_ha import fake_ha
from test_dashboard import LIST_ID, USER_DASHBOARD

TASKS = [
    {"id": "1", "title": "Comprare il latte", "completed": False, "sort_order": 0, "assigned_person": "person.anna",
     "due_date": "2026-10-20", "tags": ["spesa"], "notes": "segreto", "history": []},
    {"id": "2", "title": "Annaffiare", "completed": True, "sort_order": 1},
]


@pytest.fixture
def ha():
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = USER_DASHBOARD
        ha.lists = [{"id": LIST_ID, "name": "Casa", "task_count": 2}]
        ha.tasks[LIST_ID] = {"tasks": [dict(t) for t in TASKS], "sections": [], "tag_catalog": []}
        yield ha


@pytest.fixture
def rest(ha):
    """HA REST API, only for the names of assigned persons."""
    with respx.mock(base_url=ha.url, assert_all_called=False) as mock:
        mock.get("/api/states/person.anna", name="anna").respond(
            json={"entity_id": "person.anna", "state": "home", "attributes": {"friendly_name": "Anna"}}
        )
        yield mock


@pytest.fixture
def dashboard_settings(settings, ha):
    return dataclasses.replace(settings, ha_url=ha.url, rows=(), dashboard="dashboard-kindle")


@pytest.fixture
def client(dashboard_settings, rest):
    with TestClient(create_app(dashboard_settings)) as c:
        yield c


def test_unauthorized_does_not_contact_ha(client, ha, rest):
    assert client.get("/kindle.png").status_code == 401
    assert ha.connections == 0
    assert not rest.calls


def test_dashboard_png(client, auth):
    response = client.get("/kindle.png", headers={**auth, "X-Kindle-Battery": "84"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    image = Image.open(io.BytesIO(response.content))
    assert (image.format, image.size, image.mode) == ("PNG", (600, 800), "L")
    assert "transparency" not in image.info


def test_ha_sees_only_reads_with_the_ha_token(client, ha, rest, auth):
    client.get("/kindle.png", headers=auth)
    assert ha.received[0] == {"type": "auth", "access_token": HA_TOKEN}
    assert ha.commands == ["auth", "lovelace/config", "home_tasks/get_lists", "home_tasks/get_tasks"]
    assert [c.request.url.path for c in rest.calls] == ["/api/states/person.anna"]
    assert rest.calls[0].request.method == "GET"
    assert rest.calls[0].request.headers["authorization"] == f"Bearer {HA_TOKEN}"


def test_same_data_gives_identical_bytes(client, auth):
    assert client.get("/kindle.png", headers=auth).content == client.get("/kindle.png", headers=auth).content


def test_changed_task_gives_different_bytes(client, ha, auth):
    first = client.get("/kindle.png", headers=auth).content
    ha.tasks[LIST_ID]["tasks"][0]["completed"] = True
    assert client.get("/kindle.png", headers=auth).content != first


def test_fields_not_shown_do_not_change_the_image(client, ha, auth):
    """Notes and history are not drawn: editing them must not wake the screen."""
    first = client.get("/kindle.png", headers=auth).content
    ha.tasks[LIST_ID]["tasks"][0]["notes"] = "altro"
    ha.tasks[LIST_ID]["tasks"][0]["history"] = [{"ts": "2026-10-15T10:00:00+00:00", "action": "updated"}]
    assert client.get("/kindle.png", headers=auth).content == first


def test_person_name_lookup_failure_still_draws(client, rest, auth):
    rest.routes["anna"].respond(500)
    assert client.get("/kindle.png", headers=auth).status_code == 200


def test_missing_dashboard_returns_503(client, ha, auth, caplog):
    ha.dashboards.clear()
    response = client.get("/kindle.png", headers=auth)
    assert response.status_code == 503
    assert response.content == b""
    assert "dashboard-kindle" in caplog.text and "not found" in caplog.text


def test_strategy_dashboard_returns_503(client, ha, auth, caplog):
    ha.dashboards["dashboard-kindle"] = {"strategy": {"type": "original-states"}}
    assert client.get("/kindle.png", headers=auth).status_code == 503
    assert "strategy" in caplog.text


def test_missing_list_returns_503(client, ha, auth, caplog):
    ha.lists = []
    assert client.get("/kindle.png", headers=auth).status_code == 503
    assert LIST_ID in caplog.text


def test_rejected_ha_token_returns_503(dashboard_settings, rest, auth):
    settings = dataclasses.replace(dashboard_settings, ha_token="revoked")
    with TestClient(create_app(settings)) as client:
        assert client.get("/kindle.png", headers=auth).status_code == 503


def test_ha_unreachable_returns_503(settings, auth):
    with fake_ha(HA_TOKEN) as ha:
        url = ha.url
    settings = dataclasses.replace(settings, ha_url=url, rows=(), dashboard="dashboard-kindle")
    with TestClient(create_app(settings)) as client:
        assert client.get("/kindle.png", headers=auth).status_code == 503
