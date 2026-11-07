from xml.etree import ElementTree as ET

from omr_worker.beams import add_beams
from omr_worker.measures import check_measures, measures_from_score, parse_score

from .fixtures import score
from .test_accidentals import backup, note

TIME = (
    "<attributes><divisions>4</divisions><key><fifths>0</fifths></key>"
    "<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time></attributes>"
)


def bar(body: str, time: str = "4/4") -> str:
    beats, beat_type = time.split("/")
    return f'<measure number="1">{TIME.format(beats=beats, beat_type=beat_type)}{body}</measure>'


def rest(duration: int) -> str:
    kind = {2: "eighth", 4: "quarter"}[duration]
    return (
        f"<note><rest/><duration>{duration}</duration><voice>1</voice>"
        f"<type>{kind}</type><staff>1</staff></note>"
    )


def beams(xml: str) -> list[str]:
    """Для каждой ноты: ребра по уровням через «/», «-» — без ребра."""
    root = ET.fromstring(add_beams(score(xml)))
    return [
        "/".join(b.text for b in n.findall("beam")) or "-"
        for n in root.iter("note")
    ]


def eighths(count: int) -> str:
    return "".join(note("C5", 2) for _ in range(count))


def test_eight_eighths_in_four_four_are_beamed_by_half_bar():
    assert beams(bar(eighths(8))) == [
        "begin", "continue", "continue", "end", "begin", "continue", "continue", "end",
    ]


def test_quarter_breaks_half_bar_into_beats():
    body = eighths(2) + note("C5", 4) + eighths(4)
    assert beams(bar(body)) == ["begin", "end", "-", "begin", "continue", "continue", "end"]


def test_sixteenths_get_second_beam_inside_beat():
    # Восьмая и две шестнадцатые — одна доля (как в такте 1 «Just The Two Of Us»).
    body = note("C5", 2) + note("D5", 1) + note("E5", 1) + note("C5", 12)
    assert beams(bar(body)) == ["begin", "continue/begin", "end/end", "-"]


def test_dotted_eighth_and_sixteenth_get_hook():
    body = note("C5", 3) + note("D5", 1) + note("E5", 1) + note("F5", 3) + note("C5", 8)
    assert beams(bar(body)) == [
        "begin", "end/backward hook", "begin/forward hook", "end", "-",
    ]


def test_rest_and_lonely_eighth_are_not_beamed():
    body = rest(2) + note("C5", 2) + note("C5", 2) + note("D5", 2) + note("C5", 8)
    assert beams(bar(body)) == ["-", "-", "begin", "end", "-"]


def test_three_four_is_beamed_by_beat():
    assert beams(bar(eighths(6), "3/4")) == ["begin", "end"] * 3


def test_six_eight_is_beamed_by_dotted_quarter():
    assert beams(bar(eighths(6), "6/8")) == ["begin", "continue", "end"] * 2


def test_chord_gets_beam_on_first_note_only_and_voices_separately():
    chord = note("C5", 2) + note("E5", 2, chord=True)
    lower = note("C3", 2, staff=2) + note("D3", 2, staff=2) + note("E3", 12, staff=2)
    body = chord + note("D5", 2) + note("C5", 12) + backup(16) + lower
    assert beams(bar(body)) == ["begin", "-", "end", "-", "begin", "end", "-"]


def test_measure_with_beams_is_left_alone():
    body = eighths(2).replace("</staff>", '</staff><beam number="1">begin</beam>', 1) + note("C5", 12)
    assert beams(bar(body)) == ["begin", "-", "-"]


def test_beam_follows_schema_order_and_check_passes():
    body = note("C5", 2) + note("D5", 2) + note("C5", 12)
    result = add_beams(score(bar(body)))
    tags = [child.tag for child in ET.fromstring(result).find("part/measure/note")]
    assert tags.index("staff") < tags.index("beam")
    assert check_measures(measures_from_score(parse_score(result))) == {}
