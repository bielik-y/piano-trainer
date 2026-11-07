"""Повторное распознавание проблемных строк.

Если после всей постобработки такт остаётся подозрительным, строка нот (система) с ним вырезается
из страницы и распознаётся отдельно. homr растягивает любую картинку до ширины 1920 px и
смотрит на неё целиком, поэтому отдельная строка часто распознаётся иначе, и потерянная нота
находится. Пробуются два варианта: строка как есть и строка с белыми полями (другой масштаб).

Такт заменяется, только если в новом варианте он проходит проверку, а в исходном нет; остальные
такты строки не трогаются. Если в новом варианте другое число тактов, сопоставить их нельзя —
строка пропускается.

Где строки на странице, сообщает сам homr (`--write-staff-positions`: по строке на систему,
координаты в долях страницы).
"""

import copy
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageOps

from .engines.cli import EngineCancelled, EngineError
from .merge import merge_pages
from .models import Cancelled

log = logging.getLogger(__name__)

TIMING = ("note", "backup", "forward")
# Поле над первой и под последней строкой, в долях высоты строки.
EDGE_MARGIN = 0.6
MAX_RERUNS = 12


@dataclass
class System:
    page: int  # индекс страницы (с 0) в списке страниц задачи
    index: int  # номер строки на странице (с 0)
    measures: list[int] = field(default_factory=list)  # индексы тактов партитуры (с 0)


@dataclass
class PageSource:
    image: Path
    positions: Path | None  # файл homr с положением строк


def map_systems(music_xml: str, measures_per_page: list[int]) -> list[System]:
    """Раскладывает такты склеенной партитуры по страницам и строкам (по <print new-system>)."""
    root = ET.fromstring(music_xml.encode("utf-8"))
    part = root.find("part")
    if part is None or len(root.findall("part")) != 1:
        return []
    measures = part.findall("measure")
    pages = [page for page, count in enumerate(measures_per_page) for _ in range(count)]
    systems: list[System] = []
    for index, measure in enumerate(measures[: len(pages)]):
        page = pages[index]
        first_on_page = index == 0 or pages[index - 1] != page
        new_system = any(p.get("new-system") == "yes" for p in measure.findall("print"))
        if first_on_page:
            systems.append(System(page, 0))
        elif new_system:
            systems.append(System(page, systems[-1].index + 1))
        systems[-1].measures.append(index)
    return systems


def system_bounds(positions: Path, image: Path) -> list[tuple[int, int]]:
    """Вертикальные границы строк в пикселях, с полями до середины промежутка к соседям."""
    with Image.open(image) as picture:
        height = picture.height
    spans = []
    for line in positions.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        center, size = float(parts[2]) * height, float(parts[4]) * height
        spans.append((center - size / 2, center + size / 2))
    spans.sort()
    bounds = []
    for i, (top, bottom) in enumerate(spans):
        margin = (bottom - top) * EDGE_MARGIN
        upper = (top + spans[i - 1][1]) / 2 if i > 0 else top - margin
        lower = (bottom + spans[i + 1][0]) / 2 if i + 1 < len(spans) else bottom + margin
        bounds.append((max(0, int(upper)), min(height, int(lower))))
    return bounds


