"""Разведение рук по нотоносцам.

На фото homr иногда не связывает скрипичный и басовый станы системы: обе руки попадают на
нотоносец 1 одной цепочкой, аккорды левой руки встают между нотами правой, и такт «вылезает»
за свою длину (5/4, 6/4 вместо 4/4). Высоты и длительности при этом обычно верны.

В фортепианной партии (два нотоносца) такт, где все ноты на нотоносце 1, делится так:
- аккорд (или одиночная нота), нижняя нота которого ниже до первой октавы (C4), — левая рука,
  остальные — правая; пауза идёт с рукой, которой принадлежит большинство нот её голоса;
- в каждой руке ноты встают подряд в прежнем порядке;
- правка принимается, только если обе руки непусты и каждая ровно заполняет такт по размеру.
  Иначе такт остаётся как был: лучше честно помеченный такт, чем уверенно неверный.
Правой руке ставится скрипичный ключ, левой — басовый.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
from xml.etree import ElementTree as ET

from .timing import _rewrite, measures_with_meter, notes_with_onsets

SPLIT_MIDI = 60  # C4: ниже — левая рука
STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
RIGHT, LEFT = "1", "2"
VOICES = {RIGHT: "1", LEFT: "5"}
CLEFS = {RIGHT: ("G", "2"), LEFT: ("F", "4")}
# Порядок элементов <attributes> по схеме MusicXML.
ATTRIBUTE_ORDER = ("footnote", "level", "divisions", "key", "time", "staves", "part-symbol",
                   "instruments", "clef", "staff-details", "transpose", "directive",
                   "measure-style")
STAFF_FOLLOWERS = ("beam", "notations", "lyric", "play", "listen")


@dataclass
class _Group:
    onset: Fraction
    order: int
    voice: str
    notes: list[ET.Element] = field(default_factory=list)

    @property
    def duration(self) -> Fraction:
        return Fraction(int(self.notes[0].findtext("duration") or 0))

    @property
    def lowest(self) -> int | None:
        pitches = [p for p in (_midi(n) for n in self.notes) if p is not None]
        return min(pitches) if pitches else None


def split_hands(music_xml: str) -> str:
    root = ET.fromstring(music_xml.encode("utf-8"))
    lengths = {id(measure): meter.length for measure, meter in measures_with_meter(root)}
    for part in root.findall("part"):
        if not is_piano(part):
            continue
        staves = 1
        clefs: dict[str, tuple[str, str]] = {}
        for measure in part.findall("measure"):
            split = id(measure) in lengths and _split_measure(measure, lengths[id(measure)])
            if split:
                _fix_attributes(measure, staves, clefs)
            staves, clefs = _state_after(measure, staves, clefs)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def is_piano(part: ET.Element) -> bool:
    """Партия на двух нотоносцах хотя бы где-то: объявлено staves = 2 или есть ноты на втором."""
    return any(s.text == "2" for s in part.iter("staves")) or any(
        s.text == LEFT for s in part.iter("staff")
    )


def _split_measure(measure: ET.Element, length: Fraction) -> bool:
    notes = notes_with_onsets(measure)
    if not notes or any((n.findtext("staff") or "1") != RIGHT for _, n in notes):
        return False
    if any(n.find("grace") is not None or n.find("cue") is not None for _, n in notes):
        return False

    groups: list[_Group] = []
    for order, (onset, note) in enumerate(notes):
        if note.find("chord") is not None and groups:
            groups[-1].notes.append(note)
        else:
            groups.append(_Group(onset, order, note.findtext("voice") or "1", [note]))

    voice_hands: dict[str, Counter] = defaultdict(Counter)
    for group in groups:
        if group.lowest is not None:
            voice_hands[group.voice][_hand(group)] += len(group.notes)
    hands: dict[str, list[_Group]] = {RIGHT: [], LEFT: []}
    for group in groups:
        if group.lowest is not None:
            hands[_hand(group)].append(group)
        else:
            votes = voice_hands.get(group.voice)
            hands[votes.most_common(1)[0][0] if votes else RIGHT].append(group)

    if not hands[RIGHT] or not hands[LEFT]:
        return False
    arranged = []
    for hand in (RIGHT, LEFT):
        packed = _pack(hands[hand])
        if packed is None:
            return False
        if sum(group.duration for _, group in packed) != length:
            return False
        arranged.append([(onset, group.notes) for onset, group in packed])

    for hand, voice in zip((RIGHT, LEFT), arranged):
        for _, chord in voice:
            for index, note in enumerate(chord):
                _set_chord(note, index > 0)
                _set_text(note, "voice", VOICES[hand])
                _set_text(note, "staff", hand)
    _rewrite(measure, arranged)
    return True


def _hand(group: _Group) -> str:
    return LEFT if group.lowest is not None and group.lowest < SPLIT_MIDI else RIGHT


def _pack(groups: list[_Group]) -> list[tuple[Fraction, _Group]] | None:
    """Ноты руки подряд в прежнем порядке. Аккорды, начинавшиеся одновременно и равные по
    длительности, сливаются (homr разносит аккорд левой руки по двум голосам); если в одной руке
    одновременно начинаются ноты разной длины — это несколько голосов, такой такт не трогаем."""
    merged: list[_Group] = []
    for group in sorted(groups, key=lambda g: (g.onset, g.order)):
        if merged and merged[-1].onset == group.onset:
            if merged[-1].duration != group.duration:
                return None
            merged[-1].notes.extend(group.notes)
        else:
            merged.append(_Group(group.onset, group.order, group.voice, list(group.notes)))
    cursor = Fraction(0)
    packed = []
    for group in merged:
        packed.append((cursor, group))
        cursor += group.duration
    return packed


def _midi(note: ET.Element) -> int | None:
    pitch = note.find("pitch")
    if pitch is None:
        return None
    step = STEPS.get(pitch.findtext("step") or "")
    octave = pitch.findtext("octave")
    if step is None or octave is None:
        return None
    return 12 * (int(octave) + 1) + step + round(float(pitch.findtext("alter") or 0))


def _set_chord(note: ET.Element, chord: bool) -> None:
    existing = note.find("chord")
    if chord and existing is None:
        note.insert(1 if note.find("grace") is not None else 0, ET.Element("chord"))
    elif not chord and existing is not None:
        note.remove(existing)


def _set_text(note: ET.Element, tag: str, value: str) -> None:
    element = note.find(tag)
    if element is None:
        # <voice> — сразу после <duration> и <tie>, <staff> — перед <beam> и <notations>.
        children = list(note)
        if tag == "voice":
            position = 1 + max(i for i, c in enumerate(children) if c.tag in ("duration", "tie"))
        else:
            position = next(
                (i for i, c in enumerate(children) if c.tag in STAFF_FOLLOWERS), len(children)
            )
        element = ET.Element(tag)
        note.insert(position, element)
    element.text = value


def _state_after(
    measure: ET.Element, staves: int, clefs: dict[str, tuple[str, str]]
) -> tuple[int, dict[str, tuple[str, str]]]:
    """Число нотоносцев и ключи, действующие после такта."""
    clefs = dict(clefs)
    for attributes in measure.findall("attributes"):
        if (value := attributes.findtext("staves")) is not None:
            staves = int(value)
        for clef in attributes.findall("clef"):
            clefs[clef.get("number", "1")] = (clef.findtext("sign") or "", clef.findtext("line") or "")
    return staves, clefs


def _fix_attributes(
    measure: ET.Element, staves: int, clefs: dict[str, tuple[str, str]]
) -> None:
    """Объявляет два нотоносца и ставит ключи рук, если до такта действовали другие."""
    attributes = measure.find("attributes")
    for extra in measure.findall("attributes")[1:]:
        # homr пишет несколько <attributes> подряд в начале такта: сводим в один.
        for child in list(extra):
            extra.remove(child)
            attributes.append(child)
        measure.remove(extra)
    if attributes is None:
        attributes = ET.Element("attributes")
        children = list(measure)
        first_note = next((i for i, c in enumerate(children) if c.tag == "note"), len(children))
        measure.insert(first_note, attributes)
    for clef in attributes.findall("clef"):
        attributes.remove(clef)
    current_staves = attributes.find("staves")
    if staves != 2 and current_staves is None:
        ET.SubElement(attributes, "staves").text = "2"
    elif current_staves is not None:
        current_staves.text = "2"
    for hand in (RIGHT, LEFT):
        if clefs.get(hand) != CLEFS[hand] or staves != 2:
            clef = ET.SubElement(attributes, "clef", number=hand)
            ET.SubElement(clef, "sign").text = CLEFS[hand][0]
            ET.SubElement(clef, "line").text = CLEFS[hand][1]
    order = {tag: i for i, tag in enumerate(ATTRIBUTE_ORDER)}
    children = sorted(list(attributes), key=lambda c: order.get(c.tag, len(order)))
    for child in list(attributes):
        attributes.remove(child)
    attributes.extend(children)
    if len(attributes) == 0:
        measure.remove(attributes)
