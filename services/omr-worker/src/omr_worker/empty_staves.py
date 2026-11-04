"""Убирает со страницы пустые нотоносцы (заготовки без нот) до распознавания.

На таких станах homr придумывает ноты, и в партитуре появляются лишние такты. Поэтому системы, где
кроме линеек, ключа и тактовых черт ничего нет, закрашиваются белым.

Проверка осторожная: если страница не разбирается уверенно (фото с наклоном, линейки не складываются
в пятёрки) или рядом с линейками есть любой другой знак, ничего не меняется.
"""

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# Доля ширины страницы, которую должна занимать линейка нотоносца.
LINE_MIN_WIDTH = 0.4
# Допустимое отклонение промежутков между линейками одного нотоносца от их среднего.
SPACING_TOLERANCE = 0.2
# Начало системы, где стоят ключ, знаки при ключе и размер; в межлинейных промежутках.
HEADER_SPACES = 12
# Сколько промежутков над и под системой относится к ней (добавочные линейки, паузы).
MARGIN_SPACES = 2
# Знак шире этой доли промежутка считается музыкой: уже бывают только штили и тактовые черты.
MIN_SIGN_WIDTH = 0.8


@dataclass(frozen=True)
class Staff:
    lines: tuple[tuple[int, int], ...]  # пять линеек: (первая строка, последняя строка)
    left: int
    right: int

    @property
    def top(self) -> int:
        return self.lines[0][0]

    @property
    def bottom(self) -> int:
        return self.lines[-1][1]

    @property
    def spacing(self) -> float:
        return (self.lines[-1][0] - self.lines[0][0]) / 4


@dataclass(frozen=True)
class CleanResult:
    removed: int  # сколько систем закрашено
    blank: bool  # после закрашивания на странице ничего не осталось


def remove_empty_systems(path: Path) -> CleanResult:
    """Закрашивает пустые системы прямо в файле `path`. Без пустых систем файл не меняется."""
    with Image.open(path) as image:
        gray = np.asarray(image.convert("L"))
    ink = gray < 128
    systems = _group_systems(_find_staves(ink), ink)
    empty = [system for system in systems if _is_empty(system, ink)]
    if not empty:
        return CleanResult(removed=0, blank=False)

    with Image.open(path) as image:
        cleaned = image.copy()
    draw = ImageDraw.Draw(cleaned)
    white = 255 if cleaned.mode == "L" else (255,) * len(cleaned.getbands())
    for system in empty:
        top, bottom = _bounds(system, ink.shape[0])
        draw.rectangle((0, top, ink.shape[1], bottom), fill=white)
    cleaned.save(path, format="PNG")
    # Считаем чернила, а не системы: короткий нотоносец в поиск не попадает, но ноты на нём есть.
    left = np.asarray(cleaned.convert("L")) < 128
    return CleanResult(removed=len(empty), blank=not left.any())


def _find_staves(ink: np.ndarray) -> list[Staff]:
    rows = ink.sum(axis=1) > ink.shape[1] * LINE_MIN_WIDTH
    lines: list[tuple[int, int]] = []
    start: int | None = None
    for y, is_line in enumerate(rows):
        if is_line and start is None:
            start = y
        elif not is_line and start is not None:
            lines.append((start, y - 1))
            start = None
    if start is not None:
        lines.append((start, len(rows) - 1))

    # Все линейки обязаны сложиться в пятёрки, иначе страницу не трогаем.
    if not lines or len(lines) % 5 != 0:
        return []
    staves: list[Staff] = []
    for first in range(0, len(lines), 5):
        group = lines[first : first + 5]
        gaps = [b[0] - a[0] for a, b in pairwise(group)]
        average = sum(gaps) / 4
        if any(abs(gap - average) > average * SPACING_TOLERANCE for gap in gaps):
            return []
        # Края нотоносца: столбцы, где есть почти все пять линеек.
        centers = [(a + b) // 2 for a, b in group]
        columns = np.flatnonzero(ink[centers].sum(axis=0) >= 4)
        if columns.size == 0:
            return []
        staves.append(Staff(tuple(group), int(columns[0]), int(columns[-1])))
    return staves


def _group_systems(staves: list[Staff], ink: np.ndarray) -> list[list[Staff]]:
    """Нотоносцы одной системы соединены сплошной вертикальной чертой."""
    systems: list[list[Staff]] = []
    for staff in staves:
        if systems and _connected(systems[-1][-1], staff, ink):
            systems[-1].append(staff)
        else:
            systems.append([staff])
    return systems


def _connected(upper: Staff, lower: Staff, ink: np.ndarray) -> bool:
    gap = ink[upper.bottom + 1 : lower.top]
    if gap.shape[0] == 0:
        return True
    margin = round(upper.spacing)
    left = max(0, min(upper.left, lower.left) - margin)
    right = max(upper.right, lower.right) + margin + 1
    return bool((gap[:, left:right].mean(axis=0) >= 0.95).any())


def _bounds(system: list[Staff], height: int) -> tuple[int, int]:
    margin = round(system[0].spacing * MARGIN_SPACES)
    return max(0, system[0].top - margin), min(height - 1, system[-1].bottom + margin)


def _is_empty(system: list[Staff], ink: np.ndarray) -> bool:
    top, bottom = _bounds(system, ink.shape[0])
    spacing = system[0].spacing
    left = min(staff.left for staff in system) + round(spacing * HEADER_SPACES)
    right = max(staff.right for staff in system) - round(spacing)
    if right <= left:
        return False

    # Без линеек остаётся только то, что на них написано.
    body = ink[top : bottom + 1].copy()
    for staff in system:
        for first, last in staff.lines:
            body[max(0, first - 1 - top) : last + 2 - top] = False

    min_width = max(2, round(spacing * MIN_SIGN_WIDTH))
    run = 0
    for has_ink in body[:, left:right].any(axis=0):
        run = run + 1 if has_ink else 0
        if run >= min_width:
            return False
    return True