def rerecognize(
    raw_xml: str,
    flagged: set[int],
    systems: list[System],
    sources: list[PageSource],
    recognize: Callable[[Path], str],
    evaluate: Callable[[str], set[int]],
    work: Path,
    should_stop: Callable[[], bool],
) -> tuple[str, list[int]]:
    """Распознаёт заново строки с подозрительными тактами.

    `recognize` — картинка → MusicXML движка; `evaluate` — сырой MusicXML партитуры → индексы
    подозрительных тактов после всей постобработки. Возвращает новый сырой MusicXML и индексы
    заменённых тактов."""
    replaced: list[int] = []
    runs = 0
    bounds_cache: dict[int, list[tuple[int, int]]] = {}
    pages_systems: dict[int, int] = {}
    for system in systems:
        pages_systems[system.page] = pages_systems.get(system.page, 0) + 1

    for system in systems:
        bad = [m for m in system.measures if m in flagged]
        source = sources[system.page] if system.page < len(sources) else None
        if not bad or source is None or source.positions is None or not source.positions.exists():
            continue
        if system.page not in bounds_cache:
            bounds_cache[system.page] = system_bounds(source.positions, source.image)
        bounds = bounds_cache[system.page]
        if len(bounds) != pages_systems[system.page]:
            log.info("Страница %d: строк на картинке %d, в нотах %d — пропускаю",
                     system.page + 1, len(bounds), pages_systems[system.page])
            continue

        for padded in (False, True):
            if not bad or runs >= MAX_RERUNS:
                break
            if should_stop():
                raise Cancelled()
            crop = _crop(source.image, bounds[system.index], padded,
                         work / f"p{system.page + 1}-s{system.index + 1}{'-pad' if padded else ''}.png")
            runs += 1
            try:
                candidate = _measures(recognize(crop))
            except EngineCancelled:
                raise Cancelled() from None
            except EngineError as e:
                log.info("Повторное распознавание строки не удалось: %s", e)
                continue
            if candidate is None or len(candidate[0]) != len(system.measures):
                continue
            new_measures, divisions = candidate
            options = {m: new_measures[system.measures.index(m)] for m in bad}
            trial = transplant(raw_xml, options, divisions)
            if trial is None:
                continue
            still_bad = evaluate(trial)
            fixed = {m: options[m] for m in bad if m not in still_bad}
            if fixed:
                raw_xml = transplant(raw_xml, fixed, divisions) or raw_xml
                replaced += sorted(fixed)
                bad = [m for m in bad if m not in fixed]
                log.info("Строка %d стр. %d: исправлено тактов %d", system.index + 1,
                         system.page + 1, len(fixed))
    return raw_xml, sorted(replaced)


def _crop(image: Path, bounds: tuple[int, int], padded: bool, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image) as picture:
        piece = picture.convert("RGB").crop((0, bounds[0], picture.width, bounds[1]))
    if padded:
        piece = ImageOps.expand(piece, border=piece.width // 8, fill="white")
    piece.save(target, format="PNG")
    return target


def _measures(music_xml: str) -> tuple[list[ET.Element], int] | None:
    """Такты повторного распознавания (после той же очистки, что при склейке) и их <divisions>."""
    merged = merge_pages([music_xml])
    root = ET.fromstring(merged.music_xml.encode("utf-8"))
    part = root.find("part")
    if part is None:
        return None
    measures = part.findall("measure")
    divisions = next((int(d.text) for d in root.iter("divisions") if d.text), None)
    return (measures, divisions) if measures and divisions else None


def transplant(raw_xml: str, replacements: dict[int, ET.Element], divisions: int) -> str | None:
    """Подменяет ноты тактов `replacements` (индекс → такт другого распознавания).

    Разметка исходного такта (ключ, перенос строки, тактовая черта) остаётся; длительности
    пересчитываются в <divisions> исходной страницы. None — пересчитать нацело нельзя."""
    root = ET.fromstring(raw_xml.encode("utf-8"))
    part = root.find("part")
    if part is None:
        return None
    current: int | None = None
    for index, measure in enumerate(part.findall("measure")):
        for value in measure.iter("divisions"):
            current = int(value.text)
        if index not in replacements:
            continue
        if current is None:
            return None
        factor = Fraction(current, divisions)
        body = [copy.deepcopy(c) for c in replacements[index] if c.tag in TIMING]
        for element in body:
            for duration in element.iter("duration"):
                scaled = int(duration.text) * factor
                if scaled.denominator != 1:
                    return None
                duration.text = str(int(scaled))
        children = list(measure)
        first = next((i for i, c in enumerate(children) if c.tag in TIMING), len(children))
        head = [c for c in children[:first] if c.tag not in TIMING]
        tail = [c for c in children[first:] if c.tag not in TIMING]
        for child in children:
            measure.remove(child)
        for child in head + body + tail:
            measure.append(child)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)
