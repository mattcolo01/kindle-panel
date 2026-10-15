"""Strings of the Home Tasks card, for the languages the gateway supports.

Copied from the _TRANSLATIONS table of home-tasks-card.js, Home Tasks v2.4.0
(https://github.com/L3t4l3s/home-tasks, MIT License, Copyright (c) 2026
L3t4l3s). Only the keys used by the read-only list view are here.

MONTHS are the short month names Intl.DateTimeFormat uses for
{day: "numeric", month: "short"} (checked with Node 22, ICU 77.1).
"""

import re

TRANSLATIONS = {
    "en": {
        "my_tasks": "My Tasks",
        "progress": "{0} of {1} done",
        "empty": "No tasks",
        "done_section_header": "Done",
        "due_today": "Today",
        "due_tomorrow": "Tomorrow",
        "due_yesterday": "Yesterday",
        "due_day_after_tomorrow": "In 2 days",
        "due_day_before_yesterday": "2 days ago",
        "pri_high": "High",
        "pri_medium": "Medium",
        "pri_low": "Low",
        "rec_short_h": "h",
        "rec_short_d": "d",
        "rec_short_w": "w",
        "rec_short_m": "mo",
        "rec_short_y": "y",
        "rec_hourly": "Hourly",
        "rec_daily": "Daily",
        "rec_weekly": "Weekly",
        "rec_monthly": "Monthly",
        "rec_yearly": "Yearly",
        "rec_wd_0": "Mon",
        "rec_wd_1": "Tue",
        "rec_wd_2": "Wed",
        "rec_wd_3": "Thu",
        "rec_wd_4": "Fri",
        "rec_wd_5": "Sat",
        "rec_wd_6": "Sun",
        "rec_dom_short": "th",
        "rec_last_short": "last",
        "rec_remaining": "{0} left",
        "assigned_unknown": "Unknown (%s)",
        "rem_at_due": "At due time",
        "rem_5m": "5 min before",
        "rem_15m": "15 min before",
        "rem_30m": "30 min before",
        "rem_1h": "1 hour before",
        "rem_2h": "2 hours before",
        "rem_1d": "1 day before",
        "rem_2d": "2 days before",
    },
    "it": {
        "my_tasks": "Le mie attività",
        "progress": "{0} di {1} completate",
        "empty": "Nessuna attività",
        "done_section_header": "Fatto",
        "due_today": "Oggi",
        "due_tomorrow": "Domani",
        "due_yesterday": "Ieri",
        "due_day_after_tomorrow": "Dopodomani",
        "due_day_before_yesterday": "L'altroieri",
        "pri_high": "Alta",
        "pri_medium": "Media",
        "pri_low": "Bassa",
        "rec_short_h": "h",
        "rec_short_d": "g",
        "rec_short_w": "s",
        "rec_short_m": "m",
        "rec_short_y": "a",
        "rec_hourly": "Oraria",
        "rec_daily": "Giornaliera",
        "rec_weekly": "Settimanale",
        "rec_monthly": "Mensile",
        "rec_yearly": "Annuale",
        "rec_wd_0": "Lun",
        "rec_wd_1": "Mar",
        "rec_wd_2": "Mer",
        "rec_wd_3": "Gio",
        "rec_wd_4": "Ven",
        "rec_wd_5": "Sab",
        "rec_wd_6": "Dom",
        "rec_dom_short": "º",
        "rec_last_short": "ultimo",
        "rec_remaining": "ancora {0}",
        "assigned_unknown": "Sconosciuto (%s)",
        "rem_at_due": "All’ora di scadenza",
        "rem_5m": "5 min. prima",
        "rem_15m": "15 min. prima",
        "rem_30m": "30 min. prima",
        "rem_1h": "1 ora prima",
        "rem_2h": "2 ore prima",
        "rem_1d": "1 giorno prima",
        "rem_2d": "2 giorni prima",
    },
}

LANGUAGES = tuple(TRANSLATIONS)

MONTHS = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "it": ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"),
}


def translate(language: str, key: str, *args: object) -> str:
    """Like the card's _t(): language, then English, then the key itself."""
    text = TRANSLATIONS.get(language, {}).get(key) or TRANSLATIONS["en"].get(key) or key
    if not args:
        return text
    return re.sub(r"\{(\d+)\}", lambda m: str(args[int(m[1])]) if int(m[1]) < len(args) else "", text)
