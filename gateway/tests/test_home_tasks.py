"""The expected values are what home-tasks-card.js v2.4.0 itself shows for the
same input: they were produced by running the card in jsdom with the date
frozen at 2026-10-15 (Europe/Rome). Badges are written as their text in the
card's DOM, so the drawn icons appear as the card's emoji."""

from datetime import date

import pytest

from app.home_tasks import Badge, GroupHeader, column_view, format_due, initials

TODAY = date(2026, 10, 15)
NAMES = {"person.anna": "Anna Bianchi"}


def task(**fields) -> dict:
    return {"id": "t", "title": "Task", "completed": False, "sort_order": 0, "sub_items": [], "tags": [],
            "reminders": [], **fields}


def badge_text(badge: Badge) -> str:
    if badge.icon == "person":
        return "\U0001F464 " + badge.text
    if badge.icon == "alarm":
        return "⏰ " + badge.text
    return (badge.avatar or "") + badge.text


def shown(tasks, column=None, sections=(), language="it", list_name="Casa") -> dict:
    col = column_view({"list_id": "L1", **(column or {})}, list_name, tasks, list(sections), NAMES, language, TODAY)
    items = []
    for item in col.items:
        if isinstance(item, GroupHeader):
            items.append({"group": item.name, "count": item.count})
        else:
            items.append({"title": item.title, "completed": item.completed,
                          "badges": [badge_text(b) for b in item.badges]})
    return {"title": col.title, "progress": col.progress, "items": items, "empty": col.empty}


def badges(result: dict) -> list[list[str]]:
    return [item["badges"] for item in result["items"]]


def test_due_labels_italian():
    dates = ["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18",
             "2026-04-06", "2027-04-06"]
    result = shown([task(id=str(i), sort_order=i, title=d, due_date=d) for i, d in enumerate(dates)])
    assert result["progress"] == "0 di 8 completate"
    assert badges(result) == [["L'altroieri"], ["Ieri"], ["Oggi"], ["Domani"], ["Dopodomani"], ["18 ott"],
                              ["6 apr"], ["6 apr 27"]]


def test_due_labels_english():
    dates = ["2026-10-13", "2026-10-17", "2026-04-06", "2027-09-16"]
    result = shown([task(id=str(i), sort_order=i, due_date=d) for i, d in enumerate(dates)], language="en")
    assert result["progress"] == "0 of 4 done"
    assert badges(result) == [["2 days ago"], ["In 2 days"], ["Apr 6"], ["Sep 16, 27"]]


def test_due_today_with_time_shows_the_time_not_a_countdown():
    # The card says "Tra 8 h 0 min" here, a text that changes every minute:
    # the Kindle would redraw at every wake.
    assert format_due(task(due_date="2026-10-15", due_time="18:00"), TODAY, "it") == "Oggi 18:00"
    assert format_due(task(due_date="2026-10-15", due_time="18:00"), TODAY, "en") == "Today 18:00"
    # Other days: the card shows no time, neither does the gateway
    assert format_due(task(due_date="2026-10-16", due_time="18:00"), TODAY, "it") == "Domani"


def test_recurrence_labels():
    tasks = [
        task(id="a", sort_order=0, recurrence_enabled=True, recurrence_unit="weeks", recurrence_weekdays=[0, 3]),
        task(id="b", sort_order=1, recurrence_enabled=True, recurrence_unit="weeks", recurrence_value=2,
             recurrence_weekdays=[4]),
        task(id="c", sort_order=2, recurrence_enabled=True, recurrence_unit="months",
             recurrence_month_pattern="day_of_month", recurrence_day_of_month=15),
        task(id="d", sort_order=3, recurrence_enabled=True, recurrence_unit="months",
             recurrence_month_pattern="nth_weekday", recurrence_nth_week="last", recurrence_weekdays=[4]),
        task(id="e", sort_order=4, recurrence_enabled=True, recurrence_unit="years",
             recurrence_anniversary="12-25", recurrence_value=2),
        task(id="f", sort_order=5, recurrence_enabled=True, recurrence_unit="days", recurrence_value=3,
             recurrence_end_type="count", recurrence_remaining_count=4),
        task(id="g", sort_order=6, recurrence_enabled=True, recurrence_unit="hours"),
    ]
    assert badges(shown(tasks)) == [["↻ Lun Gio"], ["↻ 2 s Ven"], ["↻ 15º"], ["↻ ultimo Ven"], ["↻ 25.12. · 2 a"],
                                    ["↻ 3 g · ancora 4"], ["↻ Oraria"]]


