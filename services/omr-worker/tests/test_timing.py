from fractions import Fraction
from xml.etree import ElementTree as ET

from omr_worker.measures import check_measures, measures_from_score, parse_score
from omr_worker.timing import close_voice_gaps, notes_with_onsets

from .fixtures import measure, score
from .test_accidentals import backup, bar, note


def onsets(xml: str) -> list[list[tuple[str, str, int]]]:
    """По тактам: (нотоносец, высота, начало) в порядке записи."""
    root = ET.fromstring(xml)
    return [
        [
            (n.findtext("staff"), n.findtext("pitch/step") + n.findtext("pitch/octave"), int(t))
            for t, n in notes_with_onsets(m)
        ]
        for m in root.iter("measure")
    ]


# Такт 3 «Just The Two Of Us» так, как его записал homr (divisions = 4, 4/4): ля-бемоль снизу
# поставлен после верхней до (на 8 вместо 7), и всё дальше сдвинуто на шестнадцатую.
SHIFTED = bar(
    1,
    note("C5", 3)
    + backup(3)
    + note("D4", 4, staff=2)
    + backup(1)
    + note("F5", 1)
    + note("F5", 1)
    + backup(1)
    + note("F4", 3, staff=2)
    + backup(2)
    + note("C5", 3)
    + note("A4", 1, staff=2)
    + note("E5", 2)
    + backup(2)
    + note("C4", 2, staff=2)
    + note("G5", 2)
    + backup(2)
    + note("E4", 6, staff=2)
    + backup(4)
    + note("B5", 2)
    + note("C6", 2),
    fifths=-4,
)


def test_shifted_measure_is_put_back_in_time():
    result = close_voice_gaps(score(SHIFTED))

    by_staff = {"1": [], "2": []}
    for staff, pitch, start in onsets(result)[0]:
        by_staff[staff].append((pitch, start))
    assert by_staff["1"] == [
        ("C5", 0), ("F5", 3), ("F5", 4), ("C5", 5), ("E5", 8), ("G5", 10), ("B5", 12), ("C6", 14),
    ]
    assert by_staff["2"] == [("D4", 0), ("F4", 4), ("A4", 7), ("C4", 8), ("E4", 10)]
    assert check_measures(measures_from_score(parse_score(result))) == {}


def test_measure_that_fits_is_not_touched():
    # Дополнительный голос законно начинается на третьей доле — не сдвигаем его к началу.
    body = (
        note("C5", 16)
        + backup(16)
        + note("C3", 16, staff=2)
        + backup(8)
        + note("E3", 8, staff=2, voice=6)
    )
    xml = score(bar(1, body, fifths=0))
    assert onsets(close_voice_gaps(xml)) == onsets(xml)


def test_too_long_voice_is_left_as_recognition_error():
    # Сверху 5 четвертей: дырки убирать бессмысленно, такт остаётся помеченным.
    body = "".join(note(p) for p in ("C5", "D5", "E5", "F5", "G5")) + backup(20) + note(
        "C3", 16, staff=2
    )
    xml = score(bar(1, body, fifths=0))
    assert close_voice_gaps(xml) == ET.tostring(
        ET.fromstring(xml.encode("utf-8")), encoding="unicode", xml_declaration=True
    )


def test_markup_keeps_its_place():
    barline = '<barline location="right"><bar-style>light-heavy</bar-style></barline>'
    shifted = SHIFTED.replace("</attributes>", '</attributes><print new-system="yes"/>', 1)
    xml = score(shifted.replace("</measure>", barline + "</measure>"))

    result = close_voice_gaps(xml)

    assert result != xml  # такт действительно переписан
    tags = [child.tag for child in ET.fromstring(result).find("part/measure")]
    assert tags[:2] == ["attributes", "print"]
    assert tags[-1] == "barline"


def test_short_extra_voice_is_not_an_error_when_staff_is_full():
    # Такт 26 «TikTok 1.jpg»: снизу основной голос на весь такт и нота покороче во втором голосе.
    extra = (
        "<backup><duration>8</duration></backup><note><pitch><step>C</step><octave>4</octave>"
        "</pitch><duration>4</duration><voice>6</voice><type>quarter</type><staff>2</staff></note>"
    )
    full = measure(2, [("C5", 8), ("E5", 8)], [("C3", 16)]).replace("</measure>", extra + "</measure>")
    measures = measures_from_score(
        parse_score(score(measure(1, [("C5", 16)], [("C3", 16)], time="4/4"), full, measure(
            3, [("C5", 16)], [("C3", 16)]
        )))
    )
    assert check_measures(measures) == {}


def test_short_voices_without_full_one_are_still_an_error():
    # Такт 18 «TikTok 1.jpg»: снизу 3 и 1 четверть, такт целиком не заполняет ни один голос.
    extra = (
        "<backup><duration>4</duration></backup><note><pitch><step>C</step><octave>4</octave>"
        "</pitch><duration>4</duration><voice>6</voice><type>quarter</type><staff>2</staff></note>"
    )
    short = measure(2, [("C5", 8), ("E5", 8)], [("C3", 12)]).replace("</measure>", extra + "</measure>")
    measures = measures_from_score(
        parse_score(score(measure(1, [("C5", 16)], [("C3", 16)], time="4/4"), short, measure(
            3, [("C5", 16)], [("C3", 16)]
        )))
    )
    assert check_measures(measures) == {1: ["duration_mismatch"]}


def test_onsets_follow_backup_forward_and_chords():
    forward = "<forward><duration>4</duration></forward>"
    body = note("C5", 8) + note("E5", 8, chord=True) + backup(8) + forward + note("G5", 4, voice=2)
    starts = [t for t, _ in notes_with_onsets(ET.fromstring(bar(1, body)))]
    assert starts == [Fraction(0), Fraction(0), Fraction(4)]


def test_voices_are_written_one_after_another_without_moving_notes():
    # Как пишет homr: ноты верхнего и нижнего нотоносцев вперемешку через <backup>.
    body = (
        note("G5", 2) + backup(2) + note("C4", 2, staff=2)
        + note("E5", 2) + backup(2) + note("E4", 2, staff=2)
        + note("B5", 2) + backup(2) + note("G4", 4, staff=2) + backup(2)
        + note("C6", 2)
    )
    xml = score(bar(1, body, fifths=0))

    result = close_voice_gaps(xml)

    staves = [staff for staff, _, _ in onsets(result)[0]]
    assert staves == ["1", "1", "1", "1", "2", "2", "2"]
    assert sorted(onsets(result)[0]) == sorted(onsets(xml)[0])
