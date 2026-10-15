"""What custom:home-tasks-card shows for one column, without interaction.

Ported from home-tasks-card.js of Home Tasks v2.4.0
(https://github.com/L3t4l3s/home-tasks, MIT License, Copyright (c) 2026
L3t4l3s); the card's function names are given next to each part. Inputs,
buttons, filter chips and images are left out: the Kindle cannot use them.

One deliberate difference: for a task due today at a given time the card
counts down ("Tra 2 h 15 min"), which would change the image at every wake
and force a screen refresh. The gateway shows the time instead ("Oggi 18:00").
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from functools import cmp_to_key

from .i18n import MONTHS, translate

MAX_TEXT = 300  # characters kept of any text coming from HA
MAX_TASKS = 500  # tasks considered per list

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
ANNIVERSARY_RE = re.compile(r"^\d{2}-\d{2}$")

PERSON_MODES = ("off", "picture", "name", "both")
# REMINDER_OFFSETS: minutes before the due time -> label key
REMINDER_OFFSETS = {0: "rem_at_due", 5: "rem_5m", 15: "rem_15m", 30: "rem_30m",
                    60: "rem_1h", 120: "rem_2h", 1440: "rem_1d", 2880: "rem_2d"}


@dataclass(frozen=True)
class Badge:
    text: str
    style: str = "plain"  # plain | strong | inverted
    icon: str | None = None  # person | alarm
    avatar: str | None = None  # initials, drawn in a circle


@dataclass(frozen=True)
class TaskRow:
    title: str
    completed: bool
    badges: tuple[Badge, ...]


@dataclass(frozen=True)
class GroupHeader:
    name: str
    count: int  # 0 = not shown


@dataclass(frozen=True)
class TaskColumn:
    title: str | None
    progress: str | None
    items: tuple[GroupHeader | TaskRow, ...]
    empty: str | None  # shown instead of the items when there are none


def text(value: object) -> str:
    return value[:MAX_TEXT] if isinstance(value, str) else ""


def is_true(col: dict, key: str) -> bool:
    """JS `col.key === true`."""
    return col.get(key) is True


def not_false(col: dict, key: str) -> bool:
    """JS `col.key !== false`: missing means on."""
    return col.get(key) is not False


def parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def is_overdue(task: dict, today: date) -> bool:
    due = parse_date(task.get("due_date"))
    return due is not None and due < today


def locale_key(value: str) -> str:
    """Rough stand-in for localeCompare(..., {sensitivity: "base"})."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def compare(a: object, b: object) -> int:
    return (a > b) - (a < b)


def number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def due_key(task: dict) -> str | None:
    if not task.get("due_date"):
        return None
    return f"{task['due_date']}T{task.get('due_time') or '00:00'}"


def sort_comparator(sort_by: str):
    """_buildSortComparator"""
    if sort_by == "due":
        def cmp(a, b):
            da, db = due_key(a), due_key(b)
            if da and db:
                return compare(da, db)
            return -1 if da else 1 if db else 0
    elif sort_by == "priority":
        def cmp(a, b):
            return compare(number(b.get("priority")) or 0, number(a.get("priority")) or 0)
    elif sort_by == "title":
        def cmp(a, b):
            return compare(locale_key(text(a.get("title"))), locale_key(text(b.get("title"))))
    elif sort_by == "person":
        def cmp(a, b):
            pa = text(a.get("assigned_person")) or "￿"
            pb = text(b.get("assigned_person")) or "￿"
            return compare(locale_key(pa), locale_key(pb)) or compare(pa, pb)
    else:  # manual
        def cmp(a, b):
            oa, ob = number(a.get("sort_order")), number(b.get("sort_order"))
            return 0 if oa is None or ob is None else compare(oa, ob)
    return cmp


def within_days(task: dict, today: date, days: int) -> bool:
    due = parse_date(task.get("due_date"))
    return due is not None and 0 <= (due - today).days <= days


