import io
import time

from PIL import Image

from app.dashboard import DashboardView, Heading, TasksCard
from app.home_tasks import Badge, GroupHeader, TaskColumn, TaskRow
from app.render_dashboard import render_dashboard


def view(*blocks, battery=None) -> DashboardView:
    return DashboardView(tuple(blocks), battery)


def column(items=(), empty=None, title="Casa", progress="0 di 0 completate") -> TaskColumn:
    return TaskColumn(title, progress, tuple(items), empty)


def png(dashboard: DashboardView) -> Image.Image:
    data = render_dashboard(dashboard)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    return Image.open(io.BytesIO(data))


def test_png_is_600x800_grayscale_without_alpha():
    image = png(view(Heading("Nuova sezione", False), TasksCard(None, (column(empty="Nessuna attività"),))))
    assert (image.format, image.size, image.mode) == ("PNG", (600, 800), "L")
    assert "transparency" not in image.info


def test_render_is_deterministic():
    rows = [TaskRow("Latte", False, (Badge("Oggi", "strong"), Badge("Anna", icon="person"))),
            GroupHeader("Fatto", 1), TaskRow("Pane", True, ())]
    dashboard = view(TasksCard(None, (column(rows),)), battery=85)
    assert render_dashboard(dashboard) == render_dashboard(dashboard)


def test_empty_dashboard():
    assert png(view()).getextrema() == (0, 255)  # footer line only


def test_battery_changes_the_image():
    assert render_dashboard(view(battery=80)) != render_dashboard(view(battery=85))


def test_every_badge_kind_and_long_texts():
    badges = (Badge("Alta", "inverted"), Badge("1/3"), Badge("Oggi 18:00", "strong"), Badge("↻ Lun Gio"),
              Badge("Anna Maria", icon="person"), Badge("", avatar="AM"), Badge("Anna", avatar="AB"),
              Badge("#" + "x" * 300), Badge("1 ora prima", icon="alarm"))
    rows = [TaskRow("parola" * 100, False, badges), TaskRow("Titolo " * 80, True, badges),
            GroupHeader("Sezione " * 30, 12)]
    image = png(view(Heading("T" * 300, False), Heading("S" * 300, True),
                     TasksCard("Tutto " * 40, (column(rows, title="L" * 300, progress="999 di 999 completate"),))))
    assert image.size == (600, 800)


def test_many_tasks_are_cut_quickly():
    rows = [TaskRow(f"Attività {i}", i % 2 == 0, (Badge("Domani"),)) for i in range(500)]
    start = time.monotonic()
    png(view(TasksCard(None, (column(rows),) * 10)))
    assert time.monotonic() - start < 5


def test_hidden_tasks_change_the_image():
    """The "+N" counter: one more task off-screen still gives a new image."""
    rows = [TaskRow(f"Attività {i}", False, ()) for i in range(30)]
    first = render_dashboard(view(TasksCard(None, (column(rows),))))
    second = render_dashboard(view(TasksCard(None, (column(rows + [TaskRow("Altra", False, ())]),))))
    assert first != second
