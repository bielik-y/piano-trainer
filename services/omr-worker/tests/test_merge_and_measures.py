from omr_worker.measures import check_measures, measures_from_score, parse_score
from omr_worker.merge import merge_pages, page_of_measure

from .fixtures import bad_measure, good_measure, measure, score


def test_merge_appends_measures_and_renumbers():
    page1 = score(good_measure(1, time="4/4"), good_measure(2))
    page2 = score(good_measure(1), bad_measure(2), good_measure(3))
    merged = merge_pages([page1, page2])

    assert merged.measures_per_page == [2, 3]
    parsed = parse_score(merged.music_xml)
    measures = measures_from_score(parsed)
    assert len(measures) == 5
    assert [m.number for m in measures] == ["1", "2", "3", "4", "5"]
    assert len(parsed.parts) == 2  # два нотоносца
    assert '<print new-page="yes"' in merged.music_xml


def test_time_signature_from_first_page_applies_to_next_pages():
    page1 = score(good_measure(1, time="4/4"))
    page2 = score(good_measure(1), bad_measure(2))
    measures = measures_from_score(parse_score(merge_pages([page1, page2]).music_xml))
    assert check_measures(measures) == {2: ["overflow"]}


def test_without_time_signature_measures_are_flagged():
    measures = measures_from_score(parse_score(score(good_measure(1), good_measure(2))))
    assert check_measures(measures) == {0: ["no_time_signature"], 1: ["no_time_signature"]}


def test_page_of_measure():
    assert page_of_measure([2, 0, 3], 0) == 1
    assert page_of_measure([2, 0, 3], 1) == 1
    assert page_of_measure([2, 0, 3], 2) == 3
    assert page_of_measure([2, 0, 3], 4) == 3


CHORD_REST = (
    "<note><chord/><rest/><duration>16</duration><voice>5</voice><type>whole</type>"
    "<staff>2</staff></note>"
)


def test_measure_without_notes_is_dropped_and_passes_markup_on():
    page = score(
        good_measure(1, time="4/4"),
        '<measure number="2"><print new-system="yes"/></measure>',
        good_measure(3),
    )
    merged = merge_pages([page])

    assert merged.measures_per_page == [2]
    measures = measures_from_score(parse_score(merged.music_xml))
    assert [m.number for m in measures] == ["1", "2"]
    assert '<print new-system="yes"' in merged.music_xml


def test_measure_with_only_rests_is_kept():
    rest_measure = measure(2, [("rest", 16)], [("rest", 16)])
    merged = merge_pages([score(good_measure(1, time="4/4"), rest_measure)])
    assert merged.measures_per_page == [2]


def test_page_of_only_empty_measures_gives_no_measures():
    merged = merge_pages([
        score(good_measure(1, time="4/4")),
        score('<measure number="1"><print new-system="yes"/></measure>'),
    ])
    assert merged.measures_per_page == [1, 0]


def test_rest_inside_chord_is_removed():
    broken = good_measure(1, time="4/4").replace("</measure>", CHORD_REST + "</measure>")
    merged = merge_pages([score(broken)])
    assert "<rest" not in merged.music_xml
    assert check_measures(measures_from_score(parse_score(merged.music_xml))) == {}
