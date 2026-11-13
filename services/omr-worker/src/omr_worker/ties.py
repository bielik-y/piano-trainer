"""Залиговки вместо лиг.

homr не различает залиговку (две соседние ноты одной высоты звучат как одна длинная) и лигу
(легато между разными нотами): обе он пишет как `<slur>`. Для игры разница важна: на
залигованную ноту приложение не должно ждать повторного нажатия.

Лига превращается в залиговку, если её начало и конец — ноты одной высоты на одном нотоносце
и вторая вступает ровно тогда, когда кончается первая (в том же такте или в начале
следующего). Тогда залиговываются все общие ноты двух аккордов: homr ставит лигу только на
одну ноту аккорда. Лиги между разными высотами не трогаются.
"""

from dataclasses import dataclass
from fractions import Fraction
from xml.etree import ElementTree as ET

from .timing import notes_with_onsets

# По схеме MusicXML <tie> идёт после <duration>, а <notations> — в конце ноты, перед этими.
AFTER_NOTATIONS = ("lyric", "play", "listen")


@dataclass
class _Note:
    element: ET.Element
    staff: str
    start: Fraction  # в четвертях от начала партии
    end: Fraction
    pitch: tuple[str, int, str] | None


def slurs_to_ties(music_xml: str) -> str:
    root = ET.fromstring(music_xml.encode("utf-8"))
    for part in root.findall("part"):
        notes = _timeline(part)
        for start, stop, slurs in _slur_pairs(notes):
            if (
                start.pitch is None
                or start.pitch != stop.pitch
                or start.staff != stop.staff
                or start.end != stop.start
            ):
                continue
            first = _chord_of(start, notes)
            second = {n.pitch: n for n in _chord_of(stop, notes)}
            for note in first:
                partner = second.get(note.pitch)
                if partner is not None and partner.start == note.end:
                    _tie(note.element, "start")
                    _tie(partner.element, "stop")
            for owner, slur in slurs:
                _remove_slur(owner, slur)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _timeline(part: ET.Element) -> list[_Note]:
    """Ноты партии с абсолютным временем. Такт длится до конца самой поздней ноты в нём."""
    divisions = 1
    offset = Fraction(0)
    result: list[_Note] = []
    for measure in part.findall("measure"):
        for attributes in measure.findall("attributes"):
            if (value := attributes.findtext("divisions")) is not None:
                divisions = int(value)
        length = Fraction(0)
        for onset, note in notes_with_onsets(measure):
            duration = (
                Fraction(0)
                if note.find("grace") is not None
                else Fraction(int(note.findtext("duration") or 0))
            )
            length = max(length, onset + duration)
            if note.find("grace") is not None or note.find("rest") is not None:
                pitch = None
            else:
                pitch = _pitch(note)
            result.append(
                _Note(
                    note,
                    note.findtext("staff") or "1",
                    offset + onset / divisions,
                    offset + (onset + duration) / divisions,
                    pitch,
                )
            )
        offset += length / divisions
    return result


def _pitch(note: ET.Element) -> tuple[str, int, str] | None:
    pitch = note.find("pitch")
    if pitch is None:
        return None
    alter = float(pitch.findtext("alter") or 0)
    if not alter.is_integer():
        return None
    return (pitch.findtext("step") or "", int(alter), pitch.findtext("octave") or "")


def _slur_pairs(
    notes: list[_Note],
) -> list[tuple[_Note, _Note, list[tuple[ET.Element, ET.Element]]]]:
    """Пары (начало, конец лиги) по номеру лиги в порядке записи, с самими элементами <slur>."""
    open_slurs: dict[str, tuple[_Note, ET.Element]] = {}
    pairs = []
    for note in notes:
        for notations in note.element.findall("notations"):
            for slur in notations.findall("slur"):
                number = slur.get("number", "1")
                if slur.get("type") == "start":
                    open_slurs[number] = (note, slur)
                elif slur.get("type") == "stop" and number in open_slurs:
                    start, start_slur = open_slurs.pop(number)
                    pairs.append(
                        (start, note, [(start.element, start_slur), (note.element, slur)])
                    )
    return pairs


def _chord_of(note: _Note, notes: list[_Note]) -> list[_Note]:
    return [
        n
        for n in notes
        if n.staff == note.staff and n.start == note.start and n.end == note.end and n.pitch
    ]


def _tie(note: ET.Element, kind: str) -> None:
    if any(t.get("type") == kind for t in note.findall("tie")):
        return
    children = list(note)
    duration = next(i for i, c in enumerate(children) if c.tag == "duration")
    after = duration + 1 + sum(1 for c in children if c.tag == "tie")
    note.insert(after, ET.Element("tie", type=kind))
    notations = note.find("notations")
    if notations is None:
        notations = ET.Element("notations")
        children = list(note)
        position = next(
            (i for i, c in enumerate(children) if c.tag in AFTER_NOTATIONS), len(children)
        )
        note.insert(position, notations)
    notations.append(ET.Element("tied", type=kind))


def _remove_slur(note: ET.Element, slur: ET.Element) -> None:
    for notations in note.findall("notations"):
        if slur in list(notations):
            notations.remove(slur)
            if len(notations) == 0:
                note.remove(notations)
            return
