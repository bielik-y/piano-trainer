from xml.etree import ElementTree as ET

from omr_worker.measures import check_measures, measures_from_score, parse_score
from omr_worker.meter import apply_meter_changes

from .fixtures import score
from .test_accidentals import backup, note

FIRST = (
    "<attributes><divisions>4</divisions><key><fifths>0</fifths></key>"
    "<time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves></attributes>"
)


def bar(number: int, upper: list[int], lower: list[int] | str) -> str:
    """upper/lower — длительности нот в шестнадцатых; lower="rest" — целотактовая пауза (как у homr)."""
    head = FIRST if number == 1 else ""
    top = "".join(note("C5", d) for d in upper)
    if lower == "rest":
        bottom = (
            "<note><rest/><duration>16</duration><voice>5</voice><type>whole</type>"
            "<staff>2</staff></note>"
        )
    else:
        bottom = "".join(note("C3", d, staff=2) for d in lower)
    return f'<measure number="{number}">{head}{top}{backup(sum(upper))}{bottom}</measure>'


FULL = ([4, 4, 4, 4], [16])


def times(xml: str) -> list[tuple[str, str]]:
    return [
        (m.get("number"), f"{t.findtext('beats')}/{t.findtext('beat-type')}")
        for m in ET.fromstring(xml).iter("measure")
        for t in m.iter("time")
    ]


def test_one_measure_in_five_four_like_bohemian_rhapsody():
    five = bar(3, [4, 4, 4, 4, 4], "rest")
    xml = score(bar(1, *FULL), bar(2, *FULL), five, bar(4, *FULL), bar(5, *FULL))

    result, changes = apply_meter_changes(xml)

    assert changes == [(2, 5, 4)]
    assert times(result) == [("1", "4/4"), ("3", "5/4"), ("4", "4/4")]
    rest = ET.fromstring(result).findall("part/measure")[2].find("note/rest/..")
    assert rest.findtext("duration") == "20" and rest.find("rest").get("measure") == "yes"
    assert check_measures(measures_from_score(parse_score(result))) == {}


def test_section_in_three_four_returns_to_four_four():
    three = ([4, 4, 4], [12])
    xml = score(bar(1, *FULL), bar(2, *three), bar(3, *three), bar(4, *FULL), bar(5, *FULL))
    result, changes = apply_meter_changes(xml)
    assert changes == [(1, 3, 4)]
    assert times(result) == [("1", "4/4"), ("2", "3/4"), ("4", "4/4")]


def test_seven_eight_when_both_staves_agree():
    seven = ([2] * 7, [8, 6])
    xml = score(bar(1, *FULL), bar(2, *seven), bar(3, *FULL), bar(4, *FULL))
    assert times(apply_meter_changes(xml)[0]) == [("1", "4/4"), ("2", "7/8"), ("3", "4/4")]


def test_lost_note_on_one_staff_is_not_a_meter_change():
    # Сверху потеряна восьмая (как такт 18 «TikTok 1.jpg»): нотоносцы расходятся.
    xml = score(bar(1, *FULL), bar(2, [2] * 7, [16]), bar(3, *FULL), bar(4, *FULL))
    result, changes = apply_meter_changes(xml)
    assert changes == []
    assert times(result) == [("1", "4/4")]


def test_odd_length_is_not_a_meter():
    # 17 шестнадцатых на обоих нотоносцах обычным размером не записать.
    xml = score(bar(1, *FULL), bar(2, [4, 4, 4, 4, 1], [16, 1]), bar(3, *FULL), bar(4, *FULL))
    assert apply_meter_changes(xml)[1] == []


def test_first_and_last_measures_are_left_to_pickup_rules():
    xml = score(bar(1, [4, 4], [8]), bar(2, *FULL), bar(3, *FULL), bar(4, [4, 4], [8]))
    assert apply_meter_changes(xml)[1] == []


def test_single_short_measure_is_not_a_meter_change():
    # Такт 34 «You've Got a Friend in Me» с фото: оба нотоносца по четверти — потеряны ноты.
    xml = score(bar(1, *FULL), bar(2, *FULL), bar(3, [4], [4]), bar(4, *FULL), bar(5, *FULL))
    assert apply_meter_changes(xml)[1] == []


def test_short_measure_before_double_barline_is_a_meter_change():
    short = bar(3, [4], [4]).replace(
        "</measure>", '<barline location="right"><bar-style>light-light</bar-style></barline></measure>'
    )
    xml = score(bar(1, *FULL), bar(2, *FULL), short, bar(4, *FULL), bar(5, *FULL))
    assert apply_meter_changes(xml)[1] == [(2, 1, 4)]


def test_piano_measure_on_one_staff_is_not_a_meter_change():
    # Руки слиты на верхнем нотоносце (фото, homr не связал станы): такт 6/4, но это не размер.
    merged = bar(2, [4] * 6, [])
    xml = score(bar(1, *FULL), merged, bar(3, *FULL), bar(4, *FULL))
    assert apply_meter_changes(xml)[1] == []
