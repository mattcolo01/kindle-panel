import io
import time

from PIL import Image

from app.buttons import BUTTONS, TaskRef
from app.dashboard import DashboardView, Heading, TasksCard
from app.home_tasks import Badge, GroupHeader, TaskColumn, TaskRow
from app.render_dashboard import render_dashboard


def view(*blocks, battery=None, buttons=()) -> DashboardView:
    return DashboardView(tuple(blocks), battery, tuple(buttons))


def column(items=(), empty=None, title="Casa", progress="0 di 0 completate") -> TaskColumn:
    return TaskColumn(title, progress, tuple(items), empty)


def png(dashboard: DashboardView) -> Image.Image:
    data = render_dashboard(dashboard).png
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
    assert render_dashboard(dashboard).png == render_dashboard(dashboard).png


def test_empty_dashboard():
    assert png(view()).getextrema() == (0, 255)  # footer line only


def test_battery_changes_the_image():
    assert render_dashboard(view(battery=80)).png != render_dashboard(view(battery=85)).png


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
    first = render_dashboard(view(TasksCard(None, (column(rows),)))).png
    second = render_dashboard(view(TasksCard(None, (column(rows + [TaskRow("Altra", False, ())]),)))).png
    assert first != second


def task(i: int, completed: bool = False) -> TaskRow:
    return TaskRow(f"Attività {i}", completed, (), TaskRef("L1", f"t{i}", f"Attività {i}"))


def test_buttons_go_to_the_first_open_tasks_drawn():
    rows = [task(0, completed=True), task(1), TaskRow("Senza id", False, ()), task(2), task(3)]
    rendered = render_dashboard(view(TasksCard(None, (column(rows),)), buttons=("up", "select")))
    assert {k: v.task_id for k, v in rendered.presses.items()} == {"up": "t1", "select": "t2"}


def test_buttons_continue_across_columns_and_cards():
    card1 = TasksCard(None, (column([task(1)]), column([task(2, completed=True), task(3)])))
    card2 = TasksCard("Altro", (column([task(4), task(5)]),))
    rendered = render_dashboard(view(card1, card2, buttons=BUTTONS[:3]))
    assert [rendered.presses[b].task_id for b in BUTTONS[:3]] == ["t1", "t3", "t4"]


def test_tasks_off_screen_get_no_button():
    # Three-line titles: far fewer than the 12 buttons reach the screen
    rows = [TaskRow("parola " * 40, False, (), TaskRef("L1", f"t{i}", "x")) for i in range(40)]
    rendered = render_dashboard(view(TasksCard(None, (column(rows),)), buttons=BUTTONS))
    drawn = len(rendered.presses)
    assert 0 < drawn < len(BUTTONS)
    assert [ref.task_id for ref in rendered.presses.values()] == [f"t{i}" for i in range(drawn)]
    assert list(rendered.presses) == list(BUTTONS[:drawn])
    few = render_dashboard(view(TasksCard(None, (column([task(1), task(2)]),)), buttons=BUTTONS))
    assert list(few.presses) == ["right_next", "right_prev"]


def test_every_key_symbol_is_drawn_and_distinct():
    rows = [task(i) for i in range(len(BUTTONS))]
    images = set()
    for name in BUTTONS:
        rendered = render_dashboard(view(TasksCard(None, (column(rows[:1]),)), buttons=(name,)))
        images.add(rendered.png)
    assert len(images) == len(BUTTONS)


def test_no_buttons_draws_as_before():
    """Without buttons the rows keep their layout and no task is pressable."""
    rows = [task(1), task(2)]
    plain = render_dashboard(view(TasksCard(None, (column(rows),))))
    same = render_dashboard(view(TasksCard(None, (column([TaskRow(r.title, r.completed, ()) for r in rows]),))))
    assert plain.presses == {}
    assert plain.png == same.png