def filtered_tasks(tasks: list[dict], col: dict, today: date) -> list[dict]:
    """_preFilteredTasks + _filteredTasks, with the column's default filter
    and sort (setConfig): the Kindle never changes them."""
    filters = col.get("filters") if isinstance(col.get("filters"), dict) else {}
    assignees = filters.get("assignees")
    if isinstance(assignees, list) and assignees:
        tasks = [t for t in tasks if t.get("assigned_person") in assignees]
    labels = filters.get("labels")
    if isinstance(labels, list) and labels:
        tasks = [t for t in tasks if isinstance(t.get("tags"), list) and any(tag in labels for tag in t["tags"])]

    mode = col.get("default_filter") or "all"
    if mode == "due_soon" and col.get("show_due_soon_filter") is not True:
        mode = "all"
    if mode == "open":
        tasks = [t for t in tasks if not t.get("completed")]
    elif mode == "done":
        tasks = [t for t in tasks if t.get("completed")]
    elif mode == "due_soon":
        days = col.get("due_soon_days")
        days = days if isinstance(days, int) and not isinstance(days, bool) else 7
        hide_overdue = is_true(col, "hide_overdue")
        tasks = [
            t for t in tasks
            if not t.get("completed") and t.get("due_date")
            and ((not hide_overdue and is_overdue(t, today)) or within_days(t, today, days))
        ]

    cmp = sort_comparator(col.get("default_sort") or "manual")
    overdue_first = is_true(col, "overdue_first")

    def overdue(t: dict) -> bool:
        return overdue_first and not t.get("completed") and is_overdue(t, today)

    def full_cmp(a: dict, b: dict) -> int:
        if bool(a.get("completed")) != bool(b.get("completed")):
            return 1 if a.get("completed") else -1
        oa, ob = overdue(a), overdue(b)
        if oa != ob:
            return -1 if oa else 1
        if oa:
            result = compare(due_key(a), due_key(b))
            if result:
                return result
        return cmp(a, b)

    return sorted(tasks, key=cmp_to_key(full_cmp))


def format_due(task: dict, today: date, language: str) -> str:
    """_formatDueDate, except for the time of day (see the module docstring)."""
    due = parse_date(task.get("due_date"))
    if due is None:
        return text(task.get("due_date"))
    diff = (due - today).days
    if -2 <= diff <= 2:
        key = {-2: "due_day_before_yesterday", -1: "due_yesterday", 0: "due_today",
               1: "due_tomorrow", 2: "due_day_after_tomorrow"}[diff]
        label = translate(language, key)
        due_time = task.get("due_time")
        if diff == 0 and isinstance(due_time, str) and TIME_RE.match(due_time):
            label = f"{label} {due_time}"
        return label
    month = MONTHS.get(language, MONTHS["en"])[due.month - 1]
    if language == "en":
        label = f"{month} {due.day}"
        return f"{label}, {due.year % 100:02d}" if due.year != today.year else label
    label = f"{due.day} {month}"
    return f"{label} {due.year % 100:02d}" if due.year != today.year else label


def weekday_labels(task: dict, language: str) -> str:
    days = task.get("recurrence_weekdays")
    return " ".join(translate(language, f"rec_wd_{d}") for d in days)


