from pathlib import Path

from PIL import Image, ImageDraw

from omr_worker.empty_staves import remove_empty_systems

SPACING = 20
WIDTH = 1400
LEFT, RIGHT = 100, 1300


def draw_staff(draw: ImageDraw.ImageDraw, top: int) -> None:
    for line in range(5):
        y = top + line * SPACING
        draw.rectangle((LEFT, y, RIGHT, y + 1), fill="black")


def draw_system(draw: ImageDraw.ImageDraw, top: int, notes: bool) -> None:
    lower = top + 8 * SPACING
    draw_staff(draw, top)
    draw_staff(draw, lower)
    bottom = lower + 4 * SPACING
    draw.rectangle((LEFT, top, LEFT + 1, bottom), fill="black")
    # Ключ в начале системы и тактовые черты музыкой не считаются.
    draw.ellipse((LEFT + 10, top, LEFT + 60, top + 4 * SPACING), fill="black")
    draw.rectangle((700, top, 701, bottom), fill="black")
    draw.rectangle((RIGHT - 1, top, RIGHT, bottom), fill="black")
    if notes:
        draw.ellipse((800, top + 10, 824, top + 28), fill="black")


def make_page(path: Path, systems: list[bool]) -> Path:
    image = Image.new("RGB", (WIDTH, 300 * len(systems) + 100), "white")
    draw = ImageDraw.Draw(image)
    for index, notes in enumerate(systems):
        draw_system(draw, 50 + index * 300, notes)
    image.save(path, format="PNG")
    return path


def staff_rows(path: Path) -> int:
    with Image.open(path) as image:
        gray = image.convert("L")
        width, height = gray.size
        pixels = gray.load()
        return sum(
            sum(pixels[x, y] < 128 for x in range(width)) > width * 0.4 for y in range(height)
        )


def test_empty_system_is_painted_over(tmp_path: Path):
    page = make_page(tmp_path / "p.png", [True, False])
    assert staff_rows(page) == 40  # 2 системы × 2 нотоносца × 5 линеек × 2 строки

    result = remove_empty_systems(page)

    assert (result.removed, result.blank) == (1, False)
    assert staff_rows(page) == 20


def test_page_of_empty_staves_has_nothing_left(tmp_path: Path):
    page = make_page(tmp_path / "p.png", [False, False, False])
    result = remove_empty_systems(page)
    assert (result.removed, result.blank) == (3, True)
    assert staff_rows(page) == 0


def test_page_with_notes_is_not_changed(tmp_path: Path):
    page = make_page(tmp_path / "p.png", [True, True])
    before = page.read_bytes()
    result = remove_empty_systems(page)
    assert (result.removed, result.blank) == (0, False)
    assert page.read_bytes() == before


def test_short_system_with_notes_survives_next_to_empty_one(tmp_path: Path):
    # Последний такт пьесы: нотоносец короче 40 % ширины страницы, ниже — пустая заготовка.
    page = make_page(tmp_path / "p.png", [False, False])
    with Image.open(page) as image:
        image = image.copy()
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 300), fill="white")
    for line in range(5):
        y = 50 + line * SPACING
        draw.rectangle((LEFT, y, LEFT + 400, y + 1), fill="black")
    draw.ellipse((LEFT + 300, 60, LEFT + 324, 78), fill="black")
    image.save(page, format="PNG")

    result = remove_empty_systems(page)

    assert (result.removed, result.blank) == (1, False)
    with Image.open(page) as image:
        assert image.convert("L").getpixel((LEFT + 312, 69)) < 128


def test_page_without_staves_is_not_changed(tmp_path: Path):
    page = tmp_path / "p.png"
    Image.new("L", (400, 400), "white").save(page)
    before = page.read_bytes()
    assert remove_empty_systems(page).removed == 0
    assert page.read_bytes() == before


def test_lines_not_forming_staves_leave_page_alone(tmp_path: Path):
    # Семь длинных линий не складываются в пятёрки: страницу разобрать не удалось.
    page = tmp_path / "p.png"
    image = Image.new("L", (WIDTH, 400), "white")
    draw = ImageDraw.Draw(image)
    for line in range(7):
        y = 50 + line * SPACING
        draw.rectangle((LEFT, y, RIGHT, y + 1), fill="black")
    image.save(page)
    assert remove_empty_systems(page).removed == 0
