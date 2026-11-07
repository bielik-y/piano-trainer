"""Время нот внутри такта.

homr выдаёт ноты обоих нотоносцев одной цепочкой и при записи в MusicXML ставит их по общему
курсору. Если нота одного нотоносца должна вступить, пока на другом ещё звучит длинная нота,
её ставят позже, чем надо, и сдвигается весь остаток голоса. Длительности при этом верны:
внутри голоса просто появляются «дырки», и такт вылезает за свою длину.

`close_voice_gaps` убирает эти дырки, но только в тактах, которые вылезают за длину, и только
если после этого каждый голос в неё укладывается. В остальных тактах время нот не меняется:
голос, который законно начинается не с начала такта, сохраняет своё начало.

Кроме того, голоса каждого такта записываются по очереди, а не вперемешку, как у homr: иначе
просмотрщики путают ребра разных голосов (Verovio соединял ноты верхнего и нижнего нотоносцев).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from xml.etree import ElementTree as ET

TIMING_TAGS = ("backup", "forward")


def notes_with_onsets(measure: ET.Element) -> list[tuple[Fraction, ET.Element]]:
    """Ноты такта с моментом начала в единицах <divisions>, в порядке записи."""
    position = Fraction(0)
    last_onset = Fraction(0)
    result = []
    for child in measure:
        if child.tag in TIMING_TAGS:
            duration = Fraction(int(child.findtext("duration") or 0))
            position += duration if child.tag == "forward" else -duration
        elif child.tag == "note":
            if child.find("chord") is not None:
                onset = last_onset
            else:
                onset = last_onset = position
                position += _duration(child)
            result.append((onset, child))
    return result


@dataclass(frozen=True)
class Meter:
    divisions: int  # единиц на четверть
    beats: int
    beat_type: int

    @property
    def length(self) -> Fraction:
        return Fraction(self.divisions * 4 * self.beats, self.beat_type)


def measures_with_meter(root: ET.Element) -> Iterator[tuple[ET.Element, Meter]]:
    """Такты всех партий с действующим размером; такты до первого размера пропускаются."""
    for part in root.findall("part"):
        divisions: int | None = None
        beats: tuple[int, int] | None = None
        for measure in part.findall("measure"):
            for attributes in measure.findall("attributes"):
                if (value := attributes.findtext("divisions")) is not None:
                    divisions = int(value)
                time = attributes.find("time")
                if time is not None:
                    beats = (int(time.findtext("beats")), int(time.findtext("beat-type")))
            if divisions and beats:
                yield measure, Meter(divisions, *beats)


def close_voice_gaps(music_xml: str) -> str:
    root = ET.fromstring(music_xml.encode("utf-8"))
    for measure, meter in measures_with_meter(root):
        _fix_measure(measure, meter.length)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _fix_measure(measure: ET.Element, length: Fraction) -> None:
    notes = notes_with_onsets(measure)
    if not notes:
        return

    # Голос: группы (начало, ноты аккорда) в порядке записи.
    voices: dict[tuple[str, str], list[tuple[Fraction, list[ET.Element]]]] = {}
    for onset, note in notes:
        key = (note.findtext("staff") or "1", note.findtext("voice") or "1")
        groups = voices.setdefault(key, [])
        if note.find("chord") is not None and groups:
            groups[-1][1].append(note)
        else:
            groups.append((onset, [note]))

    arranged = list(voices.values())
    if max(onset + _duration(note) for onset, note in notes) > length:
        packed = [_pack(groups) for groups in arranged]
        # Если длительностей больше, чем в такте, это ошибка распознавания, а не сдвиг.
        if all(voice[-1][0] + _duration(voice[-1][1][0]) <= length for voice in packed):
            arranged = packed
    _rewrite(measure, arranged)


def _pack(
    groups: list[tuple[Fraction, list[ET.Element]]],
) -> list[tuple[Fraction, list[ET.Element]]]:
    """Ноты голоса подряд, без дырок; начало первой ноты сохраняется."""
    cursor = groups[0][0]
    voice = []
    for _, chord in groups:
        voice.append((cursor, chord))
        cursor += _duration(chord[0])
    return voice


def _rewrite(measure: ET.Element, voices: list[list[tuple[Fraction, list[ET.Element]]]]) -> None:
    children = list(measure)
    first_note = next(i for i, child in enumerate(children) if child.tag == "note")
    head = [c for c in children[:first_note] if c.tag not in TIMING_TAGS]
    tail = [c for c in children[first_note:] if c.tag not in TIMING_TAGS and c.tag != "note"]
    for child in children:
        measure.remove(child)

    body: list[ET.Element] = []
    position = Fraction(0)
    for voice in voices:
        for onset, chord in voice:
            if onset != position:
                tag = "forward" if onset > position else "backup"
                shift = ET.Element(tag)
                ET.SubElement(shift, "duration").text = str(int(abs(onset - position)))
                body.append(shift)
            body.extend(chord)
            position = onset + _duration(chord[0])
    for child in head + body + tail:
        measure.append(child)


def _duration(note: ET.Element) -> Fraction:
    if note.find("grace") is not None:
        return Fraction(0)
    return Fraction(int(note.findtext("duration") or 0))
