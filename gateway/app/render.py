"""Draw the dashboard PNG (600x800, 8-bit grayscale) with Pillow.

The output must depend only on the data, so that the Kindle can skip the
screen refresh when nothing changed: no rendering time, no randomness.
"""

import io
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from .config import Row

WIDTH, HEIGHT = 600, 800
MARGIN = 30
WHITE, BLACK = 255, 0

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_REGULAR = f"{FONT_DIR}/DejaVuSans.ttf"
FONT_BOLD = f"{FONT_DIR}/DejaVuSans-Bold.ttf"

MISSING = "—"
NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")


@dataclass(frozen=True)
class View:
    title: str
    rows: tuple[tuple[str, str], ...]  # (label, value)
    data_time: str | None  # "HH:MM"
    battery: int | None  # percent, multiple of 5


def format_number(value: object) -> str | None:
    """Round to 1 decimal (half up); None if value is not a finite number."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    text = str(value)
    if not NUMBER_RE.match(text):
        return None
    try:
        rounded = Decimal(text).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    if rounded == 0:
        rounded = abs(rounded)  # no "-0.0"
    return format(rounded, "f")


def with_unit(value: str, unit: object) -> str:
    return f"{value} {unit}" if isinstance(unit, str) and unit else value


def format_state(entity_id: str, state: dict | None) -> str:
    if state is None or state["state"] in ("unavailable", "unknown"):
        return MISSING
    raw = state["state"]
    attributes = state.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}

    if entity_id.startswith("weather."):
        temperature = format_number(attributes.get("temperature"))
        if temperature is None:
            return raw
        return f"{raw}, {with_unit(temperature, attributes.get('temperature_unit'))}"

    number = format_number(raw)
    return with_unit(raw if number is None else number, attributes.get("unit_of_measurement"))


def data_time(states: list[dict | None], timezone: ZoneInfo) -> str | None:
    """HH:MM of the most recent last_changed among the entities."""
    latest = None
    for state in states:
        if state is None or not isinstance(state.get("last_changed"), str):
            continue
        try:
            changed = datetime.fromisoformat(state["last_changed"])
        except ValueError:
            continue
        if changed.tzinfo is None:
            continue
        if latest is None or changed > latest:
            latest = changed
    return None if latest is None else latest.astimezone(timezone).strftime("%H:%M")


def parse_battery(header: str | None) -> int | None:
    """Parse X-Kindle-Battery (0-100) and round it to a multiple of 5."""
    if header is None:
        return None
    header = header.strip()
    if not re.fullmatch(r"\d{1,3}", header):
        return None
    level = int(header)
    if level > 100:
        return None
    return (level + 2) // 5 * 5


def build_view(
    title: str,
    rows: tuple[Row, ...],
    states: dict[str, dict | None],
    timezone: ZoneInfo,
    battery: int | None,
) -> View:
    return View(
        title=title,
        rows=tuple((row.label, format_state(row.entity, states.get(row.entity))) for row in rows),
        data_time=data_time([states.get(row.entity) for row in rows], timezone),
        battery=battery,
    )


def check_fonts() -> None:
    """Fail at startup, not on every request, if the fonts are missing."""
    for path in (FONT_REGULAR, FONT_BOLD):
        ImageFont.truetype(path, 10)


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: float) -> str:
    """Truncate text with an ellipsis so that it fits max_width."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…" if text else ""


def render(view: View) -> bytes:
    image = Image.new("L", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(image)
    content_width = WIDTH - 2 * MARGIN

    # Header
    title_font = ImageFont.truetype(FONT_BOLD, 52)
    draw.text((MARGIN, MARGIN), fit_text(draw, view.title, title_font, content_width), font=title_font, fill=BLACK)
    header_bottom = MARGIN + 75
    draw.line([(MARGIN, header_bottom), (WIDTH - MARGIN, header_bottom)], fill=BLACK, width=3)

    # Footer
    footer_font = ImageFont.truetype(FONT_REGULAR, 24)
    footer_top = HEIGHT - MARGIN - 45
    draw.line([(MARGIN, footer_top), (WIDTH - MARGIN, footer_top)], fill=BLACK, width=2)
    footer_y = HEIGHT - MARGIN - 10
    if view.data_time is not None:
        draw.text((MARGIN, footer_y), f"dati del {view.data_time}", font=footer_font, fill=BLACK, anchor="ls")
    if view.battery is not None:
        draw.text((WIDTH - MARGIN, footer_y), f"batteria {view.battery}%", font=footer_font, fill=BLACK, anchor="rs")

    # Rows: label on the left, value + unit on the right
    top, bottom = header_bottom + 10, footer_top - 10
    row_height = min(100, (bottom - top) // max(len(view.rows), 1))
    label_font = ImageFont.truetype(FONT_REGULAR, max(10, min(38, int(row_height * 0.38))))
    value_font = ImageFont.truetype(FONT_BOLD, max(10, min(42, int(row_height * 0.42))))
    gap = 20
    for i, (label, value) in enumerate(view.rows):
        y_mid = top + i * row_height + row_height // 2
        # The value may take the space the label does not need, but the
        # label always keeps at least 35% of the width.
        label_width = min(draw.textlength(label, font=label_font), content_width * 0.35)
        value = fit_text(draw, value, value_font, content_width - label_width - gap)
        value_width = draw.textlength(value, font=value_font)
        label = fit_text(draw, label, label_font, content_width - value_width - gap)
        draw.text((MARGIN, y_mid), label, font=label_font, fill=BLACK, anchor="lm")
        draw.text((WIDTH - MARGIN, y_mid), value, font=value_font, fill=BLACK, anchor="rm")
        if i < len(view.rows) - 1:
            y_line = top + (i + 1) * row_height
            draw.line([(MARGIN, y_line), (WIDTH - MARGIN, y_line)], fill=BLACK, width=1)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
