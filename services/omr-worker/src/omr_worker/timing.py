"""Время нот внутри такта.

homr выдаёт ноты обоих нотоносцев одной цепочкой и при записи в MusicXML ставит их по общему
курсору. Если нота одного нотоносца должна вступить, пока на другом ещё звучит длинная нота,
её ставят позже, чем надо, и сдвигается весь остаток голоса. Длительности при этом верны:
внутри голоса просто появляются «дырки», и такт вылезает за свою длину.

`close_voice_gaps` убирает эти дырки, но только в тактах, которые вылезают за длину, и только
если после этого каждый голос в неё укладывается. Остальные такты не трогаются: голос, который
законно начинается не с начала такта, сохраняет своё начало.
"""

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


def close_voice_gaps(music_xml: str) -> str:
    root = ET.fromstring(music_xml.encode("utf-8"))
    for part in root.findall("part"):
        divisions: int | None = None
        length: Fraction | None = None
        beats: tuple[int, int] | None = None
        for measure in part.findall("measure"):
            for attributes in measure.findall("attributes"):
                if (value := attributes.findtext("divisions")) is not None:
                    divisions = int(value)
                time = attributes.find("time")
                if time is not None:
                    beats = (int(time.findtext("beats")), int(time.findtext("beat-type")))
            if divisions and beats:
                length = Fraction(divisions * 4 * beats[0], beats[1])
            if length is not None:
                _fix_measure(measure, length)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _fix_measure(measure: ET.Element, length: Fraction) -> None:
    notes = notes_with_onsets(measure)
    if not notes or max(onset + _duration(note) for onset, note in notes) <= length:
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

    packed: list[list[tuple[Fraction, list[ET.Element]]]] = []
    for groups in voices.values():
        cursor = groups[0][0]
        voice = []
        for _, chord in groups:
            voice.append((cursor, chord))
            cursor += _duration(chord[0])
        if cursor > length:
            return  # длительностей больше, чем в такте: это ошибка распознавания, не сдвиг
        packed.append(voice)
    _rewrite(measure, packed)


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
