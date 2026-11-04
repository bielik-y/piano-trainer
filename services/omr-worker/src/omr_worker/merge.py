"""Склейка страниц в одну партитуру.

homr распознаёт каждую страницу отдельно и выдаёт partwise-MusicXML (обычно одна партия
с двумя нотоносцами). Такты каждой партии следующих страниц дописываются в ту же по порядку
партию первой страницы, номера тактов идут подряд. Размер такта, напечатанный только на первой
странице, после склейки действует и дальше — так устроен MusicXML.
"""

from dataclasses import dataclass
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class MergedScore:
    music_xml: str
    # Сколько тактов дала каждая страница (по первой партии), в порядке страниц.
    measures_per_page: list[int]


def merge_pages(documents: list[str]) -> MergedScore:
    if not documents:
        raise ValueError("нет страниц для склейки")
    roots = [ET.fromstring(doc.encode("utf-8")) for doc in documents]
    for root in roots:
        _clean_page(root)
    base = roots[0]
    base_parts = base.findall("part")
    counts = [len(base_parts[0].findall("measure")) if base_parts else 0]

    for root in roots[1:]:
        parts = root.findall("part")
        counts.append(len(parts[0].findall("measure")) if parts else 0)
        for index, part in enumerate(parts):
            measures = part.findall("measure")
            if not measures:
                continue
            # Страница начинается с новой страницы и при отображении.
            measures[0].insert(0, ET.Element("print", {"new-page": "yes"}))
            if index < len(base_parts):
                base_parts[index].extend(measures)
            # Лишние партии (на странице их больше, чем на первой) не теряем: такты партии
            # без пары не на чем показать, проверка отметит такты как missing_on_staff.

    for part in base_parts:
        for number, measure in enumerate(part.findall("measure"), start=1):
            measure.set("number", str(number))
    xml = ET.tostring(base, encoding="unicode", xml_declaration=True)
    return MergedScore(music_xml=xml, measures_per_page=counts)


def _clean_page(root: ET.Element) -> None:
    """Убирает то, что homr выдаёт по ошибке и чего в нотах быть не может."""
    parts = root.findall("part")
    for part in parts:
        for measure in part.findall("measure"):
            _drop_rests_in_chords(measure)
    _drop_measures_without_notes(parts)


def _drop_rests_in_chords(measure: ET.Element) -> None:
    # Пауза не может звучать в аккорде; такой элемент роняет просмотрщики MusicXML (OSMD).
    for note in measure.findall("note"):
        if note.find("rest") is not None and note.find("chord") is not None:
            measure.remove(note)


def _drop_measures_without_notes(parts: list[ET.Element]) -> None:
    """Такт без единой ноты и паузы — это не такт: homr создаёт его на переносе строки.

    Настоящий пустой такт записан паузой, поэтому он останется. Разметку (перенос строки, ключ,
    реприза слева) удалённый такт передаёт следующему."""
    measures = [part.findall("measure") for part in parts]
    for index in range(max((len(m) for m in measures), default=0)):
        row = [m[index] for m in measures if index < len(m)]
        if any(measure.find("note") is not None for measure in row):
            continue
        for part, part_measures in zip(parts, measures):
            if index >= len(part_measures):
                continue
            if index + 1 < len(part_measures):
                _move_markup(part_measures[index], part_measures[index + 1])
            part.remove(part_measures[index])


def _move_markup(source: ET.Element, target: ET.Element) -> None:
    has_print = target.find("print") is not None
    position = 0
    for child in list(source):
        if child.tag == "print" and has_print:
            continue
        if child.tag == "barline" and child.get("location", "right") == "right":
            continue
        target.insert(position, child)
        position += 1


def page_of_measure(measures_per_page: list[int], index: int) -> int:
    """Номер страницы (с 1) для такта с индексом `index` (с 0)."""
    total = 0
    for page, count in enumerate(measures_per_page, start=1):
        total += count
        if index < total:
            return page
    return len(measures_per_page)
