from xml.etree import ElementTree as ET

from omr_worker.accidentals import add_accidentals
from omr_worker.measures import check_measures, measures_from_score, parse_score

from .fixtures import score

ATTRIBUTES = (
    "<attributes><divisions>4</divisions><key><fifths>{fifths}</fifths></key>"
    "<time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves>"
    '<clef number="1"><sign>G</sign><line>2</line></clef>'
    '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>'
)
# Длительность в шестнадцатых (divisions = 4) → тип ноты; 3, 6 и 12 — с точкой.
TYPES = {1: "16th", 2: "eighth", 3: "eighth", 4: "quarter", 6: "quarter", 8: "half",
         12: "half", 16: "whole"}
ALTERS = {"#": 1, "b": -1}


def note(pitch: str, duration: int = 4, staff: int = 1, voice: int | None = None,
         chord: bool = False, tie_stop: bool = False) -> str:
    """pitch: 'E5' — без <alter> (бекар), 'Eb5' — бемоль, 'F#5' — диез."""
    step, sign, octave = pitch[0], pitch[1:-1], pitch[-1]
    alter = f"<alter>{ALTERS[sign]}</alter>" if sign else ""
    tie = '<tie type="stop"/>' if tie_stop else ""
    chord_tag = "<chord/>" if chord else ""
    voice = voice or (1 if staff == 1 else 5)
    return (
        f"<note>{chord_tag}<pitch><step>{step}</step>{alter}<octave>{octave}</octave></pitch>"
        f"<duration>{duration}</duration>{tie}<voice>{voice}</voice>"
        f"<type>{TYPES[duration]}</type>{'<dot/>' if duration in (3, 6, 12) else ''}"
        f"<staff>{staff}</staff></note>"
    )


def bar(number: int, body: str, fifths: int | None = None) -> str:
    head = ATTRIBUTES.format(fifths=fifths) if fifths is not None else ""
    return f'<measure number="{number}">{head}{body}</measure>'


def backup(duration: int) -> str:
    return f"<backup><duration>{duration}</duration></backup>"


def accidentals(xml: str) -> list[list[tuple[str, str | None]]]:
    """По тактам: (ступень+октава, знак) для каждой ноты в порядке записи."""
    root = ET.fromstring(add_accidentals(xml))
    return [
        [
            (n.findtext("pitch/step") + n.findtext("pitch/octave"), n.findtext("accidental"))
            for n in m.findall("note")
        ]
        for m in root.iter("measure")
    ]


def test_first_measure_of_just_the_two_of_us():
    # 4 бемоля. Сверху: до, ля-бемоль, ми-бекар, ещё раз ми; снизу ми-бекар октавой ниже.
    upper = note("C6") + note("Ab5") + note("E5") + note("E5")
    lower = note("E4", 16, staff=2)
    xml = score(bar(1, upper + backup(16) + lower, fifths=-4))

    assert accidentals(xml) == [[
        ("C6", None), ("A5", None), ("E5", "natural"), ("E5", None), ("E4", "natural"),
    ]]


def test_accidental_resets_in_next_measure():
    xml = score(
        bar(1, note("E5", 16), fifths=-4),
        bar(2, note("E5", 8) + note("Eb5", 8)),
    )
    assert accidentals(xml) == [[("E5", "natural")], [("E5", "natural"), ("E5", "flat")]]


def test_sharp_outside_key_and_return_to_key_note():
    # 3 диеза: ре-диез, затем ре в той же октаве — бекар; фа-диез из ключа — без знака.
    xml = score(bar(1, note("D#5") + note("D5") + note("F#5") + note("G#5"), fifths=3))
    assert accidentals(xml) == [[
        ("D5", "sharp"), ("D5", "natural"), ("F5", None), ("G5", None),
    ]]


def test_order_by_time_not_by_order_in_file():
    # Второй голос записан после <backup>, но его нота звучит раньше второй ноты первого голоса.
    voice1 = note("E5", 8) + note("E5", 8)
    voice2 = note("Eb5", 4, voice=2)
    xml = score(bar(1, voice1 + backup(16) + voice2, fifths=0))
    assert accidentals(xml) == [[("E5", None), ("E5", "natural"), ("E5", "flat")]]


def test_chord_notes_each_get_their_sign():
    chord = note("C5", 16) + note("Eb5", 16, chord=True) + note("G#5", 16, chord=True)
    assert accidentals(score(bar(1, chord, fifths=0))) == [
        [("C5", None), ("E5", "flat"), ("G5", "sharp")]
    ]


def test_key_change_applies_from_its_measure():
    key_change = '<measure number="2"><attributes><key><fifths>0</fifths></key></attributes>'
    xml = score(
        bar(1, note("F#5", 16), fifths=1),
        bar(2, note("F#5", 16)).replace('<measure number="2">', key_change),
    )
    assert accidentals(xml) == [[("F5", None)], [("F5", "sharp")]]


def test_tied_note_does_not_repeat_sign():
    xml = score(bar(1, note("F#5", 8, tie_stop=True) + note("F#5", 8), fifths=0))
    assert accidentals(xml) == [[("F5", None), ("F5", None)]]


def test_accidental_follows_schema_order_and_check_still_passes():
    result = add_accidentals(score(bar(1, note("E5", 16), fifths=-4)))
    tags = [child.tag for child in ET.fromstring(result).find("part/measure/note")]
    assert tags.index("type") < tags.index("accidental") < tags.index("staff")
    assert check_measures(measures_from_score(parse_score(result))) == {}
