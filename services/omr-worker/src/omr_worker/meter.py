"""Смена размера посреди пьесы.

homr распознаёт только нижнюю цифру размера, а верхнюю берёт как медиану длин тактов страницы,
поэтому в его MusicXML один размер на всю пьесу. Такт в другом размере (например, один такт 5/4
в «Bohemian Rhapsody») выглядит как ошибка длительностей.

Смена размера ставится, только когда такт выглядит законченным в другом размере:
- на каждом нотоносце есть голос ровно этой длины — или нотоносец целиком из одной паузы
  (целотактовую паузу homr пишет целой нотой, её длина подгоняется под такт);
- на нотоносцах есть и ноты, не только паузы;
- длина записывается обычным размером: целое число четвертей или восьмых, не больше 12 долей;
- в фортепианной партии такт есть на обоих нотоносцах (на одном — это слитые руки);
- такт короче половины исходного размера принимается, только если за ним двойная черта или
  повтор либо соседний такт той же длины: одиночный такт в одну долю — обычно потерянные ноты
  («1/4» посреди «You've Got a Friend in Me»).

Обычная ошибка распознавания (потерянная нота на одном нотоносце) этим условиям не отвечает:
длины нотоносцев расходятся. После такта в другом размере исходный размер восстанавливается,
если следующий такт в него укладывается. Первый и последний такты не трогаются: там затакт
и неполный финал.
"""

from fractions import Fraction
from xml.etree import ElementTree as ET

from .hands import is_piano
from .merge import insert_time
from .timing import Meter, measures_with_meter

MAX_BEATS = 12


MeterChange = tuple[int, int, int]  # индекс такта (с 0), доли, длительность доли


def apply_meter_changes(music_xml: str) -> tuple[str, list[MeterChange]]:
    """Возвращает MusicXML и найденные смены размера: такт, с которого действует другой размер.

    Возврат к исходному размеру сменой не считается: «5/4 в такте 3» — одна смена."""
    root = ET.fromstring(music_xml.encode("utf-8"))
    parts = root.findall("part")
    if len(parts) != 1 or sum(1 for _ in root.iter("time")) != 1:
        return music_xml, []  # несколько партий или размер уже меняется — не трогаем

    # Список строится до вставок, поэтому у всех тактов исходный размер пьесы.
    measures = list(measures_with_meter(root))
    piano = is_piano(parts[0])
    lengths = [_complete_length(measure, piano) for measure, _ in measures]
    changes: list[MeterChange] = []
    current: Fraction | None = None
    for index, (measure, meter) in enumerate(measures):
        base = meter.length
        current = current or base
        target = base
        length = lengths[index]
        if (
            0 < index < len(measures) - 1
            and length is not None
            and length != base
            and _signature(length, meter)
            and (
                length * 2 >= base
                or _ends_section(measure)
                or length in (lengths[index - 1], lengths[index + 1])
            )
        ):
            target = length
        if target != current:
            signature = _signature(target, meter) if target != base else None
            insert_time(measure, *(signature or (meter.beats, meter.beat_type)))
            if signature:
                changes.append((index, *signature))
            current = target
        if target != base:
            _stretch_measure_rests(measure, target)
    return ET.tostring(root, encoding="unicode", xml_declaration=True), changes


def _ends_section(measure: ET.Element) -> bool:
    """Такт заканчивается двойной чертой или повтором: короткий такт перед ней — часть
    формы (вольта, конец раздела), а не потерянная нота."""
    for barline in measure.findall("barline"):
        if barline.get("location", "right") != "right":
            continue
        if barline.find("repeat") is not None:
            return True
        if barline.findtext("bar-style") in ("light-light", "light-heavy", "heavy-light"):
            return True
    return False


def _complete_length(measure: ET.Element, piano: bool = False) -> Fraction | None:
    """Длина, которую одинаково заполняют все нотоносцы такта; None — заполняют по-разному.

    В фортепианной партии такт должен быть на обоих нотоносцах: такт только на одном —
    это слитые руки или потерянный нотоносец, а не другой размер."""
    staves: dict[str, dict[str, Fraction]] = {}
    rests_only: dict[str, bool] = {}
    for note in measure.findall("note"):
        staff = note.findtext("staff") or "1"
        rests_only[staff] = rests_only.get(staff, True) and note.find("rest") is not None
        if note.find("chord") is not None or note.find("grace") is not None:
            continue
        voices = staves.setdefault(staff, {})
        voice = note.findtext("voice") or "1"
        voices[voice] = voices.get(voice, Fraction(0)) + int(note.findtext("duration") or 0)

    if piano and set(staves) != {"1", "2"}:
        return None
    with_notes = [staff for staff in staves if not rests_only[staff]]
    if not with_notes:
        return None
    candidates = {max(staves[staff].values()) for staff in with_notes}
    if len(candidates) != 1:
        return None
    length = candidates.pop()
    if any(length not in staves[staff].values() for staff in with_notes):
        return None
    single_rests = all(
        len([n for n in measure.findall("note") if (n.findtext("staff") or "1") == staff]) == 1
        for staff in staves
        if rests_only[staff]
    )
    return length if single_rests else None


def _signature(length: Fraction, meter: Meter) -> tuple[int, int] | None:
    quarters = length / meter.divisions
    for beat_type, per_quarter in ((4, 1), (8, 2)):
        beats = quarters * per_quarter
        if beats.denominator == 1 and 1 <= beats <= MAX_BEATS:
            return int(beats), beat_type
    return None


def _stretch_measure_rests(measure: ET.Element, length: Fraction) -> None:
    """Целотактовая пауза длится весь такт, сколько бы долей в нём ни было."""
    for note in measure.findall("note"):
        staff = note.findtext("staff") or "1"
        same_staff = [n for n in measure.findall("note") if (n.findtext("staff") or "1") == staff]
        rest = note.find("rest")
        if rest is not None and len(same_staff) == 1:
            rest.set("measure", "yes")
            note.find("duration").text = str(int(length))
            _fix_backup_after(measure, note, length)


def _fix_backup_after(measure: ET.Element, note: ET.Element, length: Fraction) -> None:
    """<backup> сразу после удлинённой паузы должен вернуть курсор на её новую длину."""
    children = list(measure)
    index = children.index(note)
    if index + 1 < len(children) and children[index + 1].tag == "backup":
        children[index + 1].find("duration").text = str(int(length))
