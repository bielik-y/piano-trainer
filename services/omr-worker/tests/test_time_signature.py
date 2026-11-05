from pathlib import Path

from omr_worker.measures import (
    check_measures,
    infer_time_signature,
    measures_from_score,
    parse_score,
)
from omr_worker.merge import merge_pages, set_time_signature
from omr_worker.pipeline import run_pipeline

from .fixtures import measure, score
from .test_pipeline import FakeEngine, make_pdf

DIVISIONS = "<attributes><divisions>4</divisions></attributes>"


def in_three(number: int) -> str:
    return measure(number, [("C5", 4), ("D5", 4), ("E5", 4)], [("C3", 4), ("E3", 4), ("G3", 4)])


def in_four(number: int) -> str:
    return measure(number, [("C5", 8), ("E5", 8)], [("C3", 16)])


def page(first: str, *rest: str) -> str:
    """Партитура без размера: homr всегда пишет <divisions>, даже если знак размера не нашёл."""
    return score(first.replace(">", ">" + DIVISIONS, 1), *rest)


def parsed(*measures: str):
    return measures_from_score(parse_score(page(*measures)))


def test_most_common_length_gives_time_signature():
    measures = parsed(*(in_three(n) for n in range(1, 7)))
    assert infer_time_signature(measures) == (3, 4)


def test_eighth_based_length_gives_eighth_beat():
    three_eighths = [measure(n, [("C5", 2), ("D5", 2), ("E5", 2)], []) for n in range(1, 7)]
    assert infer_time_signature(parsed(*three_eighths)) == (3, 8)


def test_pickup_and_short_ending_do_not_affect_result():
    pickup = measure(1, [("G4", 4)], [])
    ending = measure(6, [("C5", 8)], [])
    measures = parsed(pickup, *(in_three(n) for n in range(2, 6)), ending)
    assert infer_time_signature(measures) == (3, 4)


def test_short_extra_voice_does_not_change_length():
    extra_voice = in_four(2).replace(
        "</measure>",
        "<backup><duration>4</duration></backup><note><pitch><step>E</step><octave>4</octave>"
        "</pitch><duration>4</duration><voice>6</voice><type>quarter</type><staff>2</staff>"
        "</note></measure>",
    )
    measures = parsed(in_four(1), extra_voice, in_four(3), in_four(4), in_four(5), in_four(6))
    assert infer_time_signature(measures) == (4, 4)


def test_too_few_measures_give_nothing():
    assert infer_time_signature(parsed(*(in_three(n) for n in range(1, 5)))) is None


def test_no_dominant_length_gives_nothing():
    mixed = [in_three(1), in_three(2), in_four(3), in_three(4), in_four(5), in_four(6)]
    assert infer_time_signature(parsed(*mixed)) is None


def test_written_time_signature_is_read_back_and_follows_schema_order():
    xml = merge_pages([page(in_three(1), in_three(2))]).music_xml

    result = set_time_signature(xml, 3, 4)

    assert "<beats>3</beats>" in result
    measures = measures_from_score(parse_score(result))
    assert check_measures(measures) == {}


def test_time_goes_after_key_in_attributes():
    attributes = "<attributes><divisions>4</divisions><key><fifths>0</fifths></key></attributes>"
    page = score(in_three(1).replace('<measure number="1">', f'<measure number="1">{attributes}'))
    result = set_time_signature(page, 3, 4)
    assert result.index("</key>") < result.index("<time>") < result.index("<note>")


def test_pipeline_infers_missing_time_signature(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=1)
    engine = FakeEngine([page(*(in_three(n) for n in range(1, 7)))])

    output = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50)

    report = output.report
    assert report.time_signature == "3/4"
    assert report.time_signature_source == "inferred"
    assert report.ok_measure_count == 6
    assert "<beats>3</beats>" in output.music_xml.read_text(encoding="utf-8")


def test_pipeline_keeps_time_signature_found_by_engine(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=1)
    first = measure(1, [("C5", 8), ("E5", 8)], [("C3", 16)], time="4/4")
    engine = FakeEngine([score(first, in_three(2), in_three(3), in_three(4), in_three(5))])

    report = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50).report

    assert report.time_signature == "4/4"
    assert report.time_signature_source == "engine"


def test_pipeline_leaves_unknown_when_not_enough_measures(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=1)
    engine = FakeEngine([page(in_three(1), in_three(2))])

    report = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50).report

    assert report.time_signature is None
    assert report.time_signature_source is None
    assert report.quality == "low"
