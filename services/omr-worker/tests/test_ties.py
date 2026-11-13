from xml.etree import ElementTree as ET

from omr_worker.ties import slurs_to_ties

from .fixtures import score

HEAD = (
    "<attributes><divisions>2</divisions><key><fifths>-3</fifths></key>"
    "<time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves></attributes>"
)


def n(pitch: str, duration: int = 1, chord: bool = False, slur: str | None = None,
      staff: int = 1) -> str:
    """pitch вида 'Eb5'; duration в восьмых (divisions = 2)."""
    step, sign, octave = pitch[0], pitch[1:-1], pitch[-1]
    alter = {"b": "<alter>-1</alter>", "#": "<alter>1</alter>"}.get(sign, "")
    notations = f'<notations><slur type="{slur}" number="1"/></notations>' if slur else ""
    return (
        f"<note>{'<chord/>' if chord else ''}<pitch><step>{step}</step>{alter}"
        f"<octave>{octave}</octave></pitch><duration>{duration}</duration><voice>1</voice>"
        f"<type>eighth</type><staff>{staff}</staff>{notations}</note>"
    )


def bar(number: int, body: str, head: str = "") -> str:
    return f'<measure number="{number}">{head}{body}</measure>'


def ties(xml: str) -> list[list[tuple[str, list[str], int]]]:
    """По тактам: (высота, типы <tie>, число <slur>) для каждой ноты."""
    root = ET.fromstring(slurs_to_ties(xml))
    return [
        [
            (
                note.findtext("pitch/step") + note.findtext("pitch/octave"),
                [t.get("type") for t in note.findall("tie")],
                len(note.findall("notations/slur")),
            )
            for note in measure.findall("note")
        ]
        for measure in root.iter("measure")
    ]


def test_chord_tied_across_barline():
    # Такт 1–2 «You've Got a Friend in Me»: [G4 Eb5] в конце такта залигован в начало следующего;
    # homr поставил лигу только на Eb5.
    first = n("C4", 6) + n("G4") + n("Eb5", chord=True, slur="start")
    second = n("G4") + n("Eb5", chord=True, slur="stop") + n("C5", 6)
    result = ties(score(bar(1, first, HEAD), bar(2, second)))
    assert result[0][1:] == [("G4", ["start"], 0), ("E5", ["start"], 0)]
    assert result[1][:2] == [("G4", ["stop"], 0), ("E5", ["stop"], 0)]
    assert result[1][2] == ("C5", [], 0)


def test_tied_notes_get_tied_notation():
    xml = slurs_to_ties(score(bar(1, n("F#5", 4, slur="start") + n("F#5", 4, slur="stop"), HEAD)))
    root = ET.fromstring(xml)
    assert [t.get("type") for t in root.iter("tied")] == ["start", "stop"]
    # <tie> стоит сразу после <duration>, как требует схема MusicXML.
    first = [child.tag for child in root.find(".//note")]
    assert first[first.index("duration") + 1] == "tie"


def test_slur_between_different_pitches_stays():
    body = n("C5", 4, slur="start") + n("D5", 4, slur="stop")
    assert ties(score(bar(1, body, HEAD))) == [[("C5", [], 1), ("D5", [], 1)]]


def test_same_pitch_not_adjacent_stays_slur():
    # Между нотами одной высоты есть другая нота: это лига, а не залиговка.
    body = n("C5", 2, slur="start") + n("D5", 2) + n("C5", 4, slur="stop")
    assert ties(score(bar(1, body, HEAD)))[0][0] == ("C5", [], 1)


def test_same_pitch_on_other_staff_stays_slur():
    body = n("C4", 4, slur="start") + "<backup><duration>4</duration></backup>"
    body += n("E3", 4, staff=2) + n("C4", 4, staff=2, slur="stop")
    result = ties(score(bar(1, body, HEAD)))
    assert result[0][0] == ("C4", [], 1)


def test_only_common_chord_notes_are_tied():
    # [A4 F#5] → [A4 F5]: залиговывается только A4, лига была на нём.
    body = n("A4", 2, slur="start") + n("F#5", 2, chord=True)
    body += n("A4", 2, slur="stop") + n("F5", 2, chord=True)
    result = ties(score(bar(1, body, HEAD)))[0]
    assert [t for _, t, _ in result] == [["start"], [], ["stop"], []]
