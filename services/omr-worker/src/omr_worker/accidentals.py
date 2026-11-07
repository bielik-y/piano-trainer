"""Знаки альтерации перед нотами.

homr записывает высоту ноты (`<alter>`), но не сам знак (`<accidental>`), поэтому на экране нет
диезов, бемолей и бекаров. Знак ставится по правилам нотной записи:
- ступень по умолчанию альтерирована ключевыми знаками (во всех октавах);
- случайный знак действует до конца такта на этом нотоносце и только в своей октаве;
- знак нужен, если высота ноты отличается от действующей на этот момент.
"""

from collections import defaultdict
from fractions import Fraction
from xml.etree import ElementTree as ET

from .timing import notes_with_onsets

SHARPS_ORDER = "FCGDAEB"
ACCIDENTALS = {2: "double-sharp", 1: "sharp", 0: "natural", -1: "flat", -2: "flat-flat"}
# По схеме MusicXML <accidental> идёт после <type> и <dot>, до этих элементов.
AFTER_ACCIDENTAL = (
    "time-modification", "stem", "notehead", "notehead-text", "staff", "beam", "notations",
    "lyric", "play",
)


def add_accidentals(music_xml: str) -> str:
    root = ET.fromstring(music_xml.encode("utf-8"))
    for part in root.findall("part"):
        fifths = 0
        for measure in part.findall("measure"):
            for key in measure.iter("key"):
                value = key.findtext("fifths")
                if value is not None and value.lstrip("-").isdigit():
                    fifths = int(value)
            _mark_measure(measure, _key_alters(fifths))
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _key_alters(fifths: int) -> dict[str, int]:
    if fifths >= 0:
        return {step: 1 for step in SHARPS_ORDER[:fifths]}
    return {step: -1 for step in SHARPS_ORDER[::-1][:-fifths]}


def _mark_measure(measure: ET.Element, key: dict[str, int]) -> None:
    current: dict[tuple[str, str, str], int] = {}
    by_staff: dict[str, list[tuple[Fraction, int, ET.Element]]] = defaultdict(list)
    for order, (onset, note) in enumerate(notes_with_onsets(measure)):
        by_staff[note.findtext("staff") or "1"].append((onset, order, note))

    for staff, notes in by_staff.items():
        for _, _, note in sorted(notes, key=lambda item: (item[0], item[1])):
            pitch = note.find("pitch")
            if pitch is None or note.find("accidental") is not None:
                continue
            alter = _alter(pitch)
            if alter is None:
                continue  # микротоны не размечаем
            step, octave = pitch.findtext("step") or "", pitch.findtext("octave") or ""
            slot = (staff, step, octave)
            if alter == current.get(slot, key.get(step, 0)):
                continue
            current[slot] = alter
            # Нота, продолжающая залигованную, знак не повторяет.
            if not any(tie.get("type") == "stop" for tie in note.findall("tie")):
                _insert_accidental(note, ACCIDENTALS[alter])


def _alter(pitch: ET.Element) -> int | None:
    text = pitch.findtext("alter")
    if text is None:
        return 0
    value = float(text)
    return int(value) if value.is_integer() and int(value) in ACCIDENTALS else None


def _insert_accidental(note: ET.Element, name: str) -> None:
    accidental = ET.Element("accidental")
    accidental.text = name
    children = list(note)
    position = len(children)
    for index, child in enumerate(children):
        if child.tag in AFTER_ACCIDENTAL:
            position = index
            break
    note.insert(position, accidental)
