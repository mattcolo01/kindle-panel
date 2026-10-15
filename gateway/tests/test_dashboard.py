import asyncio
from datetime import date

import pytest
import yaml

from app.dashboard import (
    DashboardError,
    Heading,
    TasksCard,
    TasksCardSpec,
    assigned_persons,
    build_view,
    fetch_dashboard,
    parse_dashboard,
)
from app.ha_ws import HACommandError, ha_websocket
from conftest import HA_TOKEN
from fake_ha import fake_ha

LIST_ID = "01M4RDRB51BS6VVQ450EDXCBXK"

# The dashboard of this installation, as given by its raw configuration editor
USER_DASHBOARD = yaml.safe_load(f"""
views:
  - type: sections
    sections:
      - type: grid
        cards:
          - type: heading
            heading: Nuova sezione
          - type: custom:home-tasks-card
            grid_options:
              columns: 48
              rows: auto
            columns:
              - list_id: {LIST_ID}
        column_span: 4
      - type: grid
        cards:
          - type: heading
            heading: Nuova sezione
""")


def test_user_dashboard():
    blocks = parse_dashboard(USER_DASHBOARD)
    assert blocks == [
        Heading("Nuova sezione", False),
        TasksCardSpec(None, (blocks[1].columns[0],), True),
        Heading("Nuova sezione", False),
    ]
    assert blocks[1].columns[0].list_id == LIST_ID
    assert blocks[1].columns[0].options == {"list_id": LIST_ID}


def test_only_the_first_view_is_used():
    config = {"views": [{"cards": [{"type": "heading", "heading": "A"}]},
                        {"cards": [{"type": "heading", "heading": "B"}]}]}
    assert parse_dashboard(config) == [Heading("A", False)]


def test_masonry_view_cards_and_heading_styles():
    config = {"views": [{"cards": [{"type": "heading", "heading": "T"},
                                   {"type": "heading", "heading": "S", "heading_style": "subtitle"},
                                   {"type": "heading"}]}]}
    assert parse_dashboard(config) == [Heading("T", False), Heading("S", True)]


def test_unsupported_cards_are_skipped_and_logged(caplog):
    config = {"views": [{"cards": [{"type": "entities", "entities": ["sensor.a"]}, {"type": "custom:foo"},
                                   "garbage", {"type": "heading", "heading": "H"}]}]}
    caplog.set_level("INFO")
    assert parse_dashboard(config) == [Heading("H", False)]
    assert "custom:foo, entities" in caplog.text


@pytest.mark.parametrize(
    "config",
    [
        {"strategy": {"type": "original-states"}},
        {"views": [{"strategy": {"type": "areas"}}]},
        {"views": []},
        {"views": "x"},
        {},
        [],
    ],
)
def test_dashboards_that_cannot_be_drawn(config):
    with pytest.raises(DashboardError):
        parse_dashboard(config)


def test_single_list_card_format_becomes_one_column():
    card = {"type": "custom:home-tasks-card", "list_id": LIST_ID, "title": "Spesa", "show_progress": False}
    [spec] = parse_dashboard({"views": [{"cards": [card]}]})
    assert spec.title is None  # one column: the title is the column's
    assert spec.columns[0].options == {"list_id": LIST_ID, "title": "Spesa", "show_progress": False}


def test_tasks_card_columns():
    card = {"type": "custom:home-tasks-card", "title": "Tutto", "columns": [
        {"list_id": LIST_ID, "type": "x"},
        {"entity_id": "todo.spesa"},  # external list: not supported
        {"list_id": "../../etc"},  # invalid
        {"list_id": "AAA"},
    ]}
    [spec] = parse_dashboard({"views": [{"cards": [card]}]})
    assert spec.title == "Tutto"
    assert [c.list_id for c in spec.columns] == [LIST_ID, "AAA"]
    assert spec.columns[0].options == {"list_id": LIST_ID}


