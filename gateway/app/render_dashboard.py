"""Draw a DashboardView (600x800, 8-bit grayscale) with Pillow.

Blocks are laid out top to bottom. When the screen is full the rest is left
out and the last line says how many tasks are missing ("+N"). As for the
rows view, the output depends only on the view, never on the time of render.
"""

import io
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .dashboard import DashboardView, Heading
from .home_tasks import Badge, GroupHeader, TaskColumn, TaskRow
from .render import BLACK, FONT_BOLD, FONT_REGULAR, HEIGHT, MARGIN, WHITE, WIDTH, fit_text

GRAY_TEXT = 90  # secondary text
GRAY_DONE = 120  # completed tasks
GRAY_LINE = 190
GRAY_BADGE = 225

MAX_TITLE_LINES = 3
CHECKBOX = 26
TASK_INDENT = CHECKBOX + 14
LINE_GAP = 4
BADGE_GAP = 6
BADGE_PAD_X = 9
OVERFLOW_HEIGHT = 32


@dataclass(frozen=True)
class Fonts:
    heading: ImageFont.FreeTypeFont
    subtitle: ImageFont.FreeTypeFont
    card_title: ImageFont.FreeTypeFont
    progress: ImageFont.FreeTypeFont
    group: ImageFont.FreeTypeFont
    task: ImageFont.FreeTypeFont
    badge: ImageFont.FreeTypeFont
    badge_bold: ImageFont.FreeTypeFont
    footer: ImageFont.FreeTypeFont


def load_fonts() -> Fonts:
    return Fonts(
        heading=ImageFont.truetype(FONT_REGULAR, 32),
        subtitle=ImageFont.truetype(FONT_BOLD, 24),
        card_title=ImageFont.truetype(FONT_BOLD, 30),
        progress=ImageFont.truetype(FONT_REGULAR, 20),
        group=ImageFont.truetype(FONT_BOLD, 21),
        task=ImageFont.truetype(FONT_REGULAR, 26),
        badge=ImageFont.truetype(FONT_REGULAR, 18),
        badge_bold=ImageFont.truetype(FONT_BOLD, 18),
        footer=ImageFont.truetype(FONT_REGULAR, 24),
    )


def line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent


def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: float, max_lines: int) -> list[str]:
    """Word wrap; words longer than a line are cut. The last line gets an
    ellipsis when text is left over."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while draw.textlength(word, font=font) > width:
            cut = len(word)
            while cut > 1 and draw.textlength(word[:cut], font=font) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit_text(draw, lines[-1] + " …", font, width)
    return lines or [""]


class Canvas:
    def __init__(self, fonts: Fonts) -> None:
        self.fonts = fonts
        self.image = Image.new("L", (WIDTH, HEIGHT), WHITE)
        self.draw = ImageDraw.Draw(self.image)
        self.left = MARGIN
        self.width = WIDTH - 2 * MARGIN

    # --- badges --------------------------------------------------------

    def badge_size(self, badge: Badge) -> tuple[int, int]:
        font = self.badge_font(badge)
        height = line_height(font) + 6
        width = 2 * BADGE_PAD_X
        if badge.text:
            width += math.ceil(self.draw.textlength(badge.text, font=font)) + 1
        if badge.icon or badge.avatar:
            width += height - 6 + (6 if badge.text else 0)
            if not badge.text:
                width = height
        return min(width, self.width - TASK_INDENT), height

    def badge_font(self, badge: Badge) -> ImageFont.FreeTypeFont:
        return self.fonts.badge if badge.style == "plain" else self.fonts.badge_bold

    def draw_badge(self, badge: Badge, x: int, y: int) -> None:
        width, height = self.badge_size(badge)
        fill, outline, ink = {
            "plain": (GRAY_BADGE, None, BLACK),
            "strong": (WHITE, BLACK, BLACK),
            "inverted": (BLACK, None, WHITE),
        }[badge.style]
        self.draw.rounded_rectangle([x, y, x + width, y + height], radius=height // 2, fill=fill,
                                    outline=outline, width=2)
        cursor = x + BADGE_PAD_X
        icon_size = height - 8
        if badge.avatar is not None:
            # The card's fallback for a person without picture: initials in a circle
            cursor = x + 3 if not badge.text else cursor - 5
            box = [cursor, y + 3, cursor + height - 6, y + height - 3]
            self.draw.ellipse(box, fill=BLACK if badge.style != "inverted" else WHITE)
            font = ImageFont.truetype(FONT_BOLD, max(8, (height - 6) // 2))
            self.draw.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), badge.avatar, font=font,
                           fill=WHITE if badge.style != "inverted" else BLACK, anchor="mm")
            cursor = box[2] + 6
        elif badge.icon is not None:
            self.draw_icon(badge.icon, cursor, y + 4, icon_size, ink)
            cursor += icon_size + 6
        if badge.text:
            font = self.badge_font(badge)
            label = fit_text(self.draw, badge.text, font, x + width - BADGE_PAD_X - cursor)
            self.draw.text((cursor, y + height / 2), label, font=font, fill=ink, anchor="lm")

    def draw_icon(self, icon: str, x: int, y: int, size: int, ink: int) -> None:
        # DejaVu Sans has neither 👤 nor ⏰: draw them.
        if icon == "person":
            head = size * 0.42
            self.draw.ellipse([x + (size - head) / 2, y, x + (size + head) / 2, y + head], fill=ink)
            self.draw.chord([x + 1, y + head + 1, x + size - 1, y + size * 1.75], 180, 360, fill=ink)
        elif icon == "alarm":
            self.draw.ellipse([x, y, x + size, y + size], outline=ink, width=2)
            cx, cy = x + size / 2, y + size / 2
            self.draw.line([(cx, cy), (cx, y + size * 0.22)], fill=ink, width=2)
            self.draw.line([(cx, cy), (x + size * 0.75, cy)], fill=ink, width=2)

    def layout_badges(self, badges: tuple[Badge, ...], width: int) -> list[list[Badge]]:
        rows: list[list[Badge]] = []
        used = width + 1
        for badge in badges:
            badge_width = self.badge_size(badge)[0]
            if rows and used + BADGE_GAP + badge_width <= width:
                rows[-1].append(badge)
                used += BADGE_GAP + badge_width
            else:
                rows.append([badge])
                used = badge_width
        return rows

    # --- blocks --------------------------------------------------------

    def heading_height(self, heading: Heading) -> int:
        return line_height(self.fonts.subtitle if heading.subtitle else self.fonts.heading) + 10

    def draw_heading(self, heading: Heading, y: int) -> None:
        font = self.fonts.subtitle if heading.subtitle else self.fonts.heading
        self.draw.text((self.left, y), fit_text(self.draw, heading.text, font, self.width), font=font,
                       fill=GRAY_TEXT if heading.subtitle else BLACK)

    def column_header_height(self, column: TaskColumn) -> int:
        if column.title is None and column.progress is None:
            return 0
        return line_height(self.fonts.card_title) + 12

    def draw_column_header(self, column: TaskColumn, y: int) -> None:
        baseline = y + self.fonts.card_title.getmetrics()[0]
        progress_width = 0
        if column.progress is not None:
            progress_width = self.draw.textlength(column.progress, font=self.fonts.progress)
            self.draw.text((self.left + self.width, baseline), column.progress, font=self.fonts.progress,
                           fill=GRAY_TEXT, anchor="rs")
        if column.title is not None:
            title = fit_text(self.draw, column.title, self.fonts.card_title, self.width - progress_width - 16)
            self.draw.text((self.left, baseline), title, font=self.fonts.card_title, fill=BLACK, anchor="ls")

    def group_height(self) -> int:
        return line_height(self.fonts.group) + 14

    def draw_group(self, group: GroupHeader, y: int) -> None:
        font = self.fonts.group
        name = fit_text(self.draw, group.name, font, self.width - 60)
        self.draw.text((self.left, y + 8), name, font=font, fill=GRAY_TEXT)
        if group.count:
            badge = Badge(str(group.count))
            self.draw_badge(badge, self.left + int(self.draw.textlength(name, font=font)) + 10, y + 8)

    def task_layout(self, task: TaskRow) -> tuple[list[str], list[list[Badge]], int]:
        text_width = self.width - TASK_INDENT
        lines = wrap(self.draw, task.title, self.fonts.task, text_width, MAX_TITLE_LINES)
        badge_rows = self.layout_badges(task.badges, text_width)
        height = 10 + len(lines) * (line_height(self.fonts.task) + LINE_GAP)
        for row in badge_rows:
            height += max(self.badge_size(b)[1] for b in row) + LINE_GAP
        return lines, badge_rows, max(height + 8, CHECKBOX + 20)

    def draw_task(self, task: TaskRow, y: int, separator: bool) -> None:
        lines, badge_rows, height = self.task_layout(task)
        if separator:
            self.draw.line([(self.left, y), (self.left + self.width, y)], fill=GRAY_LINE, width=1)
        box_top = y + 10 + (line_height(self.fonts.task) - CHECKBOX) // 2
        box = [self.left, box_top, self.left + CHECKBOX, box_top + CHECKBOX]
        if task.completed:
            self.draw.rounded_rectangle(box, radius=5, fill=GRAY_DONE)
            self.draw.line([(box[0] + 6, box_top + 13), (box[0] + 11, box_top + 19), (box[0] + 20, box_top + 7)],
                           fill=WHITE, width=3)
        else:
            self.draw.rounded_rectangle(box, radius=5, outline=BLACK, width=2)
        x = self.left + TASK_INDENT
        cursor = y + 10
        ink = GRAY_DONE if task.completed else BLACK
        for line in lines:
            self.draw.text((x, cursor), line, font=self.fonts.task, fill=ink)
            if task.completed:
                mid = cursor + self.fonts.task.getmetrics()[0] * 0.62
                self.draw.line([(x, mid), (x + self.draw.textlength(line, font=self.fonts.task), mid)],
                               fill=ink, width=2)
            cursor += line_height(self.fonts.task) + LINE_GAP
        for row in badge_rows:
            bx = x
            for badge in row:
                self.draw_badge(badge, bx, cursor)
                bx += self.badge_size(badge)[0] + BADGE_GAP
            cursor += max(self.badge_size(b)[1] for b in row) + LINE_GAP

    def empty_height(self) -> int:
        return line_height(self.fonts.task) + 30

    def draw_empty(self, label: str, y: int) -> None:
        self.draw.text((self.left + self.width / 2, y + 15), label, font=self.fonts.task, fill=GRAY_DONE, anchor="ma")


@dataclass(frozen=True)
class Item:
    space: int  # empty space above
    kind: str  # heading | header | empty | group | task
    payload: object
    separator: bool = False  # line above a task that follows another task


def flatten(view: DashboardView) -> list[Item]:
    """Everything to draw, in order. Nothing is measured yet: only what
    reaches the screen ever is (see render_dashboard)."""
    items: list[Item] = []

    def add(space: int, kind: str, payload: object, separator: bool = False) -> None:
        items.append(Item(space if items else 0, kind, payload, separator))

    for block in view.blocks:
        if isinstance(block, Heading):
            add(14, "heading", block)
            continue
        if block.title:
            add(14, "heading", Heading(block.title, False))
        for column in block.columns:
            if column.title is not None or column.progress is not None:
                add(10, "header", column)
            if column.empty is not None:
                add(0, "empty", column.empty)
            previous = None
            for entry in column.items:
                if isinstance(entry, GroupHeader):
                    add(0, "group", entry)
                else:
                    add(0, "task", entry, isinstance(previous, TaskRow))
                previous = entry
    return items


def item_height(canvas: Canvas, item: Item) -> int:
    if item.kind == "heading":
        return canvas.heading_height(item.payload)
    if item.kind == "header":
        return canvas.column_header_height(item.payload)
    if item.kind == "empty":
        return canvas.empty_height()
    if item.kind == "group":
        return canvas.group_height()
    return canvas.task_layout(item.payload)[2]


def render_dashboard(view: DashboardView) -> bytes:
    canvas = Canvas(load_fonts())
    draw = canvas.draw

    # Footer: battery only (tasks have no "data time" like entity rows)
    footer_top = HEIGHT - MARGIN - 45
    draw.line([(MARGIN, footer_top), (WIDTH - MARGIN, footer_top)], fill=BLACK, width=2)
    if view.battery is not None:
        draw.text((WIDTH - MARGIN, HEIGHT - MARGIN - 10), f"batteria {view.battery}%", font=canvas.fonts.footer,
                  fill=BLACK, anchor="rs")

    bottom = footer_top - 10
    y = MARGIN
    items = flatten(view)
    for index, item in enumerate(items):
        last = index == len(items) - 1
        room = bottom - (0 if last else OVERFLOW_HEIGHT)
        height = item_height(canvas, item)
        needed = item.space + height
        if item.kind in ("heading", "header", "group") and not last:
            # Keep a title with what follows it: never end the page on one
            following = items[index + 1]
            needed += following.space + item_height(canvas, following)
        if y + needed > room:
            hidden = sum(1 for i in items[index:] if i.kind == "task")
            if hidden:
                draw.text((WIDTH - MARGIN, bottom), f"+{hidden}", font=canvas.fonts.group, fill=GRAY_TEXT,
                          anchor="rd")
            break
        y += item.space
        if item.kind == "heading":
            canvas.draw_heading(item.payload, y)
        elif item.kind == "header":
            canvas.draw_column_header(item.payload, y)
        elif item.kind == "empty":
            canvas.draw_empty(item.payload, y)
        elif item.kind == "group":
            canvas.draw_group(item.payload, y)
        else:
            canvas.draw_task(item.payload, y, item.separator)
        y += height

    buffer = io.BytesIO()
    canvas.image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