def recurrence_label(task: dict, language: str) -> str | None:
    """_buildRecurrenceBadge"""
    def t(key: str, *args: object) -> str:
        return translate(language, key, *args)

    unit = task.get("recurrence_unit")
    val = task.get("recurrence_value") or 1
    units = {"hours": t("rec_short_h"), "days": t("rec_short_d"), "weeks": t("rec_short_w"),
             "months": t("rec_short_m"), "years": t("rec_short_y")}
    singles = {"hours": t("rec_hourly"), "days": t("rec_daily"), "weeks": t("rec_weekly"),
               "months": t("rec_monthly"), "years": t("rec_yearly")}
    weekdays = task.get("recurrence_weekdays")
    has_weekdays = isinstance(weekdays, list) and len(weekdays) > 0
    pattern = task.get("recurrence_month_pattern")
    dom = task.get("recurrence_day_of_month")
    nth = task.get("recurrence_nth_week")
    anniversary = task.get("recurrence_anniversary")

    label = None
    if task.get("recurrence_type") == "weekdays" and has_weekdays:
        label = weekday_labels(task, language)
    elif unit == "weeks" and has_weekdays:
        days = weekday_labels(task, language)
        label = days if val == 1 else f"{val} {units['weeks']} {days}"
    elif unit == "months" and pattern == "day_of_month" and dom is not None:
        day_part = t("rec_last_short") if dom == "last" else f"{dom}{t('rec_dom_short')}"
        label = day_part if val == 1 else f"{day_part} · {val} {units['months']}"
    elif unit == "months" and pattern == "nth_weekday" and nth is not None and has_weekdays:
        nth_label = t("rec_last_short") if nth == "last" else f"{nth}."
        head = f"{nth_label} {t(f'rec_wd_{weekdays[0]}')}"
        label = head if val == 1 else f"{head} · {val} {units['months']}"
    elif unit == "years" and isinstance(anniversary, str) and ANNIVERSARY_RE.match(anniversary):
        head = f"{int(anniversary[3:5])}.{int(anniversary[0:2])}."
        label = head if val == 1 else f"{head} · {val} {units['years']}"
    elif unit:
        label = singles.get(unit) if val == 1 else f"{val} {units.get(unit, unit)}"
    if not label:
        label = text(task.get("_todoist_recurrence_string")) or None
    if not label:
        return None
    label = "↻ " + text(label)
    if task.get("recurrence_end_type") == "count" and task.get("recurrence_remaining_count") is not None:
        label += " · " + t("rec_remaining", task["recurrence_remaining_count"])
    return label


def person_mode(col: dict) -> str:
    """_personMode(colIdx, "badge")"""
    chosen = col.get("person_badge")
    if chosen in PERSON_MODES:
        return chosen
    picture = is_true(col, "show_person_avatar")
    if not not_false(col, "badge_person"):
        return "picture" if picture else "off"
    return "both" if picture else "name"


def initials(name: str) -> str:
    """_personInitials"""
    letters = [next((c for c in word if c.isalnum()), "") for word in name.strip().split()]
    letters = [c for c in letters if c]
    if not letters:
        return "?"
    last = letters[-1] if len(letters) > 1 else ""
    return (letters[0] + last).upper()


def person_badge(task: dict, mode: str, names: dict[str, str], language: str) -> Badge:
    """_buildAssignedPersonBadge. Pictures are never fetched: the card's own
    fallback, the initials, is drawn instead."""
    person = text(task.get("assigned_person"))
    if person and person in names:
        name = names[person]
    elif task.get("assigned_name"):
        name = translate(language, "assigned_unknown").replace("%s", text(task["assigned_name"]))
    else:
        name = person
    if mode == "picture":
        return Badge("", avatar=initials(name))
    if mode == "both":
        return Badge(name, avatar=initials(name))
    return Badge(name, icon="person")


def reminder_text(reminders: list, language: str) -> str:
    """_buildReminderBadge"""
    if len(reminders) == 1:
        offset = reminders[0]
        key = REMINDER_OFFSETS.get(offset) if number(offset) is not None else None
        return translate(language, key) if key else f"{offset} min"
    return str(len(reminders))