def test_number_of_cards_is_bounded():
    config = {"views": [{"cards": [{"type": "heading", "heading": str(i)} for i in range(500)]}]}
    assert len(parse_dashboard(config)) == 50


def fetch(ha, url_path="dashboard-kindle"):
    async def go():
        async with ha_websocket(ha.url, HA_TOKEN) as ws:
            return await fetch_dashboard(ws, url_path)
    return asyncio.run(go())


def test_fetch_reads_dashboard_lists_and_tasks():
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = USER_DASHBOARD
        ha.lists = [{"id": LIST_ID, "name": "Casa", "task_count": 1}]
        ha.tasks[LIST_ID] = {"tasks": [{"id": "1", "title": "Latte", "completed": False, "sort_order": 0}],
                             "sections": [], "tag_catalog": []}
        data = fetch(ha)
    assert ha.received[1:] == [
        {"id": 1, "type": "lovelace/config", "url_path": "dashboard-kindle"},
        {"id": 2, "type": "home_tasks/get_lists"},
        {"id": 3, "type": "home_tasks/get_tasks", "list_id": LIST_ID},
    ]
    assert data.list_names == {LIST_ID: "Casa"}
    view = build_view(data, {}, "it", date(2026, 10, 15), 80)
    assert view.battery == 80
    assert [type(b) for b in view.blocks] == [Heading, TasksCard, Heading]
    column = view.blocks[1].columns[0]
    assert (column.title, column.progress) == ("Casa", "0 di 1 completate")
    assert [i.title for i in column.items] == ["Latte"]


def test_fetch_without_tasks_card_reads_only_the_dashboard():
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = {"views": [{"cards": [{"type": "heading", "heading": "H"}]}]}
        fetch(ha)
    assert ha.commands == ["auth", "lovelace/config"]


def test_fetch_each_list_once():
    card = {"type": "custom:home-tasks-card", "columns": [{"list_id": LIST_ID}, {"list_id": LIST_ID}]}
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = {"views": [{"cards": [card, card]}]}
        ha.lists = [{"id": LIST_ID, "name": "Casa"}]
        ha.tasks[LIST_ID] = {"tasks": [], "sections": []}
        fetch(ha)
    assert ha.commands == ["auth", "lovelace/config", "home_tasks/get_lists", "home_tasks/get_tasks"]


def test_card_without_list_shows_the_first_one():
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = {"views": [{"cards": [{"type": "custom:home-tasks-card"}]}]}
        ha.lists = [{"id": "SECOND", "name": "B"}, {"id": "OTHER", "name": "C"}]
        ha.tasks["SECOND"] = {"tasks": [], "sections": []}
        data = fetch(ha)
    assert data.blocks[0].columns[0].list_id == "SECOND"


def test_missing_list_is_an_error():
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = USER_DASHBOARD
        ha.lists = []
        with pytest.raises(DashboardError, match=LIST_ID):
            fetch(ha)
    assert "home_tasks/get_tasks" not in ha.commands


def test_home_tasks_not_installed_is_a_command_error():
    with fake_ha(HA_TOKEN) as ha:
        ha.dashboards["dashboard-kindle"] = USER_DASHBOARD
        ha.result = lambda message: (
            {"success": True, "result": USER_DASHBOARD} if message["type"] == "lovelace/config"
            else {"success": False, "error": {"code": "unknown_command", "message": "Unknown command."}}
        )
        with pytest.raises(HACommandError) as e:
            fetch(ha)
    assert e.value.code == "unknown_command"


def test_assigned_persons_are_valid_person_entities():
    from app.dashboard import DashboardData

    tasks = [{"assigned_person": p} for p in
             ["person.anna", "person.anna", "sensor.x", "person.../api", "person.Bob", None, 3, "person.bob"]]
    data = DashboardData((), {}, {LIST_ID: (tasks, [])})
    assert assigned_persons(data) == ["person.anna", "person.bob"]
