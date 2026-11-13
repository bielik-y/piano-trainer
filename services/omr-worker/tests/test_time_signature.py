from pathlib import Path

from omr_worker.measures import (
    check_measures,
    infer_time_signature,
    measures_from_score,
    parse_score,
)
from omr_worker.merge import (
    merge_pages,
    parse_time_signature,
    replace_time_signature,
    set_time_signature,
)
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

    output = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50)

    report = output.report
    assert report.time_signature_source == "engine"
    assert "<beats>4</beats>" in output.music_xml.read_text(encoding="utf-8")
    # В отчёте — размер большинства тактов: 4/4 только в первом, дальше смена на 3/4.
    assert report.time_signature == "3/4"
    assert [c.time_signature for c in report.time_signature_changes] == ["3/4"]


def test_pipeline_leaves_unknown_when_not_enough_measures(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=1)
    engine = FakeEngine([page(in_three(1), in_three(2))])

    report = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50).report

    assert report.time_signature is None
    assert report.time_signature_source is None
    assert report.quality == "low"


# --- Размер, заданный пользователем ---


def test_parse_time_signature():
    assert parse_time_signature("3/4") == (3, 4)
    assert parse_time_signature("12/8") == (12, 8)
    for value in (None, "", "auto", "3", "0/4", "a/b"):
        assert parse_time_signature(value) is None


def test_replace_time_signature_leaves_one_time():
    second = in_three(2).replace(
        ">", "><attributes><time><beats>2</beats><beat-type>4</beat-type></time></attributes>", 1
    )
    xml = score(measure(1, [("C5", 8), ("E5", 8)], [("C3", 16)], time="4/4"), second)

    result = replace_time_signature(xml, 3, 4)

    assert result.count("<time>") == 1
    assert "<beats>3</beats>" in result
    assert "<attributes />" not in result and "<attributes></attributes>" not in result


def test_pipeline_uses_user_time_signature(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=1)
    # Движок ошибся: написал 4/4, а такты по три четверти.
    first = measure(1, [("C5", 4), ("D5", 4), ("E5", 4)], [("C3", 4), ("E3", 4), ("G3", 4)],
                    time="4/4")
    engine = FakeEngine([score(first, *(in_three(n) for n in range(2, 7)))])

    output = run_pipeline(
        [pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50, time_signature=(3, 4)
    )

    report = output.report
    assert report.time_signature == "3/4"
    assert report.time_signature_source == "user"
    assert report.ok_measure_count == 6
    music_xml = output.music_xml.read_text(encoding="utf-8")
    assert music_xml.count("<time>") == 1
    assert "<beats>3</beats>" in music_xml


def shifted(number: int, time: str | None = None) -> str:
    """Такт 4/4, записанный по общему курсору, как homr на фото: внутри левой руки дырка в
    четверть, такт «вылезает» до 5/4. Сумма длительностей каждого голоса — 4/4."""
    head = ""
    if time:
        beats, beat_type = time.split("/")
        head = (
            "<attributes><divisions>4</divisions><key><fifths>0</fifths></key>"
            f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"
            "<staves>2</staves></attributes>"
        )
    rh = "".join(
        f"<note><pitch><step>{s}</step><octave>5</octave></pitch><duration>4</duration>"
        f"<voice>1</voice><type>quarter</type><staff>1</staff></note>"
        for s in "CDEF"
    )
    def lh_note(step: str, duration: int, kind: str) -> str:
        return (
            f"<note><pitch><step>{step}</step><octave>3</octave></pitch>"
            f"<duration>{duration}</duration><voice>5</voice><type>{kind}</type>"
            "<staff>2</staff></note>"
        )

    # До — четверть, соль — половинная (должна вступить на 2-й доле, а стоит на 3-й), до — четверть.
    lh = (
        "<backup><duration>16</duration></backup>"
        + lh_note("C", 4, "quarter")
        + "<forward><duration>4</duration></forward>"
        + lh_note("G", 8, "half")
        + lh_note("C", 4, "quarter")
    )
    return f'<measure number="{number}">{head}{rh}{lh}</measure>'


def test_engine_meter_from_shifted_measures_is_corrected(tmp_path: Path):
    # Фото «You've Got a Friend in Me» после очистки: homr связал станы, но по общему курсору
    # такты вытянулись, и верхнюю цифру он взял медианой — 5/4.
    pdf = make_pdf(tmp_path / "in.pdf", pages=1)
    measures = [shifted(1, "5/4")] + [shifted(n) for n in range(2, 7)]
    engine = FakeEngine([score(*measures)])

    report = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50).report

    assert report.time_signature == "4/4"
    assert report.time_signature_source == "inferred"
    assert report.ok_measure_count == 6


def test_engine_meter_that_matches_voices_stays(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=1)
    measures = [measure(1, [("C5", 8), ("E5", 8)], [("C3", 16)], time="4/4")]
    measures += [in_four(n) for n in range(2, 6)]
    engine = FakeEngine([score(*measures)])

    report = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50).report

    assert (report.time_signature, report.time_signature_source) == ("4/4", "engine")
