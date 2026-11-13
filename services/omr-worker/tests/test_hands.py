from pathlib import Path
from xml.etree import ElementTree as ET

from omr_worker.hands import split_hands
from omr_worker.measures import check_measures, measures_from_score, parse_score
from omr_worker.timing import notes_with_onsets

from .fixtures import measure, score

FRIEND = (Path(__file__).parent / "data" / "friend_in_me_hands.musicxml").read_text(encoding="utf-8")


def name(note: ET.Element) -> str:
    pitch = note.find("pitch")
    if pitch is None:
        return "rest"
    alter = {"-1": "b", "1": "#"}.get(pitch.findtext("alter") or "", "")
    return pitch.findtext("step") + alter + pitch.findtext("octave")


def hands(xml: str, index: int) -> dict[str, list[tuple[int, list[str]]]]:
    """Такт index: по нотоносцам — (начало в делениях, ноты аккорда по возрастанию)."""
    found = list(ET.fromstring(xml).iter("measure"))[index]
    result: dict[str, dict[int, list[str]]] = {}
    for onset, note in notes_with_onsets(found):
        staff = result.setdefault(note.findtext("staff"), {})
        staff.setdefault(int(onset), []).append(name(note))
    return {s: sorted((t, sorted(n)) for t, n in by.items()) for s, by in result.items()}


def test_friend_in_me_measures_split_into_hands():
    # Такт 1 первой строки (эталон сверен по фото): RH пауза, G4, триоль, F#5, [B4 G5], [G4 Eb5];
    # LH четвертями Eb2, [G3 Bb3 Eb4], D2, [F3 B3 D4]. divisions = 6.
    result = split_hands(FRIEND)
    assert hands(result, 0) == {
        "1": [(0, ["rest"]), (3, ["G4"]), (6, ["Bb4"]), (8, ["Eb5"]), (10, ["F5"]),
              (12, ["F#5"]), (15, ["B4", "G5"]), (21, ["Eb5", "G4"])],
        "2": [(0, ["Eb2"]), (6, ["Bb3", "Eb4", "G3"]), (12, ["D2"]), (18, ["B3", "D4", "F3"])],
    }
    assert hands(result, 2)["2"] == [
        (0, ["Bb1"]), (6, ["Bb3", "Eb3", "G3"]), (12, ["Bb1"]), (18, ["Bb3", "D3", "F3"])
    ]


def test_split_measures_pass_the_check():
    before = check_measures(measures_from_score(parse_score(FRIEND)))
    after = check_measures(measures_from_score(parse_score(split_hands(FRIEND))))
    assert {0, 1, 2} <= set(before)
    assert after == {}


def test_hands_get_their_clefs_and_two_staves():
    root = ET.fromstring(split_hands(FRIEND))
    first = root.find("part/measure/attributes")
    assert first.findtext("staves") == "2"
    clefs = {c.get("number"): c.findtext("sign") for c in first.findall("clef")}
    assert clefs == {"1": "G", "2": "F"}
    # Ключи ставятся один раз, в следующих тактах не повторяются.
    second = list(root.iter("measure"))[1]
    assert second.find("attributes/clef") is None
    # Порядок по схеме: divisions, key, time, staves, clef.
    assert [c.tag for c in first] == ["divisions", "key", "time", "staves", "clef", "clef"]


def test_split_notes_have_staff_voice_and_chords():
    found = list(ET.fromstring(split_hands(FRIEND)).iter("measure"))[0]
    left = [n for n in found.iter("note") if n.findtext("staff") == "2"]
    assert {n.findtext("voice") for n in left} == {"5"}
    # [G3 Bb3 Eb4]: первая нота аккорда без <chord/>, остальные с ним.
    flags = [n.find("chord") is not None for n in left]
    assert flags == [False, False, True, True, False, False, True, True]


def test_measure_that_does_not_fit_stays():
    # После раскладки правая рука короче такта — правка не принимается.
    bad = measure(1, [("C5", 4), ("E5", 4), ("C3", 8), ("G5", 4)], [], time="4/4")
    xml = score(bad, measure(2, [("C5", 16)], [("C3", 16)]))
    assert hands(split_hands(xml), 0) == hands(xml, 0)


def test_single_staff_part_is_not_split():
    xml = score(measure(1, [("C5", 8), ("C3", 8)], [], time="2/4").replace(
        "<staves>2</staves>", "<staves>1</staves>"))
    assert split_hands(xml).count("<staff>2</staff>") == 0


def test_measure_already_on_two_staves_stays():
    xml = score(measure(1, [("C5", 8), ("E5", 8)], [("C3", 16)], time="4/4"))
    assert hands(split_hands(xml), 0) == hands(xml, 0)