def test_priority_progress_person_tags_reminders():
    tasks = [
        task(id="a", sort_order=0, priority=3, assigned_person="person.anna", tags=["casa", "spesa"],
             reminders=[60], sub_items=[{"id": "1", "completed": True}, {"id": "2", "completed": False}]),
        task(id="b", sort_order=1, priority=1, assigned_name="Tizio", reminders=[5, 60]),
        task(id="c", sort_order=2, assigned_person="person.ghost", reminders=[90]),
    ]
    assert badges(shown(tasks)) == [
        ["Alta", "1/2", "👤 Anna Bianchi", "#casa", "#spesa", "⏰ 1 ora prima"],
        ["Bassa", "👤 Sconosciuto (Tizio)", "⏰ 2"],
        ["👤 person.ghost", "⏰ 90 min"],
    ]


def test_person_avatar_modes():
    one = [task(assigned_person="person.anna")]
    assert badges(shown(one, {"person_badge": "both"})) == [["ABAnna Bianchi"]]
    assert badges(shown(one, {"person_badge": "picture"})) == [["AB"]]
    assert badges(shown(one, {"person_badge": "off"})) == [[]]


def test_sections_unsorted_first_done_last():
    tasks = [
        task(id="1", title="Libero", sort_order=0),
        task(id="2", title="In cucina", sort_order=1, section_id="s1"),
        task(id="3", title="Fatto", sort_order=2, completed=True, section_id="s1"),
        task(id="4", title="Orfano", sort_order=3, section_id="gone"),
    ]
    sections = [{"id": "s2", "name": "Bagno", "sort_order": 1}, {"id": "s1", "name": "Cucina", "sort_order": 0}]
    assert shown(tasks, sections=sections) == {
        "title": "Casa",
        "progress": "1 di 4 completate",
        "items": [
            {"title": "Libero", "completed": False, "badges": []},
            {"title": "Orfano", "completed": False, "badges": []},
            {"group": "Cucina", "count": 1},
            {"title": "In cucina", "completed": False, "badges": []},
            {"group": "Bagno", "count": 0},
            {"group": "Fatto", "count": 1},
            {"title": "Fatto", "completed": True, "badges": []},
        ],
        "empty": None,
    }


def test_flat_list_with_done_header():
    tasks = [task(id="1", title="Aperto"), task(id="2", title="Chiuso", completed=True, sort_order=1)]
    assert shown(tasks)["items"] == [
        {"title": "Aperto", "completed": False, "badges": []},
        {"group": "Fatto", "count": 0},
        {"title": "Chiuso", "completed": True, "badges": []},
    ]


def test_empty_list_without_name():
    assert shown([], list_name=None) == {"title": "Le mie attività", "progress": "0 di 0 completate", "items": [],
                                         "empty": "Nessuna attività"}


def test_header_options():
    result = shown([task()], {"show_title": False, "show_progress": False})
    assert (result["title"], result["progress"]) == (None, None)
    assert shown([task()], {"title": "Mio"})["title"] == "Mio"


@pytest.mark.parametrize(
    "name, expected",
    [("Anna Bianchi", "AB"), ("anna", "A"), ("Unknown (Alice)", "UA"), ("", "?"), ("  ", "?")],
)
def test_initials(name, expected):
    assert initials(name) == expected


def test_long_titles_and_many_tasks_are_bounded():
    many = [task(id=str(i), sort_order=i, title="x" * 5000) for i in range(2000)]
    result = shown(many)
    assert len(result["items"]) == 500
    assert all(len(item["title"]) == 300 for item in result["items"])


@pytest.mark.parametrize("priority", [[3], {"a": 1}, "x", True, 7])
def test_unexpected_priority_values_show_no_badge(priority):
    assert badges(shown([task(priority=priority)])) == [[]]