def task_badges(task: dict, col: dict, names: dict[str, str], language: str, today: date) -> tuple[Badge, ...]:
    """_buildTaskMetaBadges"""
    badges = []
    priority = number(task.get("priority"))
    if priority and not_false(col, "show_priority") and not_false(col, "badge_priority"):
        key = {1: "pri_low", 2: "pri_medium", 3: "pri_high"}.get(priority)
        if key:
            badges.append(Badge(translate(language, key), {3: "inverted", 2: "strong"}.get(priority, "plain")))

    sub_items = task.get("sub_items")
    show_sub = col.get("show_sub_tasks")
    if show_sub is None:
        show_sub = col.get("show_sub_items")
    if isinstance(sub_items, list) and sub_items and show_sub is not False and not_false(col, "badge_progress"):
        done = sum(1 for s in sub_items if isinstance(s, dict) and s.get("completed"))
        badges.append(Badge(f"{done}/{len(sub_items)}"))

    if task.get("due_date") and not_false(col, "show_due_date") and not_false(col, "badge_due"):
        due = parse_date(task.get("due_date"))
        style = "inverted" if is_overdue(task, today) else "strong" if due == today else "plain"
        badges.append(Badge(format_due(task, today, language), style))

    if task.get("recurrence_enabled") and not_false(col, "show_recurrence") and not_false(col, "badge_recurrence"):
        label = recurrence_label(task, language)
        if label:
            badges.append(Badge(label))

    mode = person_mode(col)
    if (task.get("assigned_person") or task.get("assigned_name")) and not_false(col, "show_assigned_person") \
            and mode != "off":
        badges.append(person_badge(task, mode, names, language))

    tags = task.get("tags")
    if isinstance(tags, list) and tags and not_false(col, "show_tags") and not_false(col, "badge_tags"):
        badges.extend(Badge("#" + text(tag)) for tag in tags)

    reminders = task.get("reminders")
    if isinstance(reminders, list) and reminders and not_false(col, "show_reminders") \
            and not_false(col, "badge_reminders"):
        badges.append(Badge(reminder_text(reminders, language), icon="alarm"))
    return tuple(badges)


def column_view(
    col: dict,
    list_name: str | None,
    tasks: list[dict],
    sections: list[dict],
    names: dict[str, str],
    language: str,
    today: date,
) -> TaskColumn:
    """_buildColumn: header (_buildColumnHeader) and list (_buildColumnTaskList).
    Collapsed sections live in the browser's localStorage: here all are open."""
    tasks = tasks[:MAX_TASKS]
    title = None
    if not_false(col, "show_title"):
        title = text(col.get("title")) or list_name or translate(language, "my_tasks")
    progress = None
    if not_false(col, "show_progress"):
        progress = translate(language, "progress", sum(1 for t in tasks if t.get("completed")), len(tasks))

    def row(task: dict) -> TaskRow:
        return TaskRow(text(task.get("title")), bool(task.get("completed")),
                       task_badges(task, col, names, language, today))

    visible = filtered_tasks(tasks, col, today)
    if not visible:
        return TaskColumn(title, progress, (), translate(language, "empty"))

    done_name = translate(language, "done_section_header")
    open_tasks = [t for t in visible if not t.get("completed")]
    done_tasks = [t for t in visible if t.get("completed")]
    ordered_sections = sorted(sections, key=lambda s: number(s.get("sort_order")) or 0)
    items: list[GroupHeader | TaskRow] = []
    if not ordered_sections:
        items.extend(row(t) for t in open_tasks)
        if done_tasks and open_tasks:
            items.append(GroupHeader(done_name, 0))
        items.extend(row(t) for t in done_tasks)
    else:
        known = {s.get("id") for s in ordered_sections}
        items.extend(row(t) for t in open_tasks if not t.get("section_id") or t.get("section_id") not in known)
        for section in ordered_sections:
            inside = [t for t in open_tasks if t.get("section_id") and t.get("section_id") == section.get("id")]
            items.append(GroupHeader(text(section.get("name")), len(inside)))
            items.extend(row(t) for t in inside)
        if done_tasks:
            items.append(GroupHeader(done_name, len(done_tasks)))
            items.extend(row(t) for t in done_tasks)
    return TaskColumn(title, progress, tuple(items), None)
